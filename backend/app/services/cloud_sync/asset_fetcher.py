"""
Asset Fetcher
Fetches assets from cloud and stores them in local cache
"""

import base64
import hashlib
import json
import logging
from typing import Optional, Dict, Any, List
from pathlib import Path

from .cache_store import CacheStore, CacheLifecycleManager
from .sync_client import SyncClient, NetworkError

logger = logging.getLogger(__name__)


class AssetFetcher:
    """Fetches assets from cloud and manages local cache"""

    def __init__(
        self,
        sync_client: SyncClient,
        cache_store: CacheStore,
        lifecycle_manager: Optional[CacheLifecycleManager] = None,
    ):
        """
        Initialize asset fetcher

        Args:
            sync_client: SyncClient instance
            cache_store: CacheStore instance
            lifecycle_manager: CacheLifecycleManager instance (optional)
        """
        self.sync_client = sync_client
        self.cache_store = cache_store
        self.lifecycle_manager = lifecycle_manager or CacheLifecycleManager(cache_store)

    async def fetch_asset(
        self,
        asset_uri: str,
        force_refresh: bool = False,
    ) -> Optional[Path]:
        """
        Fetch single asset from cloud

        Args:
            asset_uri: Asset URI
            force_refresh: Force refresh even if cached

        Returns:
            Path to cached asset file, or None if fetch failed
        """
        if not force_refresh:
            cached_content = self.cache_store.get_asset(asset_uri)
            if cached_content is not None:
                status = self.lifecycle_manager.get_asset_status(asset_uri)
                if status.value in ["valid", "stale"]:
                    logger.debug(f"Using cached asset: {asset_uri}")
                    return self.cache_store.get_asset_path(asset_uri)

        try:
            response = await self.sync_client.fetch_assets([asset_uri])
            assets = response.get("assets", [])

            if not assets:
                logger.warning(f"No asset returned for {asset_uri}")
                return None

            asset_data = assets[0]
            return await self._store_asset(asset_data)

        except NetworkError as e:
            logger.error(f"Failed to fetch asset {asset_uri}: {e}")
            cached_content = self.cache_store.get_asset(asset_uri)
            if cached_content is not None:
                logger.warning(f"Using cached asset despite fetch failure: {asset_uri}")
                return self.cache_store.get_asset_path(asset_uri)
            return None

    async def fetch_assets(
        self,
        asset_uris: List[str],
        force_refresh: bool = False,
    ) -> Dict[str, Optional[Path]]:
        """
        Fetch multiple assets from cloud

        Args:
            asset_uris: List of asset URIs
            force_refresh: Force refresh even if cached

        Returns:
            Dictionary mapping asset URIs to cached file paths
        """
        results = {}

        if not force_refresh:
            for asset_uri in asset_uris:
                cached_content = self.cache_store.get_asset(asset_uri)
                if cached_content is not None:
                    status = self.lifecycle_manager.get_asset_status(asset_uri)
                    if status.value in ["valid", "stale"]:
                        results[asset_uri] = self.cache_store.get_asset_path(asset_uri)

        uris_to_fetch = [uri for uri in asset_uris if uri not in results]

        if not uris_to_fetch:
            return results

        try:
            response = await self.sync_client.fetch_assets(uris_to_fetch)
            assets = response.get("assets", [])

            for asset_data in assets:
                asset_uri = asset_data.get("uri")
                if asset_uri:
                    try:
                        asset_path = await self._store_asset(asset_data)
                        results[asset_uri] = asset_path
                    except Exception as e:
                        logger.error(f"Failed to store asset {asset_uri}: {e}")
                        results[asset_uri] = None

            for uri in uris_to_fetch:
                if uri not in results:
                    cached_content = self.cache_store.get_asset(uri)
                    if cached_content is not None:
                        logger.warning(f"Using cached asset despite fetch failure: {uri}")
                        results[uri] = self.cache_store.get_asset_path(uri)
                    else:
                        results[uri] = None

        except NetworkError as e:
            logger.error(f"Failed to fetch assets: {e}")
            for uri in uris_to_fetch:
                if uri not in results:
                    cached_content = self.cache_store.get_asset(uri)
                    if cached_content is not None:
                        logger.warning(f"Using cached asset despite fetch failure: {uri}")
                        results[uri] = self.cache_store.get_asset_path(uri)
                    else:
                        results[uri] = None

        return results

    async def fetch_incremental(
        self,
        asset_uri: str,
        base_version: str,
    ) -> Optional[Path]:
        """
        Fetch incremental update for asset

        Args:
            asset_uri: Asset URI (without version)
            base_version: Base version to update from

        Returns:
            Path to cached asset file, or None if fetch failed
        """
        try:
            response = await self.sync_client.fetch_assets(
                [asset_uri],
                incremental={
                    "enabled": True,
                    "base_versions": [
                        {
                            "uri": asset_uri,
                            "version": base_version,
                        }
                    ],
                }
            )

            diffs = response.get("diffs", [])
            if not diffs:
                return await self.fetch_asset(asset_uri, force_refresh=True)

            diff_data = diffs[0]
            diff_type = diff_data.get("diff_type", "full_replace")

            if diff_type == "full_replace":
                return await self.fetch_asset(asset_uri, force_refresh=True)

            elif diff_type == "json_patch":
                return await self._apply_json_patch(asset_uri, diff_data)

            elif diff_type == "text_diff":
                return await self._apply_text_diff(asset_uri, diff_data)

            else:
                logger.warning(f"Unknown diff type: {diff_type}, falling back to full fetch")
                return await self.fetch_asset(asset_uri, force_refresh=True)

        except NetworkError as e:
            logger.error(f"Failed to fetch incremental update for {asset_uri}: {e}")
            return None

    async def _store_asset(self, asset_data: Dict[str, Any]) -> Path:
        """
        Store asset data in cache

        Args:
            asset_data: Asset data from API response

        Returns:
            Path to stored asset file
        """
        asset_uri = asset_data["uri"]
        content_type = asset_data.get("content_type", "application/octet-stream")
        content_encoded = asset_data.get("content", "")
        checksum = asset_data.get("checksum", "")
        metadata = asset_data.get("metadata", {})

        try:
            if content_encoded.startswith("data:"):
                content = base64.b64decode(content_encoded.split(",")[1])
            else:
                content = base64.b64decode(content_encoded)
        except Exception as e:
            logger.error(f"Failed to decode asset content for {asset_uri}: {e}")
            raise

        if checksum:
            expected_checksum = checksum.replace("sha256:", "")
            actual_checksum = hashlib.sha256(content).hexdigest()

            if expected_checksum != actual_checksum:
                raise ValueError(f"Checksum mismatch for {asset_uri}")

        return self.cache_store.store_asset(
            asset_uri=asset_uri,
            content=content,
            checksum=checksum,
            metadata=metadata,
        )

    async def _apply_json_patch(
        self,
        asset_uri: str,
        diff_data: Dict[str, Any],
    ) -> Optional[Path]:
        """Apply JSON Patch to cached asset"""
        try:
            import jsonpatch
        except ImportError:
            logger.warning("jsonpatch not available, falling back to full fetch")
            return await self.fetch_asset(asset_uri, force_refresh=True)

        cached_content = self.cache_store.get_asset(asset_uri)
        if not cached_content:
            logger.warning(f"No cached content for {asset_uri}, falling back to full fetch")
            return await self.fetch_asset(asset_uri, force_refresh=True)

        try:
            current_data = json.loads(cached_content.decode("utf-8"))
            patch_ops = diff_data.get("diff", [])

            patch = jsonpatch.JsonPatch(patch_ops)
            patched_data = patch.apply(current_data)
            patched_content = json.dumps(patched_data, indent=2, ensure_ascii=False).encode("utf-8")

            return self.cache_store.store_asset(
                asset_uri=asset_uri,
                content=patched_content,
                checksum=None,
                metadata={},
            )

        except Exception as e:
            logger.error(f"Failed to apply JSON patch for {asset_uri}: {e}")
            return await self.fetch_asset(asset_uri, force_refresh=True)

    async def _apply_text_diff(
        self,
        asset_uri: str,
        diff_data: Dict[str, Any],
    ) -> Optional[Path]:
        """Apply text diff to cached asset"""
        logger.warning("Text diff not fully implemented, falling back to full fetch")
        return await self.fetch_asset(asset_uri, force_refresh=True)

