"""
Sync Client
HTTP client for cloud sync API communication
"""

import os
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum

try:
    import httpx
except ImportError:
    httpx = None

logger = logging.getLogger(__name__)


class SyncError(Exception):
    """Base exception for sync operations"""
    pass


class AuthenticationError(SyncError):
    """Authentication failed"""
    pass


class NetworkError(SyncError):
    """Network communication error"""
    pass


class VersionError(SyncError):
    """Version compatibility error"""
    pass


class QuotaError(SyncError):
    """Quota limit exceeded"""
    pass


class SyncClient:
    """HTTP client for cloud sync API"""

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: float = 30.0,
        max_retries: int = 3,
    ):
        """
        Initialize sync client

        Args:
            base_url: Cloud API base URL (defaults to CLOUD_SYNC_BASE_URL env var)
            api_key: API key for authentication (defaults to CLOUD_SYNC_API_KEY env var)
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
        """
        if not httpx:
            raise ImportError("httpx is required for sync client. Install with: pip install httpx")

        self.base_url = base_url or os.getenv("CLOUD_SYNC_BASE_URL", "")
        self.api_key = api_key or os.getenv("CLOUD_SYNC_API_KEY", "")
        self.timeout = timeout
        self.max_retries = max_retries

        if not self.base_url:
            logger.warning("CLOUD_SYNC_BASE_URL not configured, sync features will be disabled")
        if not self.api_key:
            logger.warning("CLOUD_SYNC_API_KEY not configured, sync features will be disabled")

    def is_configured(self) -> bool:
        """Check if client is properly configured"""
        return bool(self.base_url and self.api_key)

    def _get_headers(self) -> Dict[str, str]:
        """Get HTTP headers for requests"""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        if self.api_key:
            headers["X-API-Key"] = self.api_key

        return headers

    async def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Make HTTP request with retry logic

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            data: Request body data
            params: Query parameters

        Returns:
            Response JSON data

        Raises:
            AuthenticationError: If authentication fails
            NetworkError: If network request fails
            VersionError: If version compatibility error
            QuotaError: If quota limit exceeded
        """
        if not self.is_configured():
            raise NetworkError("Sync client not configured")

        url = f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        headers = self._get_headers()

        last_error = None
        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.request(
                        method=method,
                        url=url,
                        headers=headers,
                        json=data,
                        params=params,
                    )

                    if response.status_code == 200:
                        return response.json()

                    elif response.status_code == 401:
                        raise AuthenticationError("Invalid or expired API key")

                    elif response.status_code == 403:
                        error_data = response.json() if response.content else {}
                        if "license" in error_data.get("error", "").lower():
                            raise AuthenticationError("License expired")
                        raise AuthenticationError("Access forbidden")

                    elif response.status_code == 409:
                        error_data = response.json() if response.content else {}
                        error_code = error_data.get("error_code", "")
                        if error_code.startswith("VERSION_"):
                            raise VersionError(error_data.get("message", "Version compatibility error"))
                        raise VersionError("Version conflict")

                    elif response.status_code == 429:
                        raise QuotaError("Quota limit exceeded")

                    else:
                        error_msg = f"API request failed: {response.status_code}"
                        if response.content:
                            try:
                                error_data = response.json()
                                error_msg = error_data.get("message", error_msg)
                            except Exception:
                                error_msg = response.text[:200]
                        raise NetworkError(error_msg)

            except httpx.TimeoutException as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    logger.warning(f"Request timeout (attempt {attempt + 1}/{self.max_retries}), retrying...")
                    continue
                raise NetworkError(f"Request timeout after {self.max_retries} attempts")

            except httpx.NetworkError as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    logger.warning(f"Network error (attempt {attempt + 1}/{self.max_retries}), retrying...")
                    continue
                raise NetworkError(f"Network error: {str(e)}")

            except (AuthenticationError, VersionError, QuotaError):
                raise

            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    logger.warning(f"Request failed (attempt {attempt + 1}/{self.max_retries}): {e}, retrying...")
                    continue
                raise NetworkError(f"Request failed: {str(e)}")

        raise NetworkError(f"Request failed after {self.max_retries} attempts: {last_error}")

    async def check_versions(
        self,
        client_version: str,
        capabilities: List[Dict[str, str]],
        assets: List[Dict[str, Any]],
        license_id: Optional[str] = None,
        device_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Check for version updates

        Args:
            client_version: Local Core version
            capabilities: List of installed capabilities with versions
            assets: List of cached assets with versions
            license_id: License ID (optional)
            device_id: Device ID (optional)

        Returns:
            Version check response with updates information
        """
        request_data = {
            "client_version": client_version,
            "capabilities": capabilities,
            "assets": assets,
        }

        if license_id:
            request_data["license_id"] = license_id
        if device_id:
            request_data["device_id"] = device_id

        return await self._request("POST", "/api/v1/sync/versions/check", data=request_data)

    async def fetch_assets(
        self,
        asset_uris: List[str],
        incremental: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Fetch assets from cloud

        Args:
            asset_uris: List of asset URIs to fetch
            incremental: Incremental update configuration (optional)

        Returns:
            Assets response with content and metadata
        """
        request_data = {
            "assets": [{"uri": uri} for uri in asset_uris],
        }

        if incremental:
            request_data["incremental"] = incremental

        return await self._request("POST", "/api/v1/sync/assets/fetch", data=request_data)

    async def sync_instances(
        self,
        direction: str,
        instances: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Sync instances with cloud

        Args:
            direction: Sync direction (pull, push, merge)
            instances: List of instances to sync

        Returns:
            Sync results
        """
        request_data = {
            "direction": direction,
            "instances": instances,
        }

        return await self._request("POST", "/api/v1/sync/instances/sync", data=request_data)


class VersionChecker:
    """Checks for version updates and determines update priority"""

    def __init__(self, sync_client: SyncClient):
        """
        Initialize version checker

        Args:
            sync_client: SyncClient instance
        """
        self.sync_client = sync_client

    async def check_updates(
        self,
        client_version: str,
        capabilities: List[Dict[str, str]],
        assets: List[Dict[str, Any]],
        license_id: Optional[str] = None,
        device_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Check for available updates

        Args:
            client_version: Local Core version
            capabilities: Installed capabilities
            assets: Cached assets
            license_id: License ID
            device_id: Device ID

        Returns:
            Update information with priorities
        """
        response = await self.sync_client.check_versions(
            client_version=client_version,
            capabilities=capabilities,
            assets=assets,
            license_id=license_id,
            device_id=device_id,
        )

        return {
            "client_update": response.get("client_update", {}),
            "capability_updates": response.get("capability_updates", []),
            "asset_updates": response.get("asset_updates", []),
            "license": response.get("license", {}),
            "server_time": response.get("server_time"),
        }

    def get_update_priority(self, update_info: Dict[str, Any]) -> str:
        """
        Determine update priority

        Args:
            update_info: Update information from check_updates

        Returns:
            Priority level: required, recommended, optional
        """
        priority = update_info.get("priority", "optional")

        if priority == "required":
            return "required"
        elif priority == "recommended":
            return "recommended"
        else:
            return "optional"

