"""
Cloud Asset Manager
Unified interface for asset retrieval with cache-first strategy and background updates
"""

import asyncio
import logging
from typing import Optional, Dict, Any, List
from pathlib import Path

from .cache_store import CacheStore, CacheLifecycleManager, CacheLifecycle
from .asset_fetcher import AssetFetcher
from .flow_loader import FlowLoader
from .playbook_loader import PlaybookLoader
from .schema_loader import SchemaLoader
from .offline_mode import OfflineModeManager

logger = logging.getLogger(__name__)


class CloudAssetManager:
    """Unified asset manager with cache-first strategy"""

    def __init__(
        self,
        cache_store: CacheStore,
        asset_fetcher: AssetFetcher,
        offline_mode_manager: Optional[OfflineModeManager] = None,
    ):
        """
        Initialize cloud asset manager

        Args:
            cache_store: CacheStore instance
            asset_fetcher: AssetFetcher instance
            offline_mode_manager: OfflineModeManager instance (optional)
        """
        self.cache_store = cache_store
        self.asset_fetcher = asset_fetcher
        self.offline_mode_manager = offline_mode_manager

        lifecycle_manager = CacheLifecycleManager(cache_store)

        self.flow_loader = FlowLoader(cache_store, asset_fetcher, lifecycle_manager)
        self.playbook_loader = PlaybookLoader(cache_store, asset_fetcher, lifecycle_manager)
        self.schema_loader = SchemaLoader(cache_store, asset_fetcher, lifecycle_manager)

        self._background_update_tasks: List[asyncio.Task] = []

    async def get_flow(
        self,
        flow_uri: str,
        version: Optional[str] = None,
        force_refresh: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """
        Get flow definition

        Args:
            flow_uri: Flow URI
            version: Specific version (optional)
            force_refresh: Force refresh from cloud

        Returns:
            Flow definition dict or None
        """
        if force_refresh and self.offline_mode_manager and not self.offline_mode_manager.is_offline():
            await self.asset_fetcher.fetch_asset(flow_uri, force_refresh=True)

        return await self.flow_loader.load_flow_async(flow_uri, version, force_refresh)

    async def get_playbook(
        self,
        playbook_uri: str,
        locale: str = "zh-TW",
        version: Optional[str] = None,
        force_refresh: bool = False,
    ) -> Optional[str]:
        """
        Get playbook content

        Args:
            playbook_uri: Playbook URI
            locale: Language locale
            version: Specific version (optional)
            force_refresh: Force refresh from cloud

        Returns:
            Playbook content as string or None
        """
        if force_refresh and self.offline_mode_manager and not self.offline_mode_manager.is_offline():
            await self.asset_fetcher.fetch_asset(playbook_uri, force_refresh=True)

        return await self.playbook_loader.load_playbook_async(playbook_uri, locale, version, force_refresh)

    async def get_schema(
        self,
        schema_uri: str,
        version: Optional[str] = None,
        force_refresh: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """
        Get schema definition

        Args:
            schema_uri: Schema URI
            version: Specific version (optional)
            force_refresh: Force refresh from cloud

        Returns:
            JSON Schema dict or None
        """
        if force_refresh and self.offline_mode_manager and not self.offline_mode_manager.is_offline():
            await self.asset_fetcher.fetch_asset(schema_uri, force_refresh=True)

        return await self.schema_loader.load_schema_async(schema_uri, version, force_refresh)

    def get_flow_sync(
        self,
        flow_uri: str,
        version: Optional[str] = None,
        force_refresh: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """Synchronous version of get_flow"""
        return self.flow_loader.load_flow(flow_uri, version, force_refresh)

    def get_playbook_sync(
        self,
        playbook_uri: str,
        locale: str = "zh-TW",
        version: Optional[str] = None,
        force_refresh: bool = False,
    ) -> Optional[str]:
        """Synchronous version of get_playbook"""
        return self.playbook_loader.load_playbook(playbook_uri, locale, version, force_refresh)

    def get_schema_sync(
        self,
        schema_uri: str,
        version: Optional[str] = None,
        force_refresh: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """Synchronous version of get_schema"""
        return self.schema_loader.load_schema(schema_uri, version, force_refresh)

    async def check_and_update_assets(
        self,
        asset_uris: List[str],
        background: bool = True,
    ) -> Dict[str, bool]:
        """
        Check asset versions and update if needed

        Args:
            asset_uris: List of asset URIs to check
            background: Run updates in background

        Returns:
            Dictionary mapping asset URIs to update status
        """
        results = {}

        for asset_uri in asset_uris:
            metadata = self.cache_store.get_asset_metadata(asset_uri)
            if not metadata:
                results[asset_uri] = False
                continue

            status = CacheLifecycleManager(self.cache_store).get_asset_status(asset_uri)

            if status == CacheLifecycle.EXPIRED:
                if background:
                    task = asyncio.create_task(
                        self._update_asset_background(asset_uri)
                    )
                    self._background_update_tasks.append(task)
                    results[asset_uri] = True
                else:
                    try:
                        await self.asset_fetcher.fetch_asset(asset_uri, force_refresh=True)
                        results[asset_uri] = True
                    except Exception as e:
                        logger.error(f"Failed to update asset {asset_uri}: {e}")
                        results[asset_uri] = False
            else:
                results[asset_uri] = False

        return results

    async def _update_asset_background(self, asset_uri: str):
        """Update asset in background"""
        try:
            await self.asset_fetcher.fetch_asset(asset_uri, force_refresh=True)
            logger.info(f"Background update completed for {asset_uri}")
        except Exception as e:
            logger.error(f"Background update failed for {asset_uri}: {e}")

    def is_asset_cached(self, asset_uri: str, version: Optional[str] = None) -> bool:
        """
        Check if asset is cached

        Args:
            asset_uri: Asset URI
            version: Specific version (optional)

        Returns:
            True if asset is cached
        """
        if version:
            full_uri = f"{asset_uri}@{version}" if "@" not in asset_uri else asset_uri
        else:
            full_uri = asset_uri

        asset_path = self.cache_store.get_asset_path(full_uri)
        return asset_path.exists()

    def get_asset_status(self, asset_uri: str) -> CacheLifecycle:
        """
        Get asset cache status

        Args:
            asset_uri: Asset URI

        Returns:
            Cache lifecycle status
        """
        lifecycle_manager = CacheLifecycleManager(self.cache_store)
        return lifecycle_manager.get_asset_status(asset_uri)

    def clear_cache(self, asset_uri: Optional[str] = None):
        """
        Clear asset cache

        Args:
            asset_uri: Specific asset URI to clear (None to clear all)
        """
        if asset_uri:
            self.cache_store.clear_asset(asset_uri)
            self.flow_loader.clear_cache(asset_uri)
        else:
            cleared = self.cache_store.clear_expired_assets()
            logger.info(f"Cleared {cleared} expired assets")

