from fastapi import HTTPException

from backend.app.services.cloud_extension_manager import CloudExtensionManager
from backend.app.services.system_settings_store import SystemSettingsStore

from .helpers import sync_enabled_providers
from .state import logger


def get_settings_store() -> SystemSettingsStore:
    """Dependency to get settings store."""
    return SystemSettingsStore()


def get_cloud_manager() -> CloudExtensionManager:
    """Dependency to get cloud extension manager."""
    try:
        manager = CloudExtensionManager.instance()
        settings_store = SystemSettingsStore()
        sync_enabled_providers(
            manager=manager,
            settings_store=settings_store,
            logger=logger,
        )
        return manager
    except Exception as exc:
        logger.error(
            "Failed to get cloud extension manager: %s",
            exc,
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to initialize cloud extension manager: {str(exc)}",
        )
