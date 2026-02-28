"""
Shared state/helpers for playbook route modules.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from ....services.mindscape_store import MindscapeStore
from ....services.playbook_service import PlaybookService
from ....services.stores.workspace_pinned_playbooks_store import (
    WorkspacePinnedPlaybooksStore,
)

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    """Return timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def _init_cloud_extension_manager() -> Optional[Any]:
    """
    Initialize cloud extension manager and register providers from settings.

    Returns None if cloud extension modules are unavailable.
    """
    cloud_extension_manager = None
    try:
        from ....services.cloud_extension_manager import CloudExtensionManager
        from ....services.cloud_providers.generic_http import GenericHttpProvider
        from ....services.system_settings_store import SystemSettingsStore

        settings_store = SystemSettingsStore()
        _migrate_cloud_settings(settings_store)

        cloud_extension_manager = CloudExtensionManager.instance()

        try:
            providers_config = settings_store.get("cloud_providers", default=[])

            if providers_config:
                logger.info(
                    "Loading %d cloud providers from settings", len(providers_config)
                )

                for provider_config in providers_config:
                    if not provider_config.get("enabled", False):
                        continue

                    provider_id = provider_config.get("provider_id")
                    provider_type = provider_config.get("provider_type")
                    config = provider_config.get("config", {})

                    try:
                        if provider_type != "generic_http":
                            logger.warning(
                                "Unknown provider type: %s, skipping", provider_type
                            )
                            continue

                        auth_config = config.get("auth", {})
                        if not auth_config:
                            logger.warning(
                                "Provider %s: missing auth configuration, skipping",
                                provider_id,
                            )
                            continue

                        provider = GenericHttpProvider(
                            provider_id=provider_id,
                            provider_name=config.get("name", provider_id),
                            api_url=config.get("api_url"),
                            auth_config=auth_config,
                            api_path_template=config.get(
                                "api_path_template",
                                "/api/v1/playbooks/{capability_code}/{playbook_code}",
                            ),
                            pack_download_path=config.get("pack_download_path"),
                        )
                        cloud_extension_manager.register_provider(provider)
                        logger.info(
                            "Registered cloud provider: %s (%s)",
                            provider_id,
                            provider_type,
                        )
                    except Exception as e:  # pragma: no cover - defensive
                        logger.error(
                            "Failed to register provider %s: %s",
                            provider_id,
                            e,
                            exc_info=True,
                        )
            else:
                logger.debug("No cloud providers configured")
        except Exception as e:  # pragma: no cover - defensive
            logger.warning(
                "Failed to load cloud providers from settings: %s",
                e,
                exc_info=True,
            )

    except ImportError:
        logger.debug(
            "Cloud Extension Manager not available "
            "(httpx not installed or module missing)"
        )
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("Failed to initialize Cloud Extension Manager: %s", e)

    return cloud_extension_manager


def _migrate_cloud_settings(settings_store: Any) -> None:
    """Migrate legacy cloud settings into cloud_providers array."""
    try:
        providers_config = settings_store.get("cloud_providers", default=[])
        if providers_config:
            return

        old_api_url = settings_store.get("cloud_api_url", default="")
        old_license_key = settings_store.get("cloud_license_key", default="")
        old_enabled = settings_store.get("cloud_enabled", default=False)

        if old_api_url and old_license_key and old_enabled:
            logger.info(
                "Migrating cloud settings from old format to cloud_providers array"
            )
            new_provider: Dict[str, Any] = {
                "provider_id": "mindscape_official",
                "provider_type": "generic_http",
                "enabled": True,
                "config": {
                    "api_url": old_api_url,
                    "name": "Mindscape AI Cloud",
                    "auth": {"auth_type": "api_key", "api_key": old_license_key},
                },
            }
            settings_store.set("cloud_providers", [new_provider])
            logger.info("Cloud settings migrated successfully")
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("Failed to migrate cloud settings: %s", e, exc_info=True)


mindscape_store = MindscapeStore()
executions_store = mindscape_store.playbook_executions
pinned_playbooks_store = WorkspacePinnedPlaybooksStore(mindscape_store.db_path)
cloud_extension_manager = _init_cloud_extension_manager()
playbook_service = PlaybookService(
    store=mindscape_store, cloud_extension_manager=cloud_extension_manager
)

