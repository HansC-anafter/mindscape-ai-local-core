from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from backend.app.services.cloud_extension_manager import CloudExtensionManager
from backend.app.services.system_settings_store import SystemSettingsStore

from .catalog import _get_packs_catalog
from .dependencies import get_cloud_manager, get_settings_store
from .helpers import parse_action_required
from .schemas import TestConnectionResponse
from .state import logger

router = APIRouter()

@router.post("/{provider_id}/test", response_model=TestConnectionResponse)
async def test_provider_connection(
    provider_id: str,
    cloud_manager: CloudExtensionManager = Depends(get_cloud_manager)
):
    """
    Test connection to a cloud provider

    Returns:
        - If authorized: success=True
        - If 403 ACTION_REQUIRED: action_required with actions[] (neutral Provider Contract)
    """
    try:
        provider = cloud_manager.get_provider(provider_id)
        if not provider:
            raise HTTPException(status_code=404, detail=f"Provider '{provider_id}' not found")

        if not provider.is_configured():
            return {
                "success": False,
                "message": "Provider not configured",
                "action_required": None
            }

        # Try to get packs catalog to check entitlement
        # If 403, return action_required (neutral Provider Contract)
        catalog = await _get_packs_catalog(provider)

        if isinstance(catalog, dict) and catalog.get("state") == "ACTION_REQUIRED":
            action_required = parse_action_required(catalog)
            return {
                "success": False,
                "message": f"Action required: {catalog.get('reason', 'UNKNOWN')}",
                "action_required": action_required
            }

        # If catalog is available, test connection
        success, message = await cloud_manager.test_provider_connection(provider_id)
        return {
            "success": success,
            "message": message,
            "action_required": None
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to test provider connection: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to test connection: {str(e)}")


@router.post("/{provider_id}/install-default")
async def install_default_packs(
    provider_id: str,
    bundle: str = "default",
    cloud_manager: CloudExtensionManager = Depends(get_cloud_manager),
    settings_store: SystemSettingsStore = Depends(get_settings_store)
):
    """
    Install default packs from provider (one-click install)

    Hard Rule: This endpoint only triggers PackInstaller.
    PackInstaller creates isolated pack venv and installs protocol there.
    local-core core does NOT install protocol.
    """
    try:
        provider = cloud_manager.get_provider(provider_id)
        if not provider:
            raise HTTPException(status_code=404, detail=f"Provider '{provider_id}' not found")

        if not provider.is_configured():
            raise HTTPException(status_code=400, detail="Provider not configured")

        # Get packs catalog from provider API
        # Hard Rule: local-core backend calls provider API (not site-hub directly)
        packs_catalog = await _get_packs_catalog(provider, bundle)

        # Check if response indicates action required (neutral Provider Contract)
        if isinstance(packs_catalog, dict) and packs_catalog.get("state") == "ACTION_REQUIRED":
            action_required = parse_action_required(packs_catalog)
            raise HTTPException(
                status_code=403,
                detail={
                    "state": "ACTION_REQUIRED",
                    "reason": packs_catalog.get("reason", "ENTITLEMENT_REQUIRED"),
                    "message": "Action required to install packs",
                    "actions": [action.model_dump() for action in action_required.actions] if action_required else []
                }
            )

        if not packs_catalog or not isinstance(packs_catalog, dict):
            raise HTTPException(status_code=404, detail=f"No packs found for bundle '{bundle}'")

        # Use new modular installers
        from pathlib import Path
        import tempfile
        import httpx
        import os
        import yaml

        from app.services.mindpack_extractor import MindpackExtractor
        from app.services.manifest_validator import ManifestValidator
        from app.services.playbook_installer import PlaybookInstaller
        from app.services.runtime_assets_installer import RuntimeAssetsInstaller
        from app.services.post_install import PostInstallHandler
        from app.services.install_result import InstallResult

        local_core_root = Path(__file__).parent.parent.parent.parent.parent.parent
        capabilities_dir = local_core_root / "backend" / "app" / "capabilities"
        specs_dir = local_core_root / "backend" / "playbooks" / "specs"
        i18n_base_dir = local_core_root / "backend" / "i18n" / "playbooks"

        installed_packs = []
        errors = []

        for pack_info in packs_catalog.get("packs", []):
            try:
                pack_code = pack_info.get("code")
                pack_ref = pack_info.get("pack_ref")
                download_url = pack_info.get("download_url")

                if not pack_code:
                    continue

                # If download_url is not provided, get it from download_link API
                if not download_url and pack_ref:
                    try:
                        download_info = await provider.get_download_link(pack_ref)
                        download_url = download_info.get("download_url")
                        if not download_url:
                            logger.warning(f"No download_url for pack {pack_ref}, skipping")
                            continue
                    except Exception as e:
                        logger.error(f"Failed to get download link for pack {pack_ref}: {e}", exc_info=True)
                        errors.append({
                            "pack_code": pack_code,
                            "error": f"Failed to get download link: {str(e)}"
                        })
                        continue

                if not download_url:
                    logger.warning(f"No download_url for pack {pack_code}, skipping")
                    continue

                # Download pack zip/mindpack file
                headers = {}
                api_key = provider.get_api_key() if hasattr(provider, 'get_api_key') else None
                if api_key:
                    headers["X-API-Key"] = api_key

                async with httpx.AsyncClient(timeout=60.0) as client:
                    response = await client.get(download_url, headers=headers)
                    response.raise_for_status()

                    # Save to temp file
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".mindpack") as tmp_file:
                        tmp_file.write(response.content)
                        tmp_path = Path(tmp_file.name)

                    try:
                        # Install using new modular installers
                        # 1. Extract mindpack
                        extractor = MindpackExtractor(local_core_root)
                        extract_success, temp_dir, capability_code, cap_dir = extractor.extract(tmp_path)

                        if not extract_success or not capability_code or not cap_dir:
                            errors.append({
                                "pack_code": pack_code,
                                "error": "Failed to extract mindpack file or capability code not found"
                            })
                            continue

                        # 2. Load and validate manifest
                        manifest_path = cap_dir / "manifest.yaml"
                        if not manifest_path.exists():
                            errors.append({
                                "pack_code": pack_code,
                                "error": "manifest.yaml not found in mindpack"
                            })
                            continue

                        try:
                            with open(manifest_path, 'r', encoding='utf-8') as f:
                                manifest = yaml.safe_load(f)
                        except Exception as e:
                            errors.append({
                                "pack_code": pack_code,
                                "error": f"Failed to parse manifest: {e}"
                            })
                            continue

                        # Validate manifest
                        validator = ManifestValidator(local_core_root)
                        skip_validation = os.getenv("MINDSCAPE_SKIP_VALIDATION", "0") == "1"
                        is_valid, validation_errors, validation_warnings = validator.validate(
                            manifest_path, cap_dir, skip_validation=skip_validation
                        )

                        if not is_valid and not skip_validation:
                            errors.append({
                                "pack_code": pack_code,
                                "error": f"Manifest validation failed: {validation_errors}"
                            })
                            continue

                        # 3. Initialize install result
                        result = InstallResult(capability_code=capability_code)
                        result.warnings.extend(validation_warnings)

                        # 4. Install playbooks
                        playbook_installer = PlaybookInstaller()
                        playbook_installer.capabilities_dir = capabilities_dir
                        playbook_installer.specs_dir = specs_dir
                        playbook_installer.i18n_base_dir = i18n_base_dir
                        playbook_installer.local_core_root = local_core_root
                        playbook_installer._install_playbooks(cap_dir, capability_code, manifest, result)

                        # 5. Install runtime assets
                        runtime_installer = RuntimeAssetsInstaller(
                            local_core_root=local_core_root,
                            capabilities_dir=capabilities_dir
                        )
                        runtime_installer.install_all(cap_dir, capability_code, manifest, result, temp_dir)

                        # 6. Run post-install hooks
                        post_install_handler = PostInstallHandler(
                            local_core_root=local_core_root,
                            capabilities_dir=capabilities_dir,
                            specs_dir=specs_dir,
                            validate_tools_direct_call_func=playbook_installer._validate_tools_direct_call
                        )
                        post_install_handler.run_all(cap_dir, capability_code, manifest, result)

                        # 7. Reload capability registry
                        try:
                            from app.services.capability_registry import get_registry
                            registry = get_registry()
                            if hasattr(registry, '_capabilities_cache'):
                                registry._capabilities_cache.clear()
                            if hasattr(registry, '_tools_cache'):
                                registry._tools_cache.clear()
                            logger.info(f"Reloaded capability registry for {capability_code}")
                        except Exception as e:
                            logger.warning(f"Failed to reload capability registry: {e}")

                        # Check installation result
                        if result.has_errors():
                            errors.append({
                                "pack_code": pack_code,
                                "error": result.errors[0] if result.errors else "Installation failed"
                            })
                        else:
                            installed_packs.append({
                                "pack_code": pack_code,
                                "version": manifest.get("version", "unknown"),
                                "status": "installed"
                            })
                    finally:
                        # Clean up temp file and directory
                        if tmp_path.exists():
                            tmp_path.unlink()
                        if temp_dir and Path(temp_dir).exists():
                            import shutil
                            shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception as e:
                logger.error(f"Failed to install pack {pack_info.get('code')}: {e}", exc_info=True)
                errors.append({
                    "pack_code": pack_info.get("code"),
                    "error": str(e)
                })

        return {
            "success": len(installed_packs) > 0,
            "installed": installed_packs,
            "errors": errors
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to install default packs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to install packs: {str(e)}")


@router.get("/{provider_id}/packs")
async def list_provider_packs(
    provider_id: str,
    cloud_manager: CloudExtensionManager = Depends(get_cloud_manager)
):
    """
    List packs available from provider

    Returns:
        - If authorized: packs catalog
        - If 403 ACTION_REQUIRED: action_required with actions[] (neutral Provider Contract)
    """
    try:
        provider = cloud_manager.get_provider(provider_id)
        if not provider:
            raise HTTPException(status_code=404, detail=f"Provider '{provider_id}' not found")

        if not provider.is_configured():
            raise HTTPException(status_code=400, detail="Provider not configured")

        # Get packs catalog from provider API
        catalog = await _get_packs_catalog(provider)

        # Check if response indicates action required (neutral Provider Contract)
        if isinstance(catalog, dict) and catalog.get("state") == "ACTION_REQUIRED":
            action_required = parse_action_required(catalog)
            return {
                "action_required": action_required.model_dump() if action_required else None,
                "packs": []
            }

        return {
            "action_required": None,
            "packs": catalog.get("packs", []) if isinstance(catalog, dict) else []
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list provider packs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list packs: {str(e)}")


@router.get("/{provider_id}/actions")
async def get_provider_actions(
    provider_id: str,
    return_to: Optional[str] = None,
    cloud_manager: CloudExtensionManager = Depends(get_cloud_manager)
):
    """
    Get available actions for provider (neutral Provider Contract)

    Args:
        provider_id: Provider identifier
        return_to: Return URL after action (default: current settings page)

    Returns:
        ProviderActionRequired with actions[] (neutral format, not site-hub specific)
    """
    try:
        provider = cloud_manager.get_provider(provider_id)
        if not provider:
            raise HTTPException(status_code=404, detail=f"Provider '{provider_id}' not found")

        if not provider.is_configured():
            raise HTTPException(status_code=400, detail="Provider not configured")

        # Get actions from provider API (neutral Provider Contract)
        # Hard Rule: This is Provider Contract, not site-hub specific
        catalog = await _get_packs_catalog(provider)

        if isinstance(catalog, dict) and catalog.get("state") == "ACTION_REQUIRED":
            action_required = parse_action_required(catalog)
            return action_required.model_dump() if action_required else {
                "state": "ACTION_REQUIRED",
                "reason": "UNKNOWN",
                "actions": [],
                "retry_after_sec": None
            }

        # If no action required, return empty actions
        return {
            "state": "OK",
            "reason": None,
            "actions": [],
            "retry_after_sec": None
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get purchase URL: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get purchase URL: {str(e)}")
