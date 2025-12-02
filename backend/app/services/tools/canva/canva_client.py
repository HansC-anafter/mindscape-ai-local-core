"""
Canva Connect API client

HTTP client for interacting with Canva Connect API.
Handles authentication, token refresh, and API request/response.
"""

from typing import Dict, Any, Optional, List
import aiohttp
import asyncio
import logging
from datetime import datetime, timedelta

from backend.app.services.tools.base import ToolConnection
from backend.app.services.tools.canva.canva_schemas import (
    CanvaDesign,
    CanvaTextBlock,
    CanvaTemplate,
    CreateDesignRequest,
    UpdateTextBlocksRequest,
    ExportDesignRequest,
)

logger = logging.getLogger(__name__)


class CanvaAPIError(Exception):
    """Canva API error"""

    def __init__(self, message: str, status_code: Optional[int] = None, response_data: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data


class CanvaAPIClient:
    """
    Canva Connect API client

    Handles HTTP communication with Canva Connect API, including:
    - OAuth token management and refresh
    - API request/response handling
    - Error handling and retry logic
    """

    DEFAULT_BASE_URL = "https://api.canva.com/rest/v1"
    DEFAULT_TIMEOUT = 30

    def __init__(self, connection: ToolConnection):
        """
        Initialize Canva API client

        Args:
            connection: ToolConnection instance with Canva credentials
        """
        self.connection = connection
        self.base_url = (connection.base_url or self.DEFAULT_BASE_URL).rstrip("/")
        self.api_key = connection.api_key
        self.oauth_token = connection.oauth_token
        self.token_expires_at: Optional[datetime] = None

    async def _get_auth_headers(self) -> Dict[str, str]:
        """
        Get authentication headers for API requests

        Returns:
            Dictionary with Authorization header

        Raises:
            CanvaAPIError: If no valid authentication method available
        """
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        if self.oauth_token:
            headers["Authorization"] = f"Bearer {self.oauth_token}"
        elif self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        else:
            raise CanvaAPIError("No authentication credentials provided (api_key or oauth_token required)")

        return headers

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        retry_count: int = 3,
    ) -> Dict[str, Any]:
        """
        Make HTTP request to Canva API

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint path (without base URL)
            params: Query parameters
            json_data: JSON request body
            retry_count: Number of retry attempts

        Returns:
            JSON response data

        Raises:
            CanvaAPIError: If API request fails
        """
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        headers = await self._get_auth_headers()

        last_error = None
        for attempt in range(retry_count):
            try:
                timeout = aiohttp.ClientTimeout(total=self.DEFAULT_TIMEOUT)
                async with aiohttp.ClientSession() as session:
                    async with session.request(
                        method=method,
                        url=url,
                        headers=headers,
                        params=params,
                        json=json_data,
                        timeout=timeout,
                    ) as response:
                        response_data = await response.json() if response.content_type == "application/json" else await response.text()

                        if response.status == 401 and attempt < retry_count - 1:
                            logger.warning(f"Authentication failed, attempting token refresh (attempt {attempt + 1}/{retry_count})")
                            await self._refresh_token()
                            headers = await self._get_auth_headers()
                            continue

                        if response.status >= 400:
                            error_msg = response_data.get("message", "Unknown error") if isinstance(response_data, dict) else str(response_data)
                            raise CanvaAPIError(
                                f"Canva API error: {error_msg}",
                                status_code=response.status,
                                response_data=response_data if isinstance(response_data, dict) else None,
                            )

                        return response_data if isinstance(response_data, dict) else {"data": response_data}

            except aiohttp.ClientError as e:
                last_error = e
                if attempt < retry_count - 1:
                    logger.warning(f"Network error, retrying (attempt {attempt + 1}/{retry_count}): {e}")
                    await asyncio.sleep(1 * (attempt + 1))
                    continue
                raise CanvaAPIError(f"Network error: {str(e)}")

        if last_error:
            raise CanvaAPIError(f"Request failed after {retry_count} attempts: {str(last_error)}")

    async def _refresh_token(self) -> None:
        """
        Refresh OAuth token

        Note: Implementation depends on Canva OAuth flow.
        This is a placeholder for token refresh logic.
        """
        if not self.oauth_token:
            raise CanvaAPIError("Cannot refresh token: no OAuth token available")

        logger.info("Refreshing OAuth token")
        try:
            refresh_response = await self._make_request(
                method="POST",
                endpoint="/oauth/token",
                json_data={
                    "grant_type": "refresh_token",
                    "refresh_token": self.oauth_token,
                },
            )
            self.oauth_token = refresh_response.get("access_token")
            expires_in = refresh_response.get("expires_in", 3600)
            self.token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
            logger.info("OAuth token refreshed successfully")
        except Exception as e:
            logger.error(f"Failed to refresh OAuth token: {e}")
            raise CanvaAPIError(f"Token refresh failed: {str(e)}")

    async def create_design(self, template_id: str, brand_id: Optional[str] = None, title: Optional[str] = None) -> CanvaDesign:
        """
        Create a new design from a template

        Args:
            template_id: Template ID
            brand_id: Optional brand ID
            title: Optional design title

        Returns:
            CanvaDesign instance

        Raises:
            CanvaAPIError: If design creation fails
        """
        request_data: Dict[str, Any] = {"template_id": template_id}
        if brand_id:
            request_data["brand_id"] = brand_id
        if title:
            request_data["title"] = title

        response = await self._make_request(
            method="POST",
            endpoint="/designs",
            json_data=request_data,
        )

        design_data = response.get("design") or response
        return CanvaDesign(**design_data)

    async def get_design(self, design_id: str) -> CanvaDesign:
        """
        Get design information

        Args:
            design_id: Design ID

        Returns:
            CanvaDesign instance

        Raises:
            CanvaAPIError: If design retrieval fails
        """
        response = await self._make_request(
            method="GET",
            endpoint=f"/designs/{design_id}",
        )

        design_data = response.get("design") or response
        return CanvaDesign(**design_data)

    async def list_templates(self, brand_id: Optional[str] = None, limit: int = 20, offset: int = 0) -> List[CanvaTemplate]:
        """
        List available templates

        Args:
            brand_id: Optional brand ID to filter templates
            limit: Maximum number of templates to return
            offset: Pagination offset

        Returns:
            List of CanvaTemplate instances

        Raises:
            CanvaAPIError: If template listing fails
        """
        params: Dict[str, Any] = {"limit": limit, "offset": offset}
        if brand_id:
            params["brand_id"] = brand_id

        response = await self._make_request(
            method="GET",
            endpoint="/templates",
            params=params,
        )

        templates_data = response.get("templates") or response.get("data") or []
        return [CanvaTemplate(**template) for template in templates_data]

    async def update_text_block(self, design_id: str, block_id: str, text: str) -> CanvaTextBlock:
        """
        Update a text block in a design

        Args:
            design_id: Design ID
            block_id: Text block ID
            text: New text content

        Returns:
            Updated CanvaTextBlock instance

        Raises:
            CanvaAPIError: If text update fails
        """
        response = await self._make_request(
            method="PUT",
            endpoint=f"/designs/{design_id}/text-blocks/{block_id}",
            json_data={"text": text},
        )

        block_data = response.get("text_block") or response
        return CanvaTextBlock(**block_data)

    async def update_text_blocks(self, design_id: str, text_blocks: List[Dict[str, str]]) -> List[CanvaTextBlock]:
        """
        Update multiple text blocks in a design

        Args:
            design_id: Design ID
            text_blocks: List of text block updates, each with 'block_id' and 'text'

        Returns:
            List of updated CanvaTextBlock instances

        Raises:
            CanvaAPIError: If text updates fail
        """
        updates = [{"block_id": block["block_id"], "text": block["text"]} for block in text_blocks]

        response = await self._make_request(
            method="PUT",
            endpoint=f"/designs/{design_id}/text-blocks/batch",
            json_data={"updates": updates},
        )

        blocks_data = response.get("text_blocks") or response.get("data") or []
        return [CanvaTextBlock(**block) for block in blocks_data]

    async def export_design(self, design_id: str, format: str = "PNG", scale: Optional[float] = None) -> Dict[str, Any]:
        """
        Export a design as an image or PDF

        Args:
            design_id: Design ID
            format: Export format (PNG, JPG, PDF)
            scale: Optional scale factor (0.1 to 4.0)

        Returns:
            Dictionary with export information (url, status, etc.)

        Raises:
            CanvaAPIError: If export fails
        """
        request_data: Dict[str, Any] = {"format": format.upper()}
        if scale is not None:
            request_data["scale"] = scale

        response = await self._make_request(
            method="POST",
            endpoint=f"/designs/{design_id}/exports",
            json_data=request_data,
        )

        return response.get("export") or response

    async def validate_connection(self) -> bool:
        """
        Validate Canva API connection

        Returns:
            True if connection is valid, False otherwise
        """
        try:
            await self.list_templates(limit=1)
            return True
        except Exception as e:
            logger.error(f"Canva connection validation failed: {e}")
            return False
