"""
Flow Loader
Loads Flow definitions from cache with version resolution and hot reload support
"""

import yaml
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)

from .cache_store import CacheStore, CacheLifecycleManager
from .asset_fetcher import AssetFetcher

logger = logging.getLogger(__name__)


class FlowLoader:
    """Loads Flow definitions from cache"""

    def __init__(
        self,
        cache_store: CacheStore,
        asset_fetcher: Optional[AssetFetcher] = None,
        lifecycle_manager: Optional[CacheLifecycleManager] = None,
    ):
        """
        Initialize flow loader

        Args:
            cache_store: CacheStore instance
            asset_fetcher: AssetFetcher instance (optional, for fetching missing flows)
            lifecycle_manager: CacheLifecycleManager instance (optional)
        """
        self.cache_store = cache_store
        self.asset_fetcher = asset_fetcher
        self.lifecycle_manager = lifecycle_manager or CacheLifecycleManager(cache_store)
        self._loaded_flows: Dict[str, Dict[str, Any]] = {}
        self._load_timestamps: Dict[str, datetime] = {}

    def load_flow(
        self,
        flow_uri: str,
        version: Optional[str] = None,
        force_refresh: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """
        Load flow from cache

        Args:
            flow_uri: Flow URI (with or without version)
            version: Specific version to load (optional)
            force_refresh: Force refresh from cache

        Returns:
            Flow definition dict or None if not found
        """
        if version:
            full_uri = f"{flow_uri}@{version}" if "@" not in flow_uri else flow_uri
        else:
            full_uri = flow_uri

        if not force_refresh and full_uri in self._loaded_flows:
            return self._loaded_flows[full_uri]

        asset_path = self.cache_store.get_asset_path(full_uri)
        flow_file = asset_path / "asset.yaml"

        if not flow_file.exists():
            if self.asset_fetcher:
                logger.info(f"Flow not in cache, fetching: {full_uri}")
                import asyncio
                try:
                    asyncio.run(self.asset_fetcher.fetch_asset(full_uri, force_refresh=True))
                    flow_file = self.cache_store.get_asset_path(full_uri) / "asset.yaml"
                except Exception as e:
                    logger.error(f"Failed to fetch flow {full_uri}: {e}")
                    return None
            else:
                logger.warning(f"Flow not found in cache: {full_uri}")
                return None

        try:
            with open(flow_file, "r", encoding="utf-8") as f:
                flow_data = yaml.safe_load(f)

            if not flow_data:
                logger.warning(f"Empty flow data for {full_uri}")
                return None

            metadata = self.cache_store.get_asset_metadata(full_uri)
            if metadata:
                flow_data["_metadata"] = {
                    "uri": full_uri,
                    "cached_at": metadata.get("cached_at"),
                    "expires_at": metadata.get("expires_at"),
                    "version": self._extract_version(full_uri),
                }

            self._loaded_flows[full_uri] = flow_data
            self._load_timestamps[full_uri] = _utc_now()

            return flow_data

        except Exception as e:
            logger.error(f"Failed to load flow {full_uri}: {e}")
            return None

    async def load_flow_async(
        self,
        flow_uri: str,
        version: Optional[str] = None,
        force_refresh: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """
        Load flow from cache (async version)

        Args:
            flow_uri: Flow URI (with or without version)
            version: Specific version to load (optional)
            force_refresh: Force refresh from cache

        Returns:
            Flow definition dict or None if not found
        """
        if version:
            full_uri = f"{flow_uri}@{version}" if "@" not in flow_uri else flow_uri
        else:
            full_uri = flow_uri

        if not force_refresh and full_uri in self._loaded_flows:
            return self._loaded_flows[full_uri]

        asset_path = self.cache_store.get_asset_path(full_uri)
        flow_file = asset_path / "asset.yaml"

        if not flow_file.exists():
            if self.asset_fetcher:
                logger.info(f"Flow not in cache, fetching: {full_uri}")
                try:
                    await self.asset_fetcher.fetch_asset(full_uri, force_refresh=True)
                    flow_file = self.cache_store.get_asset_path(full_uri) / "asset.yaml"
                except Exception as e:
                    logger.error(f"Failed to fetch flow {full_uri}: {e}")
                    return None
            else:
                logger.warning(f"Flow not found in cache: {full_uri}")
                return None

        try:
            with open(flow_file, "r", encoding="utf-8") as f:
                flow_data = yaml.safe_load(f)

            if not flow_data:
                logger.warning(f"Empty flow data for {full_uri}")
                return None

            metadata = self.cache_store.get_asset_metadata(full_uri)
            if metadata:
                flow_data["_metadata"] = {
                    "uri": full_uri,
                    "cached_at": metadata.get("cached_at"),
                    "expires_at": metadata.get("expires_at"),
                    "version": self._extract_version(full_uri),
                }

            self._loaded_flows[full_uri] = flow_data
            self._load_timestamps[full_uri] = _utc_now()

            return flow_data

        except Exception as e:
            logger.error(f"Failed to load flow {full_uri}: {e}")
            return None

    def reload_flow(self, flow_uri: str) -> Optional[Dict[str, Any]]:
        """
        Reload flow from cache (hot reload)

        Args:
            flow_uri: Flow URI

        Returns:
            Reloaded flow definition dict or None if not found
        """
        if "@" in flow_uri:
            full_uri = flow_uri
        else:
            full_uri = flow_uri

        if full_uri in self._loaded_flows:
            del self._loaded_flows[full_uri]
            if full_uri in self._load_timestamps:
                del self._load_timestamps[full_uri]

        return self.load_flow(full_uri, force_refresh=True)

    def get_flow_version(self, flow_uri: str) -> Optional[str]:
        """
        Get version of cached flow

        Args:
            flow_uri: Flow URI (without version)

        Returns:
            Version string or None if not found
        """
        metadata = self.cache_store.get_asset_metadata(flow_uri)
        if metadata:
            return self._extract_version(metadata.get("uri", flow_uri))
        return None

    def is_flow_cached(self, flow_uri: str, version: Optional[str] = None) -> bool:
        """
        Check if flow is cached

        Args:
            flow_uri: Flow URI
            version: Specific version (optional)

        Returns:
            True if flow is cached
        """
        if version:
            full_uri = f"{flow_uri}@{version}" if "@" not in flow_uri else flow_uri
        else:
            full_uri = flow_uri

        asset_path = self.cache_store.get_asset_path(full_uri)
        flow_file = asset_path / "asset.yaml"
        return flow_file.exists()

    def _extract_version(self, uri: str) -> Optional[str]:
        """Extract version from URI"""
        if "@" in uri:
            return uri.split("@")[-1]
        return None

    def clear_cache(self, flow_uri: Optional[str] = None):
        """
        Clear loaded flow cache

        Args:
            flow_uri: Specific flow URI to clear (None to clear all)
        """
        if flow_uri:
            if flow_uri in self._loaded_flows:
                del self._loaded_flows[flow_uri]
            if flow_uri in self._load_timestamps:
                del self._load_timestamps[flow_uri]
        else:
            self._loaded_flows.clear()
            self._load_timestamps.clear()

