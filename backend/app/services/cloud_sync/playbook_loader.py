"""
Playbook Loader
Loads Playbook content from cache with multi-language support
"""

import logging
from pathlib import Path
from typing import Optional, Dict, Any

from .cache_store import CacheStore, CacheLifecycleManager
from .asset_fetcher import AssetFetcher

logger = logging.getLogger(__name__)


class PlaybookLoader:
    """Loads Playbook content from cache"""

    def __init__(
        self,
        cache_store: CacheStore,
        asset_fetcher: Optional[AssetFetcher] = None,
        lifecycle_manager: Optional[CacheLifecycleManager] = None,
    ):
        """
        Initialize playbook loader

        Args:
            cache_store: CacheStore instance
            asset_fetcher: AssetFetcher instance (optional, for fetching missing playbooks)
            lifecycle_manager: CacheLifecycleManager instance (optional)
        """
        self.cache_store = cache_store
        self.asset_fetcher = asset_fetcher
        self.lifecycle_manager = lifecycle_manager or CacheLifecycleManager(cache_store)

    def load_playbook(
        self,
        playbook_uri: str,
        locale: str = "zh-TW",
        version: Optional[str] = None,
        force_refresh: bool = False,
    ) -> Optional[str]:
        """
        Load playbook content from cache

        Args:
            playbook_uri: Playbook URI (with or without version)
            locale: Language locale (default: zh-TW)
            version: Specific version to load (optional)
            force_refresh: Force refresh from cache

        Returns:
            Playbook content as string or None if not found
        """
        if version:
            full_uri = f"{playbook_uri}@{version}" if "@" not in playbook_uri else playbook_uri
        else:
            full_uri = playbook_uri

        asset_path = self.cache_store.get_asset_path(full_uri)
        playbook_file = asset_path / f"asset.{locale}.md"

        if not playbook_file.exists():
            playbook_file = asset_path / "asset.md"

        if not playbook_file.exists():
            if self.asset_fetcher:
                logger.info(f"Playbook not in cache, fetching: {full_uri} (locale: {locale})")
                import asyncio
                try:
                    asyncio.run(self.asset_fetcher.fetch_asset(full_uri, force_refresh=True))
                    asset_path = self.cache_store.get_asset_path(full_uri)
                    playbook_file = asset_path / f"asset.{locale}.md"
                    if not playbook_file.exists():
                        playbook_file = asset_path / "asset.md"
                except Exception as e:
                    logger.error(f"Failed to fetch playbook {full_uri}: {e}")
                    return None
            else:
                logger.warning(f"Playbook not found in cache: {full_uri} (locale: {locale})")
                return None

        try:
            with open(playbook_file, "r", encoding="utf-8") as f:
                content = f.read()
            return content

        except Exception as e:
            logger.error(f"Failed to load playbook {full_uri} (locale: {locale}): {e}")
            return None

    async def load_playbook_async(
        self,
        playbook_uri: str,
        locale: str = "zh-TW",
        version: Optional[str] = None,
        force_refresh: bool = False,
    ) -> Optional[str]:
        """
        Load playbook content from cache (async version)

        Args:
            playbook_uri: Playbook URI (with or without version)
            locale: Language locale (default: zh-TW)
            version: Specific version to load (optional)
            force_refresh: Force refresh from cache

        Returns:
            Playbook content as string or None if not found
        """
        if version:
            full_uri = f"{playbook_uri}@{version}" if "@" not in playbook_uri else playbook_uri
        else:
            full_uri = playbook_uri

        asset_path = self.cache_store.get_asset_path(full_uri)
        playbook_file = asset_path / f"asset.{locale}.md"

        if not playbook_file.exists():
            playbook_file = asset_path / "asset.md"

        if not playbook_file.exists():
            if self.asset_fetcher:
                logger.info(f"Playbook not in cache, fetching: {full_uri} (locale: {locale})")
                try:
                    await self.asset_fetcher.fetch_asset(full_uri, force_refresh=True)
                    asset_path = self.cache_store.get_asset_path(full_uri)
                    playbook_file = asset_path / f"asset.{locale}.md"
                    if not playbook_file.exists():
                        playbook_file = asset_path / "asset.md"
                except Exception as e:
                    logger.error(f"Failed to fetch playbook {full_uri}: {e}")
                    return None
            else:
                logger.warning(f"Playbook not found in cache: {full_uri} (locale: {locale})")
                return None

        try:
            with open(playbook_file, "r", encoding="utf-8") as f:
                content = f.read()
            return content

        except Exception as e:
            logger.error(f"Failed to load playbook {full_uri} (locale: {locale}): {e}")
            return None

    def get_available_locales(self, playbook_uri: str) -> list:
        """
        Get available locales for playbook

        Args:
            playbook_uri: Playbook URI

        Returns:
            List of available locale codes
        """
        asset_path = self.cache_store.get_asset_path(playbook_uri)
        locales = []

        if asset_path.exists():
            for file in asset_path.glob("asset.*.md"):
                locale = file.stem.replace("asset.", "")
                if locale:
                    locales.append(locale)

            if (asset_path / "asset.md").exists():
                locales.append("default")

        return locales

    def is_playbook_cached(self, playbook_uri: str, locale: str = "zh-TW", version: Optional[str] = None) -> bool:
        """
        Check if playbook is cached

        Args:
            playbook_uri: Playbook URI
            locale: Language locale
            version: Specific version (optional)

        Returns:
            True if playbook is cached
        """
        if version:
            full_uri = f"{playbook_uri}@{version}" if "@" not in playbook_uri else playbook_uri
        else:
            full_uri = playbook_uri

        asset_path = self.cache_store.get_asset_path(full_uri)
        playbook_file = asset_path / f"asset.{locale}.md"

        if not playbook_file.exists():
            playbook_file = asset_path / "asset.md"

        return playbook_file.exists()

