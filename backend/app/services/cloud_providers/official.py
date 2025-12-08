"""
Official Mindscape AI Cloud Provider
Provider implementation for official commercial cloud service

Note: This is just one provider type, not a "built-in" or special provider.
All providers are configured through the same neutral interface.
"""

import os
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Tuple
from datetime import datetime, timedelta

try:
    import httpx
except ImportError:
    httpx = None

from .base import CloudProvider

logger = logging.getLogger(__name__)


class OfficialCloudProvider(CloudProvider):
    """
    Official Mindscape AI Cloud provider

    This is a provider implementation for the official commercial cloud service.
    It's just one provider type among many - no special treatment.
    Developers can use this as a reference for implementing their own providers.
    """

    def __init__(
        self,
        api_url: Optional[str] = None,
        license_key: Optional[str] = None,
        cache_dir: Optional[Path] = None,
        cache_ttl_days: int = 1,
        settings_store=None
    ):
        """
        Initialize Official Cloud Provider

        Args:
            api_url: Cloud API base URL (from config)
            license_key: License key for authentication (from config)
            cache_dir: Directory for caching playbooks
            cache_ttl_days: Cache TTL in days
            settings_store: SystemSettingsStore instance (optional, for backward compatibility)
        """
        # Get from parameters (passed from config) or env vars (backward compatibility)
        self.api_url = api_url or os.getenv("CLOUD_API_URL")
        self.license_key = license_key or os.getenv("CLOUD_LICENSE_KEY")

        # Backward compatibility: try to read from old settings format
        if settings_store and not self.api_url:
            try:
                self.api_url = settings_store.get("cloud_api_url", default="") or os.getenv("CLOUD_API_URL")
                self.license_key = settings_store.get("cloud_license_key", default="") or os.getenv("CLOUD_LICENSE_KEY")
            except Exception as e:
                logger.debug(f"Failed to read cloud settings from store: {e}")

        self.cache_ttl_days = cache_ttl_days

        if cache_dir:
            self.cache_dir = Path(cache_dir)
        else:
            cache_home = Path.home() / ".mindscape" / "cloud_playbooks" / "official"
            self.cache_dir = cache_home

        self.cache_dir.mkdir(parents=True, exist_ok=True)

        if not httpx:
            logger.warning("httpx not installed, cloud playbook features will be disabled")
            self._httpx_available = False
        else:
            self._httpx_available = True

    def get_provider_id(self) -> str:
        return "mindscape_official"

    def get_provider_name(self) -> str:
        return "Mindscape AI Cloud"

    def get_provider_description(self) -> str:
        return "Commercial cloud service for Mindscape AI playbooks"

    def is_configured(self) -> bool:
        """Check if provider is properly configured"""
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
        """Get playbook from cache or download from cloud"""
        if not self.is_configured():
            logger.debug("Official Cloud Provider not configured, skipping playbook download")
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
            "cached_at": datetime.utcnow().isoformat(),
            "expires_at": (datetime.utcnow() + timedelta(days=self.cache_ttl_days)).isoformat()
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
            return datetime.utcnow() > expires_at
        except Exception as e:
            logger.warning(f"Error checking cache expiration: {e}")
            return True

    async def test_connection(self) -> Tuple[bool, str]:
        """Test connection to provider"""
        if not self.is_configured():
            return False, "Provider not configured (missing API URL or License Key)"

        try:
            # Try to get version of a test playbook
            url = f"{self.api_url}/api/v1/playbooks/web_generation/page_outline/version"

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    url,
                    headers={"Authorization": f"Bearer {self.license_key}"}
                )

                if response.status_code == 200:
                    return True, "Connection successful"
                elif response.status_code == 401:
                    return False, "Invalid license key"
                elif response.status_code == 403:
                    return False, "License key valid but playbook not included in subscription"
                else:
                    return False, f"Connection failed: {response.status_code} {response.statusText}"
        except httpx.TimeoutException:
            return False, "Connection timeout"
        except Exception as e:
            return False, f"Connection failed: {str(e)}"

    def get_config_schema(self) -> Dict:
        """Return configuration schema"""
        return {
            "fields": [
                {
                    "name": "api_url",
                    "type": "string",
                    "label": "Cloud API URL",
                    "required": True,
                    "description": "Base URL for Cloud service API"
                },
                {
                    "name": "license_key",
                    "type": "password",
                    "label": "License Key",
                    "required": True,
                    "description": "License key for authentication",
                    "sensitive": True
                }
            ],
            "required": ["api_url", "license_key"]
        }

    def validate_config(self, config: Dict) -> Tuple[bool, Optional[str]]:
        """Validate provider configuration"""
        if not config.get("api_url"):
            return False, "API URL is required"
        if not config.get("license_key"):
            return False, "License Key is required"
        return True, None

