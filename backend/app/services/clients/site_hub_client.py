"""
Site-Hub Client

Handles Site-Hub integration including:
- OIDC authentication
- Tenant management
- Permission verification
"""

import aiohttp
import logging
from typing import Dict, Any, Optional
from urllib.parse import urljoin

logger = logging.getLogger(__name__)


class SiteHubClient:
    """
    Site-Hub Client

    Connects to Site-Hub for:
    - Identity authentication (OIDC)
    - Tenant information retrieval
    - Permission verification
    """

    def __init__(self, base_url: str, api_token: Optional[str] = None):
        """
        Initialize Site-Hub client

        Args:
            base_url: Site-Hub API URL
            api_token: API Token (optional, for service-to-service calls)
        """
        self.base_url = base_url.rstrip("/")
        self.api_token = api_token
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        """Close HTTP session"""
        if self._session and not self._session.closed:
            await self._session.close()

    async def authenticate(self, token: str) -> Dict[str, Any]:
        """
        Verify OIDC Token

        Args:
            token: OIDC Token (JWT)

        Returns:
            User info and tenant list

        Raises:
            Exception: Authentication failed
        """
        url = urljoin(self.base_url, "/api/v1/auth/verify")
        headers = {"Authorization": f"Bearer {token}"}

        try:
            session = await self._get_session()
            async with session.post(url, headers=headers) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Authentication failed: {response.status} - {error_text}")

                return await response.json()

        except aiohttp.ClientError as e:
            logger.error(f"Site-Hub connection error: {e}")
            raise Exception(f"Failed to connect to Site-Hub: {str(e)}")

    async def get_tenant_info(self, tenant_id: str) -> Dict[str, Any]:
        """
        Get tenant information

        Args:
            tenant_id: Tenant ID

        Returns:
            Tenant details

        Raises:
            Exception: Query failed
        """
        url = urljoin(self.base_url, f"/api/v1/tenants/{tenant_id}")
        headers = {}
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"

        try:
            session = await self._get_session()
            async with session.get(url, headers=headers) as response:
                if response.status == 404:
                    raise Exception(f"Tenant not found: {tenant_id}")
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Failed to get tenant info: {response.status} - {error_text}")

                return await response.json()

        except aiohttp.ClientError as e:
            logger.error(f"Site-Hub connection error: {e}")
            raise Exception(f"Failed to connect to Site-Hub: {str(e)}")

    async def check_permission(
        self,
        user_id: str,
        tenant_id: str,
        action: str,
        resource: Optional[str] = None
    ) -> bool:
        """
        Check user permission

        Args:
            user_id: User ID
            tenant_id: Tenant ID
            action: Action type (e.g., "read", "write", "execute")
            resource: Resource identifier (optional)

        Returns:
            Whether user has permission

        Raises:
            Exception: Check failed
        """
        url = urljoin(self.base_url, "/api/v1/auth/check-permission")
        headers = {}
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"

        payload = {
            "user_id": user_id,
            "tenant_id": tenant_id,
            "action": action,
            "resource": resource
        }

        try:
            session = await self._get_session()
            async with session.post(url, json=payload, headers=headers) as response:
                if response.status != 200:
                    return False

                result = await response.json()
                return result.get("allowed", False)

        except aiohttp.ClientError as e:
            logger.error(f"Site-Hub connection error: {e}")
            return False

    async def health_check(self) -> bool:
        """
        Check Site-Hub health status

        Returns:
            Whether service is healthy
        """
        url = urljoin(self.base_url, "/health")

        try:
            session = await self._get_session()
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                return response.status == 200
        except Exception:
            return False

    def is_configured(self) -> bool:
        """Check if client is configured"""
        return bool(self.base_url)



