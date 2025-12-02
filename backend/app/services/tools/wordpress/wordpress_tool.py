"""
WordPress tool implementation.

This tool provides access to WordPress REST API and enables AI agents to:
- List and read posts
- Create draft posts
- Update posts (with safety checks)
- Manage WooCommerce orders (high-risk operations)
- Call custom plugin endpoints
"""
import aiohttp
import os
from typing import Dict, Any, List, Optional
from base64 import b64encode

from backend.app.services.tools.base import Tool, ToolConnection


class WordPressTool(Tool):
    """WordPress integration tool - Core capability"""

    # High-risk actions that require user confirmation
    HIGH_RISK_ACTIONS = [
        "update_order_status",  # May affect payments
        "delete_post",  # Delete content
        "publish_post",  # Publish content (needs confirmation)
        "refund_order",  # Refund
    ]

    def __init__(self, connection: ToolConnection):
        super().__init__(connection)
        # WordPress REST API base URL
        self.wp_base_url = (connection.base_url or os.getenv("WORDPRESS_URL", "http://wordpress:80")).rstrip('/')
        self.wp_username = connection.api_key or os.getenv("WORDPRESS_USERNAME", "admin")
        self.wp_password = connection.api_secret or os.getenv("WORDPRESS_APPLICATION_PASSWORD", "")

        # Basic auth header
        if self.wp_username and self.wp_password:
            credentials = f"{self.wp_username}:{self.wp_password}"
            token = b64encode(credentials.encode()).decode()
            self.auth_header = f"Basic {token}"
        else:
            self.auth_header = None

    async def execute(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute WordPress action"""
        if action == "list_posts":
            return await self._list_posts(params)
        elif action == "get_post":
            return await self._get_post(params.get("id"))
        elif action == "create_draft":
            return await self._create_draft(params)
        elif action == "update_post":
            return await self._update_post(params.get("id"), params.get("patch", {}))
        elif action == "list_orders":  # WooCommerce
            return await self._list_orders(params)
        elif action == "update_order_status":  # High-risk, requires confirmation
            return await self._update_order_status(params.get("id"), params.get("status"))
        elif action == "call_plugin_endpoint":
            return await self._call_plugin_endpoint(
                params.get("plugin"),
                params.get("endpoint"),
                params.get("payload", {})
            )
        else:
            raise ValueError(f"Unknown action: {action}")

    def get_available_actions(self) -> List[str]:
        """Get list of available WordPress actions"""
        return [
            "list_posts",
            "get_post",
            "create_draft",
            "update_post",
            "list_orders",  # WooCommerce
            "update_order_status",  # High-risk
            "call_plugin_endpoint",  # For SEO plugins, forms, etc.
        ]

    async def validate_connection(self) -> bool:
        """Validate WordPress connection"""
        try:
            async with aiohttp.ClientSession() as session:
                headers = {}
                if self.auth_header:
                    headers["Authorization"] = self.auth_header

                url = f"{self.wp_base_url}/wp-json/wp/v2"
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as response:
                    return response.status == 200
        except Exception:
            return False

    async def _list_posts(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List WordPress posts"""
        async with aiohttp.ClientSession() as session:
            headers = {"Content-Type": "application/json"}
            if self.auth_header:
                headers["Authorization"] = self.auth_header

            url = f"{self.wp_base_url}/wp-json/wp/v2/posts"

            # Add query parameters
            query_params = {}
            if "per_page" in params:
                query_params["per_page"] = params["per_page"]
            if "page" in params:
                query_params["page"] = params["page"]
            if "status" in params:
                query_params["status"] = params["status"]
            if "search" in params:
                query_params["search"] = params["search"]

            async with session.get(url, headers=headers, params=query_params) as response:
                if response.status == 200:
                    posts = await response.json()
                    return {"success": True, "data": posts, "count": len(posts)}
                else:
                    error_text = await response.text()
                    return {"success": False, "error": f"HTTP {response.status}: {error_text}"}

    async def _get_post(self, post_id: int) -> Dict[str, Any]:
        """Get a single post by ID"""
        async with aiohttp.ClientSession() as session:
            headers = {}
            if self.auth_header:
                headers["Authorization"] = self.auth_header

            url = f"{self.wp_base_url}/wp-json/wp/v2/posts/{post_id}"
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    post = await response.json()
                    return {"success": True, "data": post}
                else:
                    error_text = await response.text()
                    return {"success": False, "error": f"HTTP {response.status}: {error_text}"}

    async def _create_draft(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Create a draft post in WordPress"""
        async with aiohttp.ClientSession() as session:
            headers = {"Content-Type": "application/json"}
            if self.auth_header:
                headers["Authorization"] = self.auth_header

            url = f"{self.wp_base_url}/wp-json/wp/v2/posts"

            payload = {
                "title": params.get("title", ""),
                "content": params.get("content", ""),
                "status": "draft",  # Always create as draft for safety
            }

            # Add meta fields if provided
            if "meta" in params:
                payload["meta"] = params["meta"]

            async with session.post(url, headers=headers, json=payload) as response:
                if response.status in [200, 201]:
                    post = await response.json()
                    return {"success": True, "data": post}
                else:
                    error_text = await response.text()
                    return {"success": False, "error": f"HTTP {response.status}: {error_text}"}

    async def _update_post(self, post_id: int, patch: Dict[str, Any]) -> Dict[str, Any]:
        """Update an existing post"""
        async with aiohttp.ClientSession() as session:
            headers = {"Content-Type": "application/json"}
            if self.auth_header:
                headers["Authorization"] = self.auth_header

            url = f"{self.wp_base_url}/wp-json/wp/v2/posts/{post_id}"
            async with session.post(url, headers=headers, json=patch) as response:
                if response.status == 200:
                    post = await response.json()
                    return {"success": True, "data": post}
                else:
                    error_text = await response.text()
                    return {"success": False, "error": f"HTTP {response.status}: {error_text}"}

    async def _list_orders(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List WooCommerce orders"""
        async with aiohttp.ClientSession() as session:
            headers = {}
            if self.auth_header:
                headers["Authorization"] = self.auth_header

            url = f"{self.wp_base_url}/wp-json/wc/v3/orders"

            query_params = {}
            if "per_page" in params:
                query_params["per_page"] = params["per_page"]
            if "page" in params:
                query_params["page"] = params["page"]
            if "status" in params:
                query_params["status"] = params["status"]
            if "after" in params:
                query_params["after"] = params["after"]
            if "before" in params:
                query_params["before"] = params["before"]

            async with session.get(url, headers=headers, params=query_params) as response:
                if response.status == 200:
                    orders = await response.json()
                    return {"success": True, "data": orders, "count": len(orders)}
                else:
                    error_text = await response.text()
                    return {"success": False, "error": f"HTTP {response.status}: {error_text}"}

    async def _update_order_status(self, order_id: int, status: str) -> Dict[str, Any]:
        """Update order status (HIGH RISK - requires confirmation)"""
        # This should only be called after user confirmation
        async with aiohttp.ClientSession() as session:
            headers = {"Content-Type": "application/json"}
            if self.auth_header:
                headers["Authorization"] = self.auth_header

            url = f"{self.wp_base_url}/wp-json/wc/v3/orders/{order_id}"
            payload = {"status": status}

            async with session.put(url, headers=headers, json=payload) as response:
                if response.status == 200:
                    order = await response.json()
                    return {"success": True, "data": order}
                else:
                    error_text = await response.text()
                    return {"success": False, "error": f"HTTP {response.status}: {error_text}"}

    async def _call_plugin_endpoint(self, plugin_name: str, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Call custom plugin endpoint (for SEO plugins, forms, etc.)"""
        async with aiohttp.ClientSession() as session:
            headers = {"Content-Type": "application/json"}
            if self.auth_header:
                headers["Authorization"] = self.auth_header

            # Support for custom plugin endpoints
            # Example: /wp-json/mindscape/v1/...
            url = f"{self.wp_base_url}/wp-json/{plugin_name}/v1/{endpoint}"

            async with session.post(url, headers=headers, json=payload) as response:
                if response.status in [200, 201]:
                    result = await response.json()
                    return {"success": True, "data": result}
                else:
                    error_text = await response.text()
                    return {"success": False, "error": f"HTTP {response.status}: {error_text}"}

