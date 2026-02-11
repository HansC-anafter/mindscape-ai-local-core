"""
Generic HTTP Cloud Provider
Generic provider for HTTP-based cloud services
Allows developers to easily add custom cloud providers
"""

import json
import logging
from pathlib import Path
from typing import Optional, Dict, Tuple, Any
from datetime import datetime, timedelta, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)

try:
    import httpx
except ImportError:
    httpx = None

from backend.app.services.cloud_providers.base import CloudProvider

logger = logging.getLogger(__name__)


class GenericHttpProvider(CloudProvider):
    """
    Generic HTTP-based cloud provider

    This provider can be configured to work with any HTTP-based
    cloud service that follows a similar API structure.

    Developers can use this as a template or extend it for their needs.
    """

    def __init__(
        self,
        provider_id: str,
        provider_name: str,
        api_url: str,
        auth_config: Dict,
        cache_dir: Optional[Path] = None,
        cache_ttl_days: int = 1,
        api_path_template: str = "/api/v1/playbooks/{capability_code}/{playbook_code}",
        pack_download_path: Optional[str] = None
    ):
        """
        Initialize Generic HTTP Provider

        Args:
            provider_id: Unique provider identifier
            provider_name: Human-readable provider name
            api_url: Base URL for the cloud service
            auth_config: Authentication configuration
                - auth_type: "bearer", "api_key", "oauth", etc.
                - token/api_key/client_id/etc.: Based on auth_type
            cache_dir: Directory for caching playbooks
            cache_ttl_days: Cache TTL in days
            api_path_template: API path template (supports {capability_code}, {playbook_code}, {locale})
            pack_download_path: API path for getting pack download link (e.g., "/api/v1/packs/download_link")
        """
        self.provider_id = provider_id
        self.provider_name = provider_name
        self.api_url = api_url.rstrip("/")
        self.auth_config = auth_config
        self.api_path_template = api_path_template
        self.cache_ttl_days = cache_ttl_days
        self.pack_download_path = pack_download_path or "/api/v1/packs/download_link"

        if cache_dir:
            self.cache_dir = Path(cache_dir)
        else:
            cache_home = Path.home() / ".mindscape" / "cloud_playbooks" / provider_id
            self.cache_dir = cache_home

        self.cache_dir.mkdir(parents=True, exist_ok=True)

        if not httpx:
            logger.warning("httpx not installed, cloud playbook features will be disabled")
            self._httpx_available = False
        else:
            self._httpx_available = True

    def get_provider_id(self) -> str:
        return self.provider_id

    def get_provider_name(self) -> str:
        return self.provider_name

    def get_provider_description(self) -> str:
        return f"Generic HTTP provider for {self.provider_name}"

    def is_configured(self) -> bool:
        """Check if provider is properly configured"""
        if not self._httpx_available:
            return False
        if not self.api_url:
            return False

        auth_type = self.auth_config.get("auth_type", "bearer")
        if auth_type == "bearer":
            return bool(self.auth_config.get("token"))
        elif auth_type == "api_key":
            return bool(self.auth_config.get("api_key"))
        elif auth_type == "oauth":
            return bool(self.auth_config.get("client_id") and self.auth_config.get("client_secret"))

        return False

    def _get_auth_headers(self) -> Dict[str, str]:
        """Get authentication headers based on auth_config"""
        auth_type = self.auth_config.get("auth_type", "bearer")
        headers = {}

        if auth_type == "bearer":
            token = self.auth_config.get("token")
            if token:
                headers["Authorization"] = f"Bearer {token}"
        elif auth_type == "api_key":
            api_key = self.auth_config.get("api_key")
            api_key_header = self.auth_config.get("api_key_header", "X-API-Key")
            if api_key:
                headers[api_key_header] = api_key
        elif auth_type == "oauth":
            # OAuth would need token refresh logic
            # For now, assume token is already obtained
            token = self.auth_config.get("access_token")
            if token:
                headers["Authorization"] = f"Bearer {token}"

        return headers

    async def get_playbook(
        self,
        capability_code: str,
        playbook_code: str,
        locale: str = "en"
    ) -> Optional[Dict]:
        """Get playbook from cache or download from cloud"""
        if not self.is_configured():
            logger.debug(f"{self.provider_name} not configured, skipping playbook download")
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

        # Build URL from template
        path = self.api_path_template.format(
            capability_code=capability_code,
            playbook_code=playbook_code,
            locale=locale
        )
        url = f"{self.api_url}{path}"

        headers = self._get_auth_headers()
        headers["Accept"] = "application/json"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    url,
                    params={"locale": locale},
                    headers=headers
                )

                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 401:
                    logger.error("Authentication failed")
                    raise ValueError("Authentication failed")
                elif response.status_code == 403:
                    logger.error(f"Access denied for {capability_code}.{playbook_code}")
                    raise ValueError("Access denied")
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

    async def test_connection(self) -> Tuple[bool, str]:
        """Test connection to provider"""
        if not self.is_configured():
            return False, "Provider not configured"

        try:
            # Try a simple health check or version endpoint
            test_url = f"{self.api_url}/health"
            headers = self._get_auth_headers()

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(test_url, headers=headers)

                if response.status_code in [200, 404]:  # 404 is OK if health endpoint doesn't exist
                    return True, "Connection successful"
                else:
                    return False, f"Connection failed: {response.status_code}"
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
                    "label": "API URL",
                    "required": True,
                    "description": "Base URL for the cloud service"
                },
                {
                    "name": "auth_type",
                    "type": "select",
                    "label": "Authentication Type",
                    "required": True,
                    "options": ["bearer", "api_key", "oauth"],
                    "description": "Authentication method"
                },
                {
                    "name": "token",
                    "type": "password",
                    "label": "Token",
                    "required": False,
                    "description": "Bearer token (if auth_type is bearer)",
                    "sensitive": True
                },
                {
                    "name": "api_key",
                    "type": "password",
                    "label": "API Key",
                    "required": False,
                    "description": "API key (if auth_type is api_key)",
                    "sensitive": True
                },
                {
                    "name": "pack_download_path",
                    "type": "string",
                    "label": "Pack Download API Path",
                    "required": False,
                    "description": "API path for getting pack download link (default: /api/v1/packs/download_link)",
                    "default": "/api/v1/packs/download_link"
                }
            ],
            "required": ["api_url", "auth_type"]
        }

    def validate_config(self, config: Dict) -> Tuple[bool, Optional[str]]:
        """Validate provider configuration"""
        if not config.get("api_url"):
            return False, "API URL is required"

        auth_type = config.get("auth_type")
        if not auth_type:
            return False, "Authentication type is required"

        if auth_type == "bearer" and not config.get("token"):
            return False, "Token is required for bearer authentication"
        elif auth_type == "api_key" and not config.get("api_key"):
            return False, "API key is required for api_key authentication"

        # Update pack_download_path if provided in config
        if config.get("pack_download_path"):
            self.pack_download_path = config["pack_download_path"]

        return True, None

    def get_api_url(self) -> str:
        """Get provider API URL"""
        return self.api_url

    def get_api_key(self) -> Optional[str]:
        """Get provider API key/token for authentication"""
        auth_type = self.auth_config.get("auth_type", "bearer")
        if auth_type == "bearer":
            return self.auth_config.get("token")
        elif auth_type == "api_key":
            return self.auth_config.get("api_key")
        return None

    async def get_download_link(self, pack_ref: str) -> Dict[str, Any]:
        """
        Get download link for a pack from cloud provider

        Generic implementation that calls the configured pack_download_path endpoint.
        Provider-specific implementations can override this method.

        Args:
            pack_ref: Pack reference in format "provider_id:code@version" or provider-specific format

        Returns:
            Dict containing download_url, expires_at, checksum, size

        Raises:
            ValueError: If authentication fails or pack not found
            Exception: If API call fails
        """
        if not self.is_configured():
            raise ValueError(f"{self.provider_name} not configured")

        if not self._httpx_available:
            raise ValueError("httpx not available")

        # Use configured pack_download_path (default: "/api/v1/packs/download_link")
        url = f"{self.api_url}{self.pack_download_path}"
        headers = self._get_auth_headers()
        headers["Content-Type"] = "application/json"
        headers["Accept"] = "application/json"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    url,
                    json={"pack_ref": pack_ref},
                    headers=headers
                )

                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 401:
                    logger.error("Authentication failed when getting download link")
                    raise ValueError("Authentication failed")
                elif response.status_code == 403:
                    logger.error(f"Access denied for pack {pack_ref}")
                    error_data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
                    raise ValueError(f"Access denied: {error_data.get('detail', 'Entitlement required')}")
                elif response.status_code == 404:
                    logger.warning(f"Pack {pack_ref} not found")
                    raise ValueError(f"Pack {pack_ref} not found")
                else:
                    logger.error(f"Failed to get download link: {response.status_code}")
                    error_msg = f"Failed to get download link: {response.status_code}"
                    try:
                        error_data = response.json()
                        error_msg = error_data.get("detail", error_msg)
                    except:
                        pass
                    raise Exception(error_msg)
        except httpx.TimeoutException:
            logger.error(f"Timeout getting download link for pack {pack_ref}")
            raise Exception("Request timeout")
        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Error getting download link: {e}")
            raise

