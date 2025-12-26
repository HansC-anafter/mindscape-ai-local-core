"""
Cloud Providers API Routes
Manage cloud playbook providers (add, edit, delete, test)
"""

import logging
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, Field

from ...services.cloud_extension_manager import CloudExtensionManager
from ...services.system_settings_store import SystemSettingsStore
from ...services.cloud_providers.official import OfficialCloudProvider
from ...services.cloud_providers.generic_http import GenericHttpProvider
from ...models.system_settings import SettingType

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/cloud-providers", tags=["cloud-providers"])


class ProviderConfig(BaseModel):
    """Provider configuration model"""
    provider_id: str = Field(..., description="Unique provider identifier")
    provider_type: str = Field(..., description="Provider type: official, generic_http, or custom")
    enabled: bool = Field(True, description="Whether provider is enabled")
    config: Dict[str, Any] = Field(..., description="Provider-specific configuration")


class ProviderResponse(BaseModel):
    """Provider response model"""
    provider_id: str
    provider_type: str
    enabled: bool
    configured: bool
    name: str
    description: str
    config: Dict[str, Any]


class ProviderAction(BaseModel):
    """
    Provider action link (neutral contract)

    ⚠️ Hard Rule: This is part of Provider Contract, not site-hub specific.
    local-core does not need to know if it's site-hub, green world, or WooCommerce.
    """
    type: str  # e.g., "BROWSER_AUTH", "MANAGE", "DOCS"
    label: str  # Display label for UI
    rel: str  # Enum: "purchase" | "manage" | "login" | "docs"
    url: str  # Action URL (must be in allowed_domains)
    expires_at: Optional[str] = None  # ISO 8601 timestamp


class ProviderActionRequired(BaseModel):
    """
    Provider action required response (neutral contract)

    ⚠️ Hard Rule: This is Provider Contract, not site-hub specific.
    """
    state: str  # e.g., "ACTION_REQUIRED"
    reason: str  # e.g., "ENTITLEMENT_REQUIRED"
    actions: List[ProviderAction]  # List of available actions
    retry_after_sec: Optional[int] = None  # Seconds to wait before retry


class TestConnectionResponse(BaseModel):
    """Test connection response model"""
    success: bool
    message: str
    action_required: Optional[ProviderActionRequired] = None


def get_settings_store() -> SystemSettingsStore:
    """Dependency to get settings store"""
    return SystemSettingsStore()


def get_cloud_manager() -> CloudExtensionManager:
    """Dependency to get cloud extension manager"""
    try:
        return CloudExtensionManager.instance()
    except Exception as e:
        logger.error(f"Failed to get cloud extension manager: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to initialize cloud extension manager: {str(e)}")


@router.get("", response_model=List[ProviderResponse])
async def list_providers(
    settings_store: SystemSettingsStore = Depends(get_settings_store),
    cloud_manager: CloudExtensionManager = Depends(get_cloud_manager)
):
    """
    List all configured cloud providers
    """
    try:
        # Get providers config - use get() with default empty list
        providers_config = settings_store.get("cloud_providers", default=[])

        # Ensure providers_config is a list
        if not isinstance(providers_config, list):
            logger.warning(f"cloud_providers setting is not a list: {type(providers_config)}, resetting to empty list")
            providers_config = []

        result = []
        for provider_config in providers_config:
            if not isinstance(provider_config, dict):
                logger.warning(f"Invalid provider config format: {type(provider_config)}, skipping")
                continue

            provider_id = provider_config.get("provider_id")
            provider_type = provider_config.get("provider_type")
            enabled = provider_config.get("enabled", False)
            config = provider_config.get("config", {})

            if not provider_id:
                logger.warning("Provider config missing provider_id, skipping")
                continue

            # Get provider instance to check status
            provider = cloud_manager.get_provider(provider_id)
            if provider:
                result.append({
                    "provider_id": provider_id,
                    "provider_type": provider_type,
                    "enabled": enabled,
                    "configured": provider.is_configured(),
                    "name": provider.get_provider_name(),
                    "description": provider.get_provider_description(),
                    "config": config
                })
            else:
                # Provider not registered yet (might be disabled or not loaded)
                result.append({
                    "provider_id": provider_id,
                    "provider_type": provider_type,
                    "enabled": enabled,
                    "configured": False,
                    "name": provider_id,
                    "description": f"{provider_type} provider",
                    "config": config
                })

        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list providers: {e}", exc_info=True, stack_info=True)
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to list providers: {str(e)}")


