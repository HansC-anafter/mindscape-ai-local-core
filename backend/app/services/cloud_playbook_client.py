"""
Cloud Playbook Client (Legacy)
DEPRECATED: Use CloudExtensionManager and CloudProvider instead

This module is kept for backward compatibility.
New code should use CloudExtensionManager and CloudProvider interface.
"""

import os
import json
import logging
from pathlib import Path
from typing import Optional, Dict
from datetime import datetime, timedelta, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)

try:
    import httpx
except ImportError:
    httpx = None

logger = logging.getLogger(__name__)


class CloudPlaybookClient:
    """Client for downloading and managing cloud playbooks"""

    def __init__(
        self,
        api_url: Optional[str] = None,
        license_key: Optional[str] = None,
        cache_dir: Optional[Path] = None,
        cache_ttl_days: int = 1,
        settings_store=None
    ):
        """
        Initialize Cloud Playbook Client

        Args:
            api_url: Cloud API base URL (defaults to system settings or CLOUD_API_URL env var)
            license_key: License key for authentication (defaults to system settings or CLOUD_LICENSE_KEY env var)
            cache_dir: Directory for caching playbooks (defaults to ~/.mindscape/cloud_playbooks)
            cache_ttl_days: Cache TTL in days (default: 1)
            settings_store: SystemSettingsStore instance (optional, for reading settings from database)
        """
        # Try to get from system settings first, then env vars
        if settings_store:
            try:
                cloud_enabled = settings_store.get("cloud_enabled", default=False)
                if cloud_enabled:
                    self.api_url = api_url or settings_store.get("cloud_api_url", default="") or os.getenv("CLOUD_API_URL")
                    self.license_key = license_key or settings_store.get("cloud_license_key", default="") or os.getenv("CLOUD_LICENSE_KEY")
                else:
                    self.api_url = None
                    self.license_key = None
            except Exception as e:
                logger.warning(f"Failed to read cloud settings from store: {e}, falling back to env vars")
                self.api_url = api_url or os.getenv("CLOUD_API_URL")
                self.license_key = license_key or os.getenv("CLOUD_LICENSE_KEY")
        else:
            self.api_url = api_url or os.getenv("CLOUD_API_URL")
            self.license_key = license_key or os.getenv("CLOUD_LICENSE_KEY")
        self.cache_ttl_days = cache_ttl_days

        if cache_dir:
            self.cache_dir = Path(cache_dir)
        else:
            cache_home = Path.home() / ".mindscape" / "cloud_playbooks"
            self.cache_dir = cache_home

        self.cache_dir.mkdir(parents=True, exist_ok=True)

        if not httpx:
            logger.warning("httpx not installed, cloud playbook features will be disabled")
            self._httpx_available = False
        else:
            self._httpx_available = True

    def is_configured(self) -> bool:
        """Check if client is properly configured"""
        return (
            self._httpx_available and
            self.api_url is not None and
            self.license_key is not None
        )

    async def get_playbook(
        self,
        capability_code: str,
        playbook_code: str,
        locale: str = "en"
    ) -> Optional[Dict]:
        """
        Get playbook from cache or download from cloud

        Args:
            capability_code: Capability pack code (e.g., "web_generation")
            playbook_code: Playbook code (e.g., "page_outline")
            locale: Locale code (e.g., "en", "zh-TW")

        Returns:
            Playbook data dict or None if not available
        """
        if not self.is_configured():
            logger.debug("Cloud Playbook Client not configured, skipping cloud playbook download")
            return None

        # Check cache first
        cached = self._load_from_cache(capability_code, playbook_code, locale)
        if cached and not self._is_cache_expired(cached):
            logger.debug(f"Using cached playbook: {capability_code}.{playbook_code} ({locale})")
            return cached["playbook"]

        # Download from cloud
        try:
            playbook = await self._download_from_cloud(
                capability_code, playbook_code, locale
            )

            if playbook:
                self._save_to_cache(capability_code, playbook_code, locale, playbook)
                logger.info(f"Downloaded and cached playbook: {capability_code}.{playbook_code} ({locale})")

            return playbook
        except Exception as e:
            logger.error(f"Failed to download playbook {capability_code}.{playbook_code}: {e}")
            # Return cached version if available, even if expired
            if cached:
                logger.warning(f"Using expired cache for {capability_code}.{playbook_code}")
                return cached["playbook"]
            return None

    async def _download_from_cloud(
        self,
        capability_code: str,
        playbook_code: str,
        locale: str
    ) -> Optional[Dict]:
        """Download playbook from cloud API"""

        if not self._httpx_available:
            return None

        url = f"{self.api_url}/api/v1/playbooks/{capability_code}/{playbook_code}"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    url,
                    params={"locale": locale},
                    headers={
                        "Authorization": f"Bearer {self.license_key}",
                        "Accept": "application/json"
                    }
                )

                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 401:
                    logger.error("Invalid license key")
                    raise ValueError("Invalid license key")
                elif response.status_code == 403:
                    logger.error(f"Playbook {capability_code}.{playbook_code} not included in subscription")
                    raise ValueError("Playbook not included in your subscription")
                elif response.status_code == 404:
                    logger.warning(f"Playbook {capability_code}.{playbook_code} not found")
                    return None
                else:
                    logger.error(f"Failed to download playbook: {response.status_code}")
                    raise Exception(f"Failed to download playbook: {response.status_code}")
        except httpx.TimeoutException:
            logger.error(f"Timeout downloading playbook {capability_code}.{playbook_code}")
            return None
        except Exception as e:
            logger.error(f"Error downloading playbook: {e}")
            raise

    def _load_from_cache(
        self,
        capability_code: str,
        playbook_code: str,
        locale: str
    ) -> Optional[Dict]:
        """Load playbook from local cache"""

        cache_file = self._get_cache_file(capability_code, playbook_code, locale)
        if not cache_file.exists():
            return None

        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load cache file {cache_file}: {e}")
            return None

    def _save_to_cache(
        self,
        capability_code: str,
        playbook_code: str,
        locale: str,
        playbook: Dict
    ):
        """Save playbook to local cache"""

        cache_file = self._get_cache_file(capability_code, playbook_code, locale)

        cache_data = {
            "playbook": playbook,
            "cached_at": _utc_now().isoformat(),
            "expires_at": (_utc_now() + timedelta(days=self.cache_ttl_days)).isoformat()
        }

        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(cache_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"Failed to save cache file {cache_file}: {e}")

    def _get_cache_file(
        self,
        capability_code: str,
        playbook_code: str,
        locale: str
    ) -> Path:
        """Get cache file path"""
        safe_name = f"{capability_code}_{playbook_code}_{locale}".replace("/", "_")
        return self.cache_dir / f"{safe_name}.json"

    def _is_cache_expired(self, cached: Dict) -> bool:
        """Check if cache is expired"""

        try:
            expires_at_str = cached.get("expires_at")
            if not expires_at_str:
                return True

            expires_at = datetime.fromisoformat(expires_at_str)
            return _utc_now() > expires_at
        except Exception as e:
            logger.warning(f"Error checking cache expiration: {e}")
            return True

    async def check_updates(
        self,
        capability_code: str,
        playbook_code: str
    ) -> bool:
        """
        Check if playbook has updates available

        Args:
            capability_code: Capability pack code
            playbook_code: Playbook code

        Returns:
            True if updates are available, False otherwise
        """
        if not self.is_configured():
            return False

        if not self._httpx_available:
            return False

        url = f"{self.api_url}/api/v1/playbooks/{capability_code}/{playbook_code}/version"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    url,
                    headers={"Authorization": f"Bearer {self.license_key}"}
                )

                if response.status_code == 200:
                    cloud_version = response.json().get("version")
                    if not cloud_version:
                        return False

                    # Check cached version
                    cached = self._load_from_cache(capability_code, playbook_code, "en")
                    if cached:
                        cached_version = cached.get("playbook", {}).get("metadata", {}).get("version")
                        return cloud_version != cached_version
                    return True

                return False
        except Exception as e:
            logger.warning(f"Error checking updates for {capability_code}.{playbook_code}: {e}")
            return False

    def clear_cache(
        self,
        capability_code: Optional[str] = None,
        playbook_code: Optional[str] = None
    ):
        """
        Clear cache for specific playbook or all playbooks

        Args:
            capability_code: If provided, only clear cache for this capability
            playbook_code: If provided, only clear cache for this playbook
        """
        if capability_code and playbook_code:
            # Clear specific playbook cache for all locales
            for cache_file in self.cache_dir.glob(f"{capability_code}_{playbook_code}_*.json"):
                try:
                    cache_file.unlink()
                    logger.info(f"Cleared cache: {cache_file.name}")
                except Exception as e:
                    logger.warning(f"Failed to clear cache {cache_file}: {e}")
        elif capability_code:
            # Clear all playbooks for this capability
            for cache_file in self.cache_dir.glob(f"{capability_code}_*.json"):
                try:
                    cache_file.unlink()
                    logger.info(f"Cleared cache: {cache_file.name}")
                except Exception as e:
                    logger.warning(f"Failed to clear cache {cache_file}: {e}")
        else:
            # Clear all cache
            for cache_file in self.cache_dir.glob("*.json"):
                try:
                    cache_file.unlink()
                    logger.info(f"Cleared cache: {cache_file.name}")
                except Exception as e:
                    logger.warning(f"Failed to clear cache {cache_file}: {e}")

