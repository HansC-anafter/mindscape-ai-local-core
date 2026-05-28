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
        from backend.app.routes.core.capability_install_core.paths import (
            _require_control_plane_install,
        )

        _require_control_plane_install("cloud-provider-install-default")

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

        from backend.app.database.write_readiness import DatabaseWriteNotReadyError
        from backend.app.routes.core.capability_install_core.routes import (
            _raise_db_not_ready,
        )
        from backend.app.services.capability_install_jobs import (
            CapabilityInstallJobService,
        )

        install_job_service = CapabilityInstallJobService()
        jobs = []
        skipped = []

        for pack_info in packs_catalog.get("packs", []):
            try:
                pack_code = pack_info.get("code")
                pack_ref = pack_info.get("pack_ref")
                download_url = pack_info.get("download_url")

                if not pack_code:
                    skipped.append({"reason": "missing_pack_code", "pack": pack_info})
                    continue

                if not pack_ref and not download_url:
                    skipped.append(
                        {
                            "pack_code": pack_code,
                            "reason": "missing_pack_ref_or_download_url",
                        }
                    )
                    continue

                job = install_job_service.create_cloud_pack_job(
                    provider_id=provider_id,
                    pack_ref=pack_ref or pack_code,
                    verify_checksum=True,
                    allow_overwrite=False,
                    overwrite_review_confirmation="",
                    profile_id="default-user",
                    bundle=bundle,
                    pack_code=pack_code,
                    download_url=download_url,
                )
                jobs.append(
                    {
                        "pack_code": pack_code,
                        "pack_ref": pack_ref,
                        "install_id": job["install_id"],
                        "state": job["state"],
                        "status_url": job["status_url"],
                    }
                )
            except DatabaseWriteNotReadyError as exc:
                _raise_db_not_ready(exc)
            except Exception as e:
                logger.error(f"Failed to enqueue pack {pack_info.get('code')}: {e}", exc_info=True)
                skipped.append({
                    "pack_code": pack_info.get("code"),
                    "error": str(e)
                })

        return {
            "success": len(jobs) > 0,
            "accepted": True,
            "bundle": bundle,
            "provider_id": provider_id,
            "jobs": jobs,
            "skipped": skipped,
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
