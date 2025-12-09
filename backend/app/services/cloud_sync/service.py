"""
Cloud Sync Service
Main service class that initializes and manages all cloud sync components
"""

import os
import logging
from typing import Optional
from pathlib import Path

from .cache_store import CacheStore, CacheLifecycleManager
from .sync_client import SyncClient, VersionChecker
from .asset_fetcher import AssetFetcher
from .offline_mode import ConnectivityMonitor, OfflineModeManager
from .flow_loader import FlowLoader
from .playbook_loader import PlaybookLoader
from .schema_loader import SchemaLoader
from .asset_manager import CloudAssetManager
from .instance_store import InstanceStore
from .instance_syncer import InstanceSyncer
from .offline_changes import OfflineChangeTracker

logger = logging.getLogger(__name__)


class CloudSyncService:
    """Main cloud sync service that manages all sync components"""

    def __init__(
        self,
        cache_root: Optional[Path] = None,
        instances_root: Optional[Path] = None,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        auto_start: bool = True,
    ):
        """
        Initialize cloud sync service

        Args:
            cache_root: Cache root directory (defaults to ~/.mindscape/cache)
            instances_root: Instances root directory (defaults to ~/.mindscape/instances)
            base_url: Cloud API base URL (defaults to CLOUD_SYNC_BASE_URL env var)
            api_key: API key (defaults to CLOUD_SYNC_API_KEY env var)
            auto_start: Automatically start connectivity monitoring
        """
        self.cache_store = CacheStore(cache_root)
        self.instance_store = InstanceStore(instances_root)

        self.sync_client = SyncClient(base_url=base_url, api_key=api_key)
        self.version_checker = VersionChecker(self.sync_client)

        self.asset_fetcher = AssetFetcher(
            sync_client=self.sync_client,
            cache_store=self.cache_store,
        )

        self.connectivity_monitor = ConnectivityMonitor()
        self.offline_mode_manager = OfflineModeManager(self.connectivity_monitor)

        self.asset_manager = CloudAssetManager(
            cache_store=self.cache_store,
            asset_fetcher=self.asset_fetcher,
            offline_mode_manager=self.offline_mode_manager,
        )

        self.instance_syncer = InstanceSyncer(
            instance_store=self.instance_store,
            sync_client=self.sync_client,
            offline_mode_manager=self.offline_mode_manager,
        )

        self.offline_change_tracker = OfflineChangeTracker(
            instance_store=self.instance_store,
            instance_syncer=self.instance_syncer,
        )

        if auto_start and self.sync_client.is_configured():
            self.connectivity_monitor.start_monitoring()

        logger.info("CloudSyncService initialized")

    def is_configured(self) -> bool:
        """Check if service is properly configured"""
        return self.sync_client.is_configured()

    def is_online(self) -> bool:
        """Check if currently online"""
        return self.connectivity_monitor.is_online()

    async def check_updates(
        self,
        client_version: str,
        capabilities: list,
        assets: list,
        license_id: Optional[str] = None,
        device_id: Optional[str] = None,
    ):
        """Check for available updates"""
        if not self.is_configured():
            return None

        try:
            return await self.version_checker.check_updates(
                client_version=client_version,
                capabilities=capabilities,
                assets=assets,
                license_id=license_id,
                device_id=device_id,
            )
        except Exception as e:
            logger.error(f"Failed to check updates: {e}")
            return None

    async def sync_pending_changes(self):
        """Sync all pending changes"""
        if not self.is_online():
            logger.warning("Cannot sync: offline mode")
            return

        try:
            result = await self.offline_change_tracker.replay_all_changes()
            logger.info(f"Synced pending changes: {result}")
            return result
        except Exception as e:
            logger.error(f"Failed to sync pending changes: {e}")
            return None

    def cleanup_expired_cache(self):
        """Clean up expired cache entries"""
        try:
            result = self.cache_store.clear_expired_assets()
            logger.info(f"Cleaned up {result} expired assets")
            return result
        except Exception as e:
            logger.error(f"Failed to cleanup expired cache: {e}")
            return 0

    def stop(self):
        """Stop the service and cleanup"""
        self.connectivity_monitor.stop_monitoring()
        logger.info("CloudSyncService stopped")


# Global service instance
_cloud_sync_service: Optional[CloudSyncService] = None


def get_cloud_sync_service() -> Optional[CloudSyncService]:
    """Get global cloud sync service instance"""
    return _cloud_sync_service


def initialize_cloud_sync_service(
    cache_root: Optional[Path] = None,
    instances_root: Optional[Path] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    auto_start: bool = True,
) -> CloudSyncService:
    """
    Initialize global cloud sync service

    Args:
        cache_root: Cache root directory
        instances_root: Instances root directory
        base_url: Cloud API base URL
        api_key: API key
        auto_start: Automatically start connectivity monitoring

    Returns:
        Initialized CloudSyncService instance
    """
    global _cloud_sync_service

    if _cloud_sync_service is None:
        _cloud_sync_service = CloudSyncService(
            cache_root=cache_root,
            instances_root=instances_root,
            base_url=base_url,
            api_key=api_key,
            auto_start=auto_start,
        )

    return _cloud_sync_service

