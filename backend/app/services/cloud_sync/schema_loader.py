"""
Schema Loader
Loads JSON Schema definitions from cache with version compatibility checking
"""

import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any

from .cache_store import CacheStore, CacheLifecycleManager
from .asset_fetcher import AssetFetcher

logger = logging.getLogger(__name__)

try:
    from packaging import version as pkg_version
    PACKAGING_AVAILABLE = True
except ImportError:
    PACKAGING_AVAILABLE = False
    logger.warning("packaging module not available, version compatibility checking will be limited")


class SchemaLoader:
    """Loads JSON Schema definitions from cache"""

    def __init__(
        self,
        cache_store: CacheStore,
        asset_fetcher: Optional[AssetFetcher] = None,
        lifecycle_manager: Optional[CacheLifecycleManager] = None,
    ):
        """
        Initialize schema loader

        Args:
            cache_store: CacheStore instance
            asset_fetcher: AssetFetcher instance (optional, for fetching missing schemas)
            lifecycle_manager: CacheLifecycleManager instance (optional)
        """
        self.cache_store = cache_store
        self.asset_fetcher = asset_fetcher
        self.lifecycle_manager = lifecycle_manager or CacheLifecycleManager(cache_store)

    def load_schema(
        self,
        schema_uri: str,
        version: Optional[str] = None,
        force_refresh: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """
        Load schema from cache

        Args:
            schema_uri: Schema URI (with or without version)
            version: Specific version to load (optional)
            force_refresh: Force refresh from cache

        Returns:
            JSON Schema dict or None if not found
        """
        if version:
            full_uri = f"{schema_uri}@{version}" if "@" not in schema_uri else schema_uri
        else:
            full_uri = schema_uri

        asset_path = self.cache_store.get_asset_path(full_uri)
        schema_file = asset_path / "asset.json"

        if not schema_file.exists():
            if self.asset_fetcher:
                logger.info(f"Schema not in cache, fetching: {full_uri}")
                import asyncio
                try:
                    asyncio.run(self.asset_fetcher.fetch_asset(full_uri, force_refresh=True))
                    schema_file = self.cache_store.get_asset_path(full_uri) / "asset.json"
                except Exception as e:
                    logger.error(f"Failed to fetch schema {full_uri}: {e}")
                    return None
            else:
                logger.warning(f"Schema not found in cache: {full_uri}")
                return None

        try:
            with open(schema_file, "r", encoding="utf-8") as f:
                schema_data = json.load(f)

            if not schema_data:
                logger.warning(f"Empty schema data for {full_uri}")
                return None

            return schema_data

        except Exception as e:
            logger.error(f"Failed to load schema {full_uri}: {e}")
            return None

    async def load_schema_async(
        self,
        schema_uri: str,
        version: Optional[str] = None,
        force_refresh: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """
        Load schema from cache (async version)

        Args:
            schema_uri: Schema URI (with or without version)
            version: Specific version to load (optional)
            force_refresh: Force refresh from cache

        Returns:
            JSON Schema dict or None if not found
        """
        if version:
            full_uri = f"{schema_uri}@{version}" if "@" not in schema_uri else schema_uri
        else:
            full_uri = schema_uri

        asset_path = self.cache_store.get_asset_path(full_uri)
        schema_file = asset_path / "asset.json"

        if not schema_file.exists():
            if self.asset_fetcher:
                logger.info(f"Schema not in cache, fetching: {full_uri}")
                try:
                    await self.asset_fetcher.fetch_asset(full_uri, force_refresh=True)
                    schema_file = self.cache_store.get_asset_path(full_uri) / "asset.json"
                except Exception as e:
                    logger.error(f"Failed to fetch schema {full_uri}: {e}")
                    return None
            else:
                logger.warning(f"Schema not found in cache: {full_uri}")
                return None

        try:
            with open(schema_file, "r", encoding="utf-8") as f:
                schema_data = json.load(f)

            if not schema_data:
                logger.warning(f"Empty schema data for {full_uri}")
                return None

            return schema_data

        except Exception as e:
            logger.error(f"Failed to load schema {full_uri}: {e}")
            return None

    def check_version_compatibility(
        self,
        schema_uri: str,
        required_version: str,
        cached_version: Optional[str] = None,
    ) -> bool:
        """
        Check if cached schema version is compatible with required version

        Args:
            schema_uri: Schema URI
            required_version: Required version (SemVer format)
            cached_version: Cached version (optional, will be fetched if not provided)

        Returns:
            True if versions are compatible
        """
        if cached_version is None:
            metadata = self.cache_store.get_asset_metadata(schema_uri)
            if metadata:
                uri = metadata.get("uri", schema_uri)
                if "@" in uri:
                    cached_version = uri.split("@")[-1]
                else:
                    return False
            else:
                return False

        if not PACKAGING_AVAILABLE:
            return required_version == cached_version

        try:
            req_ver = pkg_version.parse(required_version)
            cached_ver = pkg_version.parse(cached_version)

            if req_ver.major != cached_ver.major:
                return False

            if req_ver.major == cached_ver.major:
                if req_ver.minor > cached_ver.minor:
                    return False

            return True

        except Exception as e:
            logger.error(f"Failed to check version compatibility: {e}")
            return False

    def is_schema_cached(self, schema_uri: str, version: Optional[str] = None) -> bool:
        """
        Check if schema is cached

        Args:
            schema_uri: Schema URI
            version: Specific version (optional)

        Returns:
            True if schema is cached
        """
        if version:
            full_uri = f"{schema_uri}@{version}" if "@" not in schema_uri else schema_uri
        else:
            full_uri = schema_uri

        asset_path = self.cache_store.get_asset_path(full_uri)
        schema_file = asset_path / "asset.json"
        return schema_file.exists()

