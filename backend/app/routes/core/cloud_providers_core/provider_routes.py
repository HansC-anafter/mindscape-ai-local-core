from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.models.system_settings import SettingType
from backend.app.services.cloud_extension_manager import CloudExtensionManager
from backend.app.services.system_settings_store import SystemSettingsStore

from .dependencies import get_cloud_manager, get_settings_store
from .helpers import (
    build_provider_response,
    create_provider_instance,
    get_provider_settings,
)
from .schemas import ProviderConfig, ProviderResponse
from .state import logger

router = APIRouter(prefix="/api/v1/cloud-providers", tags=["cloud-providers"])

@router.get("", response_model=List[ProviderResponse])
async def list_providers(
    settings_store: SystemSettingsStore = Depends(get_settings_store),
    cloud_manager: CloudExtensionManager = Depends(get_cloud_manager)
):
    """
    List all configured cloud providers
    """
    try:
        providers_config = get_provider_settings(settings_store, logger)

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
            result.append(
                build_provider_response(
                    provider_id=provider_id,
                    provider_type=provider_type,
                    enabled=enabled,
                    config=config,
                    provider=provider,
                )
            )

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
            # Note: "official" is deprecated but still supported for backward compatibility
            raise HTTPException(
                status_code=400,
                detail=f"Invalid provider type: {provider.provider_type}"
            )

        # Create provider instance to validate configuration
        provider_instance = create_provider_instance(
            provider.provider_id,
            provider.provider_type,
            provider.config,
            logger,
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

        providers_config = settings_store.get("cloud_providers") or []

        # Find and update provider
        found = False
        for i, existing in enumerate(providers_config):
            if existing.get("provider_id") == provider_id:
                # Unregister old provider
                old_provider = cloud_manager.get_provider(provider_id)
                if old_provider:
                    cloud_manager.unregister_provider(provider_id)

                # Create new provider instance
                provider_instance = create_provider_instance(
                    provider.provider_id,
                    provider.provider_type,
                    provider.config,
                    logger,
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
        providers_config = settings_store.get("cloud_providers") or []

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