@router.post("", response_model=ProviderResponse)
async def create_provider(
    provider: ProviderConfig,
    settings_store: SystemSettingsStore = Depends(get_settings_store),
    cloud_manager: CloudExtensionManager = Depends(get_cloud_manager)
):
    """
    Create a new cloud provider
    """
    try:
        providers_config = settings_store.get("cloud_providers")
        if providers_config is None:
            providers_config = []

        # Check if provider_id already exists
        for existing in providers_config:
            if existing.get("provider_id") == provider.provider_id:
                raise HTTPException(
                    status_code=400,
                    detail=f"Provider with ID '{provider.provider_id}' already exists"
                )

        # Validate provider type
        if provider.provider_type not in ["official", "generic_http", "custom"]:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid provider type: {provider.provider_type}"
            )

        # Create provider instance to validate configuration
        provider_instance = _create_provider_instance(
            provider.provider_id,
            provider.provider_type,
            provider.config,
            settings_store
        )

        if provider_instance:
            # Validate configuration
            is_valid, error_msg = provider_instance.validate_config(provider.config)
            if not is_valid:
                raise HTTPException(status_code=400, detail=error_msg or "Invalid configuration")

        # Add to settings
        new_provider = {
            "provider_id": provider.provider_id,
            "provider_type": provider.provider_type,
            "enabled": provider.enabled,
            "config": provider.config
        }

        providers_config.append(new_provider)
        settings_store.set_setting(
            key="cloud_providers",
            value=providers_config,
            value_type=SettingType.JSON,
            category="cloud"
        )

        # Register provider if enabled
        if provider.enabled and provider_instance:
            cloud_manager.register_provider(provider_instance)

        return {
            "provider_id": provider.provider_id,
            "provider_type": provider.provider_type,
            "enabled": provider.enabled,
            "configured": provider_instance.is_configured() if provider_instance else False,
            "name": provider_instance.get_provider_name() if provider_instance else provider.provider_id,
            "description": provider_instance.get_provider_description() if provider_instance else f"{provider.provider_type} provider",
            "config": provider.config
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create provider: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create provider: {str(e)}")


@router.put("/{provider_id}", response_model=ProviderResponse)
async def update_provider(
    provider_id: str,
    provider: ProviderConfig,
    settings_store: SystemSettingsStore = Depends(get_settings_store),
    cloud_manager: CloudExtensionManager = Depends(get_cloud_manager)
):
    """
    Update an existing cloud provider
    """
    try:
        if provider_id != provider.provider_id:
            raise HTTPException(
                status_code=400,
                detail="Provider ID in path must match provider ID in body"
            )

        providers_config = settings_store.get("cloud_providers")
        if providers_config is None:
            providers_config = []

        # Find and update provider
        found = False
        for i, existing in enumerate(providers_config):
            if existing.get("provider_id") == provider_id:
                # Unregister old provider
                old_provider = cloud_manager.get_provider(provider_id)
                if old_provider:
                    cloud_manager.unregister_provider(provider_id)

                # Create new provider instance
                provider_instance = _create_provider_instance(
                    provider.provider_id,
                    provider.provider_type,
                    provider.config,
                    settings_store
                )

                if provider_instance:
                    # Validate configuration
                    is_valid, error_msg = provider_instance.validate_config(provider.config)
                    if not is_valid:
                        raise HTTPException(status_code=400, detail=error_msg or "Invalid configuration")

                # Update provider
                providers_config[i] = {
                    "provider_id": provider.provider_id,
                    "provider_type": provider.provider_type,
                    "enabled": provider.enabled,
                    "config": provider.config
                }

                # Register if enabled
                if provider.enabled and provider_instance:
                    cloud_manager.register_provider(provider_instance)

                found = True
                break

        if not found:
            raise HTTPException(status_code=404, detail=f"Provider '{provider_id}' not found")

        settings_store.set_setting(
            key="cloud_providers",
            value=providers_config,
            value_type=SettingType.JSON,
            category="cloud"
        )

        provider_instance = cloud_manager.get_provider(provider_id)
        return {
            "provider_id": provider.provider_id,
            "provider_type": provider.provider_type,
            "enabled": provider.enabled,
            "configured": provider_instance.is_configured() if provider_instance else False,
            "name": provider_instance.get_provider_name() if provider_instance else provider.provider_id,
            "description": provider_instance.get_provider_description() if provider_instance else f"{provider.provider_type} provider",
            "config": provider.config
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update provider: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update provider: {str(e)}")


@router.delete("/{provider_id}")
async def delete_provider(
    provider_id: str,
    settings_store: SystemSettingsStore = Depends(get_settings_store),
    cloud_manager: CloudExtensionManager = Depends(get_cloud_manager)
):
    """
    Delete a cloud provider
    """
    try:
        providers_config = settings_store.get("cloud_providers")
        if providers_config is None:
            providers_config = []

        # Find and remove provider
        found = False
        for i, existing in enumerate(providers_config):
            if existing.get("provider_id") == provider_id:
                providers_config.pop(i)
                found = True
                break

        if not found:
            raise HTTPException(status_code=404, detail=f"Provider '{provider_id}' not found")

        settings_store.set_setting(
            key="cloud_providers",
            value=providers_config,
            value_type=SettingType.JSON,
            category="cloud"
        )

        # Unregister from manager
        if cloud_manager.get_provider(provider_id):
            cloud_manager.unregister_provider(provider_id)

        return {"message": f"Provider '{provider_id}' deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete provider: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to delete provider: {str(e)}")


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
            action_required = _parse_action_required(catalog)
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

    ⚠️ Hard Rule: This endpoint only triggers PackInstaller.
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
        # ⚠️ Hard Rule: local-core backend calls provider API (not site-hub directly)
        packs_catalog = await _get_packs_catalog(provider, bundle)

        # Check if response indicates action required (neutral Provider Contract)
        if isinstance(packs_catalog, dict) and packs_catalog.get("state") == "ACTION_REQUIRED":
            action_required = _parse_action_required(packs_catalog)
            raise HTTPException(
                status_code=403,
                detail={
                    "state": "ACTION_REQUIRED",
                    "reason": packs_catalog.get("reason", "ENTITLEMENT_REQUIRED"),
                    "message": "Action required to install packs",
                    "actions": [action.dict() for action in action_required.actions] if action_required else []
                }
            )

        if not packs_catalog or not isinstance(packs_catalog, dict):
            raise HTTPException(status_code=404, detail=f"No packs found for bundle '{bundle}'")

        # Use existing CapabilityInstaller
        # ⚠️ Hard Rule: Pack venv and protocol installation should be handled by pack runtime executor
        # For now, CapabilityInstaller installs packs to local-core capabilities directory
        # Protocol installation in pack venv will be handled when pack is executed (not during install)

        from ...services.capability_installer import CapabilityInstaller
        from pathlib import Path
        import tempfile
        import httpx

        local_core_root = Path(__file__).parent.parent.parent.parent.parent
        installer = CapabilityInstaller(local_core_root=local_core_root)

        installed_packs = []
        errors = []

        for pack_info in packs_catalog.get("packs", []):
            try:
                pack_code = pack_info.get("code")
                download_url = pack_info.get("download_url")

                if not pack_code or not download_url:
                    continue

                # Download pack zip/mindpack file
                headers = {}
                api_key = provider.get_api_key() if hasattr(provider, 'get_api_key') else None
                if api_key:
                    headers["Authorization"] = f"Bearer {api_key}"

                async with httpx.AsyncClient(timeout=60.0) as client:
                    response = await client.get(download_url, headers=headers)
                    response.raise_for_status()

                    # Save to temp file
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".mindpack") as tmp_file:
                        tmp_file.write(response.content)
                        tmp_path = Path(tmp_file.name)

                    try:
                        # Install using existing CapabilityInstaller
                        success, result = installer.install_from_mindpack(tmp_path, validate=True)

                        if success:
                            installed_packs.append({
                                "pack_code": pack_code,
                                "version": result.get("version", "unknown"),
                                "status": "installed"
                            })
                        else:
                            errors.append({
                                "pack_code": pack_code,
                                "error": "; ".join(result.get("errors", []))
                            })
                    finally:
                        # Clean up temp file
                        if tmp_path.exists():
                            tmp_path.unlink()
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
            action_required = _parse_action_required(catalog)
            return {
                "action_required": action_required.dict() if action_required else None,
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
        # ⚠️ Hard Rule: This is Provider Contract, not site-hub specific
        catalog = await _get_packs_catalog(provider)

        if isinstance(catalog, dict) and catalog.get("state") == "ACTION_REQUIRED":
            action_required = _parse_action_required(catalog)
            return action_required.dict() if action_required else {
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


async def _get_packs_catalog(provider, bundle: str = "default") -> Dict:
    """
    Get packs catalog from provider API

    ⚠️ Hard Rule: local-core backend calls provider API (not site-hub directly)
    Returns neutral Provider Contract format (actions[] instead of purchase_url)
    """
    import httpx

    api_url = provider.get_api_url() if hasattr(provider, 'get_api_url') else None
    api_key = provider.get_api_key() if hasattr(provider, 'get_api_key') else None

    if not api_url:
        raise ValueError("Provider API URL not configured")

    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(
                f"{api_url}/v1/packs",
                params={"bundle": bundle},
                headers=headers
            )

            if response.status_code == 403:
                # Check if response contains neutral Provider Contract format
                error_data = response.json()
                # Support both old format (backward compatibility) and new format
                if error_data.get("state") == "ACTION_REQUIRED" or error_data.get("error") == "ENTITLEMENT_REQUIRED":
                    # Convert old format to new format if needed
                    if "actions" in error_data:
                        return error_data  # Already in new format
                    elif "purchase_url" in error_data:
                        # Convert old format to new format
                        return {
                            "state": "ACTION_REQUIRED",
                            "reason": error_data.get("error", "ENTITLEMENT_REQUIRED"),
                            "actions": [
                                {
                                    "type": "BROWSER_AUTH",
                                    "label": "Login / Purchase",
                                    "rel": "purchase",
                                    "url": error_data.get("purchase_url"),
                                    "expires_at": None
                                }
                            ],
                            "retry_after_sec": 5
                        }
                    else:
                        return {
                            "state": "ACTION_REQUIRED",
                            "reason": error_data.get("error", "ENTITLEMENT_REQUIRED"),
                            "actions": [],
                            "retry_after_sec": 5
                        }

            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                error_data = e.response.json()
                # Convert old format to new format if needed
                if "actions" in error_data:
                    return error_data
                elif "purchase_url" in error_data:
                    return {
                        "state": "ACTION_REQUIRED",
                        "reason": error_data.get("error", "ENTITLEMENT_REQUIRED"),
                        "actions": [
                            {
                                "type": "BROWSER_AUTH",
                                "label": "Login / Purchase",
                                "rel": "purchase",
                                "url": error_data.get("purchase_url"),
                                "expires_at": None
                            }
                        ],
                        "retry_after_sec": 5
                    }
            raise


def _parse_action_required(data: Dict) -> Optional[ProviderActionRequired]:
    """
    Parse action_required from provider response (neutral Provider Contract)
    """
    if not isinstance(data, dict) or data.get("state") != "ACTION_REQUIRED":
        return None

    actions = []
    for action_data in data.get("actions", []):
        if isinstance(action_data, dict):
            actions.append(ProviderAction(
                type=action_data.get("type", "BROWSER_AUTH"),
                label=action_data.get("label", "Action"),
                rel=action_data.get("rel", "purchase"),
                url=action_data.get("url", ""),
                expires_at=action_data.get("expires_at")
            ))

    return ProviderActionRequired(
        state=data.get("state", "ACTION_REQUIRED"),
        reason=data.get("reason", "UNKNOWN"),
        actions=actions,
        retry_after_sec=data.get("retry_after_sec")
    )




def _create_provider_instance(
    provider_id: str,
    provider_type: str,
    config: Dict[str, Any],
    settings_store: SystemSettingsStore
):
    """
    Create a provider instance from configuration

    Returns:
        CloudProvider instance or None if type is not supported
    """
    try:
        if provider_type == "official":
            return OfficialCloudProvider(
                api_url=config.get("api_url"),
                license_key=config.get("license_key"),
                settings_store=settings_store
            )
        elif provider_type == "generic_http":
            return GenericHttpProvider(
                provider_id=provider_id,
                provider_name=config.get("name", provider_id),
                api_url=config.get("api_url"),
                auth_config=config.get("auth", {})
            )
        else:
            logger.warning(f"Provider type '{provider_type}' not supported for instantiation")
            return None
    except Exception as e:
        logger.error(f"Failed to create provider instance: {e}", exc_info=True)
        return None

