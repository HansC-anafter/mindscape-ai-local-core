"""WooCommerce WordPress MindscapeTool implementations."""

from __future__ import annotations

from typing import Any, Dict

import aiohttp

from backend.app.services.tools.base import MindscapeTool, ToolConnection
from backend.app.services.tools.schemas import (
    ToolCategory,
    ToolDangerLevel,
    ToolSourceType,
    create_simple_tool_metadata,
)
from backend.app.services.tools.wordpress.wordpress_client import (
    apply_wp_client_connection,
)


class WordPressListOrdersTool(MindscapeTool):
    """List WooCommerce orders."""

    def __init__(self, connection: ToolConnection):
        metadata = create_simple_tool_metadata(
            name="wordpress.list_orders",
            description="List WooCommerce orders with status and date range filtering",
            category=ToolCategory.COMMERCE,
            source_type=ToolSourceType.LOCAL,
            danger_level=ToolDangerLevel.SAFE,
            properties={
                "per_page": {
                    "type": "integer",
                    "description": "Number of orders per page",
                    "default": 10,
                    "minimum": 1,
                    "maximum": 100,
                },
                "page": {
                    "type": "integer",
                    "description": "Page number",
                    "default": 1,
                },
                "status": {
                    "type": "string",
                    "description": "Order status filter",
                    "enum": [
                        "pending",
                        "processing",
                        "completed",
                        "cancelled",
                        "refunded",
                        "any",
                    ],
                },
                "after": {
                    "type": "string",
                    "description": "Start date (ISO 8601 format)",
                },
                "before": {
                    "type": "string",
                    "description": "End date (ISO 8601 format)",
                },
            },
            required=[],
        )
        super().__init__(metadata)
        self.connection = connection
        self._init_wp_client()

    def _init_wp_client(self):
        """Initialize WordPress REST API client."""
        apply_wp_client_connection(self, self.connection)

    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute list orders."""
        per_page = input_data.get("per_page", 10)
        page = input_data.get("page", 1)
        status = input_data.get("status")
        after = input_data.get("after")
        before = input_data.get("before")

        async with aiohttp.ClientSession() as session:
            headers = {}
            if self.auth_header:
                headers["Authorization"] = self.auth_header

            url = f"{self.wp_base_url}/wp-json/wc/v3/orders"
            params = {"per_page": per_page, "page": page}
            if status:
                params["status"] = status
            if after:
                params["after"] = after
            if before:
                params["before"] = before

            async with session.get(
                url,
                headers=headers,
                params=params,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                if response.status == 200:
                    orders = await response.json()
                    return {"success": True, "data": orders, "count": len(orders)}
                error_text = await response.text()
                raise Exception(
                    f"WooCommerce API error: {response.status} - {error_text}"
                )


class WordPressUpdateOrderStatusTool(MindscapeTool):
    """Update WooCommerce order status."""

    def __init__(self, connection: ToolConnection):
        metadata = create_simple_tool_metadata(
            name="wordpress.update_order_status",
            description="Update WooCommerce order status (high-risk operation, may affect payment and logistics)",
            category=ToolCategory.COMMERCE,
            source_type=ToolSourceType.LOCAL,
            danger_level=ToolDangerLevel.DANGER,
            properties={
                "order_id": {
                    "type": "integer",
                    "description": "Order ID",
                    "minimum": 1,
                },
                "status": {
                    "type": "string",
                    "description": "New order status",
                    "enum": [
                        "pending",
                        "processing",
                        "completed",
                        "cancelled",
                        "refunded",
                    ],
                },
            },
            required=["order_id", "status"],
        )
        super().__init__(metadata)
        self.connection = connection
        self._init_wp_client()

    def _init_wp_client(self):
        """Initialize WordPress REST API client."""
        apply_wp_client_connection(self, self.connection)

    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute update order status."""
        order_id = input_data["order_id"]
        status = input_data["status"]

        async with aiohttp.ClientSession() as session:
            headers = {"Content-Type": "application/json"}
            if self.auth_header:
                headers["Authorization"] = self.auth_header

            url = f"{self.wp_base_url}/wp-json/wc/v3/orders/{order_id}"
            payload = {"status": status}

            async with session.put(
                url,
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                if response.status == 200:
                    order = await response.json()
                    return {
                        "success": True,
                        "data": order,
                        "message": f"Order #{order_id} status updated to {status}",
                    }
                error_text = await response.text()
                raise Exception(
                    "Failed to update order status: "
                    f"{response.status} - {error_text}"
                )
