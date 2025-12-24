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


class TestConnectionResponse(BaseModel):
    """Test connection response model"""
    success: bool
    message: str


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
    """
    try:
        success, message = await cloud_manager.test_provider_connection(provider_id)
        return {
            "success": success,
            "message": message
        }
    except Exception as e:
        logger.error(f"Failed to test provider connection: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to test connection: {str(e)}")


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

