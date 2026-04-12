"""
Cloud Registry API client.

Fetches channel_config and tokens from the Cloud Registry API.
Supports URL resolution from runtime-environments DB (mindscape_cloud_integration pattern).
"""

import os
import logging
import httpx
from typing import Dict, Any, Optional, Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class CloudRegistryClient:
    """Cloud Registry API client."""

    def __init__(self, registry_api_url: Optional[str] = None):
        if registry_api_url:
            self.registry_api_url = registry_api_url.rstrip("/")
        else:
            self.registry_api_url = os.getenv(
                "REGISTRY_API_URL",
                os.getenv("CLOUD_REGISTRY_API_URL", "http://registry-api:8000"),
            )
        self.service_token = os.getenv(
            "CLOUD_REGISTRY_SERVICE_TOKEN",
            os.getenv("CLOUD_REGISTRY_API_TOKEN", "cloud-registry-service-token"),
        )

    @classmethod
    async def from_runtime(
        cls,
        runtime_id: str,
        local_core_api_base: Optional[str] = None,
    ) -> "CloudRegistryClient":
        """Resolve registry URL from runtime-environments DB.

        Follows the same pattern as mindscape_cloud_integration's site_hub_client.py:
        query GET /api/v1/runtime-environments/{runtime_id}, then extract
        base URL from metadata.signature.base_url or config_url.
        """
        if not local_core_api_base:
            local_core_api_base = os.getenv(
                "LOCAL_CORE_API_BASE", "http://localhost:8000"
            ).rstrip("/")

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{local_core_api_base}/api/v1/runtime-environments/{runtime_id}"
            )
            resp.raise_for_status()
            runtime_data = resp.json()

        config_url = runtime_data.get("config_url", "")
        base_url = cls._extract_base_url(runtime_data, config_url)
        if not base_url:
            raise ValueError(
                f"Cannot determine registry URL from runtime {runtime_id}. "
                f"Ensure runtime has config_url or metadata.signature.base_url."
            )

        logger.info("Resolved registry URL from runtime %s: %s", runtime_id, base_url)
        return cls(registry_api_url=base_url)

    @staticmethod
    def _extract_base_url(
        runtime_data: Dict[str, Any], config_url: str
    ) -> Optional[str]:
        """Extract base URL from runtime environment data.

        Same logic as site_hub_client.get_site_hub_base_url:
        1. metadata.signature.base_url (full URL with path prefix)
        2. config_url (extract base, preserving path prefix)
        """
        metadata = runtime_data.get("metadata")
        if isinstance(metadata, dict):
            signature = metadata.get("signature")
            if isinstance(signature, dict):
                base_url = signature.get("base_url")
                if base_url:
                    return base_url.rstrip("/")

        if config_url:
            parsed = urlparse(config_url)
            path = parsed.path or ""
            base_path = path.split("/settings", 1)[0] if "/settings" in path else path
            normalized = base_path.rstrip("/")
            if normalized:
                return f"{parsed.scheme}://{parsed.netloc}{normalized}"
            return f"{parsed.scheme}://{parsed.netloc}"

        return None

    async def get_channel_config(
        self, channel_config_id: int, workspace_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Fetch a channel_config from the Cloud Registry API.

        Endpoint: GET /api/v1/channel_configs/{channel_config_id}
        Auth: service token (or workspace-bound auth in cloud registry)
        Permission check: validates workspace access to the channel_config_id

        Args:
            channel_config_id: ChannelConfig ID
            workspace_id: Workspace ID (optional, for permission checks)

        Returns:
            ChannelConfig payload
        """
        async with httpx.AsyncClient(timeout=10.0) as client:
            headers = {"X-Service-Auth": self.service_token}

            # If workspace_id is provided, pass as query param for permission checks.
            params = {}
            if workspace_id:
                params["workspace_id"] = workspace_id

            response = await client.get(
                f"{self.registry_api_url}/api/v1/channel_configs/{channel_config_id}",
                headers=headers,
                params=params,
            )

            if response.status_code == 404:
                raise ValueError(
                    f"Channel config {channel_config_id} not found. "
                    f"Please ensure the channel is bound in cloud registry first."
                )
            elif response.status_code == 403:
                raise ValueError(
                    f"Workspace {workspace_id} does not have permission to access "
                    f"channel config {channel_config_id}"
                )
            elif response.status_code != 200:
                raise Exception(
                    f"Failed to get channel config: {response.status_code} - {response.text}"
                )

            return response.json()

    async def get_access_token(
        self, channel_config_id: int, workspace_id: Optional[str] = None
    ) -> str:
        """
        Fetch an access_token from the Cloud Registry API.

        Args:
            channel_config_id: ChannelConfig ID
            workspace_id: Workspace ID (optional, for permission checks)

        Returns:
            Access token
        """
        config = await self.get_channel_config(channel_config_id, workspace_id)

        access_token = config.get("access_token")
        if not access_token:
            raise ValueError(
                f"Access token not found for channel config {channel_config_id}. "
                f"Please ensure OAuth authorization is completed in cloud registry."
            )

        # Validate token status.
        status = config.get("status")
        if status == "invalid_credentials" or status == "token_expired":
            raise ValueError(
                f"Token for channel config {channel_config_id} is {status}. "
                f"Please re-authorize in cloud registry."
            )

        return access_token

    async def get_app_secret(
        self, channel_config_id: int, workspace_id: Optional[str] = None
    ) -> Optional[str]:
        """
        Fetch app_secret (for appsecret_proof) via Cloud Registry.

        Endpoint: GET /api/v1/channel_configs/{id}/secret

        Args:
            channel_config_id: ChannelConfig ID
            workspace_id: Workspace ID (optional, for permission checks)

        Returns:
            App secret if available, otherwise None
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                headers = {"X-Service-Auth": self.service_token}
                params = {}
                if workspace_id:
                    params["workspace_id"] = workspace_id

                response = await client.get(
                    f"{self.registry_api_url}/api/v1/channel_configs/{channel_config_id}/secret",
                    headers=headers,
                    params=params,
                )

                if response.status_code == 200:
                    secret_data = response.json()
                    return secret_data.get("app_secret")
                elif response.status_code == 404:
                    # Secret not found; app_secret_proof will be skipped.
                    logger.warning(
                        f"App secret not found for channel config {channel_config_id}, "
                        f"app_secret_proof will not be used"
                    )
                    return None
                else:
                    logger.warning(
                        f"Failed to get app secret: {response.status_code}, "
                        f"app_secret_proof will not be used"
                    )
                    return None
        except Exception as e:
            logger.warning(
                f"Error getting app secret: {e}, app_secret_proof will not be used"
            )
            return None

    async def get_ig_business_account_id(
        self, channel_config_id: int, workspace_id: Optional[str] = None
    ) -> Optional[str]:
        """
        Fetch ig_business_account_id from channel_config.

        Args:
            channel_config_id: ChannelConfig ID
            workspace_id: Workspace ID (optional, for permission checks)

        Returns:
            ig_business_account_id if available, otherwise None
        """
        config = await self.get_channel_config(channel_config_id, workspace_id)

        # ig_business_account_id may be stored in channel_id or config.
        channel_id = config.get("channel_id")
        if channel_id and channel_id.startswith("ig_"):
            # channel_id already uses ig_business_account_id format
            return channel_id

        # Fallback: read from config blob.
        config_data = config.get("config", {})
        return config_data.get("ig_business_account_id")
