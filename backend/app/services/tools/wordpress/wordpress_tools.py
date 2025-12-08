"""
WordPress Tools Collection

Uses the MindscapeTool interface, splitting WordPress operations into multiple focused tool classes.
Each tool corresponds to a specific WordPress operation.

Design Principles:
- Single Responsibility: Each tool does one thing
- Standardized Schema: Uses ToolMetadata definition
- Type Safety: Complete type hints
- Unified Error Handling: Uses safe_execute wrapper
"""
from typing import Dict, Any, List
import aiohttp
from base64 import b64encode
import os

from backend.app.services.tools.base import MindscapeTool, ToolConnection
from backend.app.services.tools.schemas import (
    ToolMetadata,
    ToolCategory,
    ToolSourceType,
    ToolDangerLevel,
    create_simple_tool_metadata
)


# ============================================
# Shared WordPress client utilities
# ============================================

def _init_wp_client_from_connection(connection: ToolConnection) -> tuple[str, str | None]:
    """
    Initialize WordPress REST API client from connection

    Returns:
        Tuple of (wp_base_url, auth_header)
    """
    wp_base_url = (
        connection.base_url or
        os.getenv("WORDPRESS_URL", "http://wordpress:80")
    ).rstrip('/')

    wp_username = (
        connection.api_key or
        os.getenv("WORDPRESS_USERNAME", "admin")
    )

    wp_password = (
        connection.api_secret or
        os.getenv("WORDPRESS_APPLICATION_PASSWORD", "")
    )

    if wp_username and wp_password:
        credentials = f"{wp_username}:{wp_password}"
        token = b64encode(credentials.encode()).decode()
        auth_header = f"Basic {token}"
    else:
        auth_header = None

    return wp_base_url, auth_header


async def validate_wp_connection(connection: ToolConnection) -> bool:
    """
    Validate WordPress REST API connection

    Args:
        connection: WordPress connection configuration

    Returns:
        True if connection is valid, False otherwise
    """
    try:
        wp_base_url, auth_header = _init_wp_client_from_connection(connection)
        async with aiohttp.ClientSession() as session:
            headers = {}
            if auth_header:
                headers["Authorization"] = auth_header

            url = f"{wp_base_url}/wp-json/wp/v2"
            async with session.get(
                url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=5)
            ) as response:
                return response.status == 200
    except Exception:
        return False


class WordPressListPostsTool(MindscapeTool):
    """List WordPress posts"""

    def __init__(self, connection: ToolConnection):
        metadata = create_simple_tool_metadata(
            name="wordpress.list_posts",
            description="List WordPress posts with pagination, status filtering, and search",
            category=ToolCategory.CONTENT,
            source_type=ToolSourceType.LOCAL,
            danger_level=ToolDangerLevel.SAFE,
            properties={
                "per_page": {
                    "type": "integer",
                    "description": "Number of posts per page",
                    "default": 10,
                    "minimum": 1,
                    "maximum": 100
                },
                "page": {
                    "type": "integer",
                    "description": "Page number (starts from 1)",
                    "default": 1,
                    "minimum": 1
                },
                "status": {
                    "type": "string",
                    "description": "Post status filter",
                    "enum": ["publish", "draft", "pending", "private", "any"],
                    "default": "publish"
                },
                "search": {
                    "type": "string",
                    "description": "Search keyword (searches title and content)"
                }
            },
            required=[]
        )
        super().__init__(metadata)
        self.connection = connection
        self._init_wp_client()

    def _init_wp_client(self):
        """Initialize WordPress REST API client"""
        self.wp_base_url, self.auth_header = _init_wp_client_from_connection(self.connection)

    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute: List WordPress posts

        Args:
            input_data: Validated input parameters

        Returns:
            {
                "success": True,
                "data": [...],  # list of posts
                "count": 10,
                "page": 1,
                "per_page": 10
            }
        """
        per_page = input_data.get("per_page", 10)
        page = input_data.get("page", 1)
        status = input_data.get("status", "publish")
        search = input_data.get("search")

        async with aiohttp.ClientSession() as session:
            headers = {"Content-Type": "application/json"}
            if self.auth_header:
                headers["Authorization"] = self.auth_header

            url = f"{self.wp_base_url}/wp-json/wp/v2/posts"
            params = {
                "per_page": per_page,
                "page": page,
                "status": status
            }
            if search:
                params["search"] = search

            async with session.get(
                url,
                headers=headers,
                params=params,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status == 200:
                    posts = await response.json()
                    return {
                        "success": True,
                        "data": posts,
                        "count": len(posts),
                        "page": page,
                        "per_page": per_page
                    }
                else:
                    error_text = await response.text()
                    raise Exception(
                        f"WordPress API error {response.status}: {error_text}"
                    )


class WordPressGetPostTool(MindscapeTool):
    """Get a single WordPress post"""

    def __init__(self, connection: ToolConnection):
        metadata = create_simple_tool_metadata(
            name="wordpress.get_post",
            description="Get complete information of a WordPress post by ID",
            category=ToolCategory.CONTENT,
            source_type=ToolSourceType.LOCAL,
            danger_level=ToolDangerLevel.SAFE,
            properties={
                "post_id": {
                    "type": "integer",
                    "description": "Post ID",
                    "minimum": 1
                }
            },
            required=["post_id"]
        )
        super().__init__(metadata)
        self.connection = connection
        self._init_wp_client()

    def _init_wp_client(self):
        """Same as WordPressListPostsTool"""
        self.wp_base_url, self.auth_header = _init_wp_client_from_connection(self.connection)

    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute: Get post"""
        post_id = input_data["post_id"]

        async with aiohttp.ClientSession() as session:
            headers = {}
            if self.auth_header:
                headers["Authorization"] = self.auth_header

            url = f"{self.wp_base_url}/wp-json/wp/v2/posts/{post_id}"

            async with session.get(
                url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status == 200:
                    post = await response.json()
                    return {
                        "success": True,
                        "data": post
                    }
                else:
                    error_text = await response.text()
                    raise Exception(
                        f"Failed to get post {post_id}: {response.status} - {error_text}"
                    )


class WordPressCreateDraftTool(MindscapeTool):
    """Create a WordPress draft post"""

    def __init__(self, connection: ToolConnection):
        metadata = create_simple_tool_metadata(
            name="wordpress.create_draft",
            description="Create a draft post in WordPress (not published, requires manual review before publishing)",
            category=ToolCategory.CONTENT,
            source_type=ToolSourceType.LOCAL,
            danger_level=ToolDangerLevel.SAFE,
            properties={
                "title": {
                    "type": "string",
                    "description": "Post title",
                },
                "content": {
                    "type": "string",
                    "description": "Post content (HTML supported)",
                },
                "excerpt": {
                    "type": "string",
                    "description": "Post excerpt"
                },
                "meta": {
                    "type": "object",
                    "description": "Custom meta fields"
                }
            },
            required=["title", "content"]
        )
        super().__init__(metadata)
        self.connection = connection
        self._init_wp_client()

    def _init_wp_client(self):
        """Same as above"""
        self.wp_base_url = (
            self.connection.base_url or
            os.getenv("WORDPRESS_URL", "http://wordpress:80")
        ).rstrip('/')
        self.wp_username = self.connection.api_key or os.getenv("WORDPRESS_USERNAME", "admin")
        self.wp_password = self.connection.api_secret or os.getenv("WORDPRESS_APPLICATION_PASSWORD", "")

        if self.wp_username and self.wp_password:
            credentials = f"{self.wp_username}:{self.wp_password}"
            token = b64encode(credentials.encode()).decode()
            self.auth_header = f"Basic {token}"
        else:
            self.auth_header = None

    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute: Create draft"""
        title = input_data["title"]
        content = input_data["content"]
        excerpt = input_data.get("excerpt", "")
        meta = input_data.get("meta", {})

        async with aiohttp.ClientSession() as session:
            headers = {"Content-Type": "application/json"}
            if self.auth_header:
                headers["Authorization"] = self.auth_header

            url = f"{self.wp_base_url}/wp-json/wp/v2/posts"
            payload = {
                "title": title,
                "content": content,
                "status": "draft",  # Force set to draft
            }

            if excerpt:
                payload["excerpt"] = excerpt
            if meta:
                payload["meta"] = meta

            async with session.post(
                url,
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=15)
            ) as response:
                if response.status in [200, 201]:
                    post = await response.json()
                    return {
                        "success": True,
                        "data": post,
                        "post_id": post["id"],
                        "edit_url": post.get("link")
                    }
                else:
                    error_text = await response.text()
                    raise Exception(
                        f"Failed to create draft: {response.status} - {error_text}"
                    )


class WordPressUpdatePostTool(MindscapeTool):
    """Update WordPress post"""

    def __init__(self, connection: ToolConnection):
        metadata = create_simple_tool_metadata(
            name="wordpress.update_post",
            description="Update existing WordPress post content, title, or other attributes",
            category=ToolCategory.CONTENT,
            source_type=ToolSourceType.LOCAL,
            danger_level=ToolDangerLevel.MODERATE,  # Content modification has moderate risk
            properties={
                "post_id": {
                    "type": "integer",
                    "description": "Post ID to update",
                    "minimum": 1
                },
                "title": {
                    "type": "string",
                    "description": "New post title (optional)"
                },
                "content": {
                    "type": "string",
                    "description": "New post content (optional)"
                },
                "excerpt": {
                    "type": "string",
                    "description": "New post excerpt (optional)"
                },
                "status": {
                    "type": "string",
                    "description": "Post status (optional)",
                    "enum": ["draft", "pending", "publish"]
                }
            },
            required=["post_id"]
        )
        super().__init__(metadata)
        self.connection = connection
        self._init_wp_client()

    def _init_wp_client(self):
        """Same as above"""
        self.wp_base_url = (
            self.connection.base_url or
            os.getenv("WORDPRESS_URL", "http://wordpress:80")
        ).rstrip('/')
        self.wp_username = self.connection.api_key or os.getenv("WORDPRESS_USERNAME", "admin")
        self.wp_password = self.connection.api_secret or os.getenv("WORDPRESS_APPLICATION_PASSWORD", "")

        if self.wp_username and self.wp_password:
            credentials = f"{self.wp_username}:{self.wp_password}"
            token = b64encode(credentials.encode()).decode()
            self.auth_header = f"Basic {token}"
        else:
            self.auth_header = None

    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute: Update post"""
        post_id = input_data["post_id"]

        # Build update payload (only include provided fields)
        payload = {}
        if "title" in input_data:
            payload["title"] = input_data["title"]
        if "content" in input_data:
            payload["content"] = input_data["content"]
        if "excerpt" in input_data:
            payload["excerpt"] = input_data["excerpt"]
        if "status" in input_data:
            payload["status"] = input_data["status"]

        if not payload:
            raise ValueError("At least one field to update must be provided")

        async with aiohttp.ClientSession() as session:
            headers = {"Content-Type": "application/json"}
            if self.auth_header:
                headers["Authorization"] = self.auth_header

            url = f"{self.wp_base_url}/wp-json/wp/v2/posts/{post_id}"

            async with session.post(
                url,
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=15)
            ) as response:
                if response.status == 200:
                    post = await response.json()
                    return {
                        "success": True,
                        "data": post,
                        "post_id": post["id"]
                    }
                else:
                    error_text = await response.text()
                    raise Exception(
                        f"Failed to update post: {response.status} - {error_text}"
                    )


class WordPressListOrdersTool(MindscapeTool):
    """List WooCommerce orders"""

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
                    "maximum": 100
                },
                "page": {
                    "type": "integer",
                    "description": "Page number",
                    "default": 1
                },
                "status": {
                    "type": "string",
                    "description": "Order status filter",
                    "enum": ["pending", "processing", "completed", "cancelled", "refunded", "any"]
                },
                "after": {
                    "type": "string",
                    "description": "Start date (ISO 8601 format)"
                },
                "before": {
                    "type": "string",
                    "description": "End date (ISO 8601 format)"
                }
            },
            required=[]
        )
        super().__init__(metadata)
        self.connection = connection
        self._init_wp_client()

    def _init_wp_client(self):
        """Same as above"""
        self.wp_base_url = (
            self.connection.base_url or
            os.getenv("WORDPRESS_URL", "http://wordpress:80")
        ).rstrip('/')
        self.wp_username = self.connection.api_key or os.getenv("WORDPRESS_USERNAME", "admin")
        self.wp_password = self.connection.api_secret or os.getenv("WORDPRESS_APPLICATION_PASSWORD", "")

        if self.wp_username and self.wp_password:
            credentials = f"{self.wp_username}:{self.wp_password}"
            token = b64encode(credentials.encode()).decode()
            self.auth_header = f"Basic {token}"
        else:
            self.auth_header = None

    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute: List orders"""
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
            params = {
                "per_page": per_page,
                "page": page
            }
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
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status == 200:
                    orders = await response.json()
                    return {
                        "success": True,
                        "data": orders,
                        "count": len(orders)
                    }
                else:
                    error_text = await response.text()
                    raise Exception(
                        f"WooCommerce API error: {response.status} - {error_text}"
                    )


class WordPressUpdateOrderStatusTool(MindscapeTool):
    """Update WooCommerce order status (high-risk operation)"""

    def __init__(self, connection: ToolConnection):
        metadata = create_simple_tool_metadata(
            name="wordpress.update_order_status",
            description="Update WooCommerce order status (high-risk operation, may affect payment and logistics)",
            category=ToolCategory.COMMERCE,
            source_type=ToolSourceType.LOCAL,
            danger_level=ToolDangerLevel.DANGER,  # High risk operation
            properties={
                "order_id": {
                    "type": "integer",
                    "description": "Order ID",
                    "minimum": 1
                },
                "status": {
                    "type": "string",
                    "description": "New order status",
                    "enum": ["pending", "processing", "completed", "cancelled", "refunded"]
                }
            },
            required=["order_id", "status"]
        )
        super().__init__(metadata)
        self.connection = connection
        self._init_wp_client()

    def _init_wp_client(self):
        """Same as above"""
        self.wp_base_url = (
            self.connection.base_url or
            os.getenv("WORDPRESS_URL", "http://wordpress:80")
        ).rstrip('/')
        self.wp_username = self.connection.api_key or os.getenv("WORDPRESS_USERNAME", "admin")
        self.wp_password = self.connection.api_secret or os.getenv("WORDPRESS_APPLICATION_PASSWORD", "")

        if self.wp_username and self.wp_password:
            credentials = f"{self.wp_username}:{self.wp_password}"
            token = b64encode(credentials.encode()).decode()
            self.auth_header = f"Basic {token}"
        else:
            self.auth_header = None

    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute: Update order status

        Note: This operation should require user confirmation at the UI layer
        """
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
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status == 200:
                    order = await response.json()
                    return {
                        "success": True,
                        "data": order,
                        "message": f"Order #{order_id} status updated to {status}"
                    }
                else:
                    error_text = await response.text()
                    raise Exception(
                        f"Failed to update order status: {response.status} - {error_text}"
                    )


class WordPressCallPluginEndpointTool(MindscapeTool):
    """Call custom WordPress plugin endpoint"""

    def __init__(self, connection: ToolConnection):
        metadata = create_simple_tool_metadata(
            name="wordpress.call_plugin_endpoint",
            description="Call custom WordPress plugin endpoint (for SEO plugins, forms, etc.)",
            category=ToolCategory.INTEGRATION,
            source_type=ToolSourceType.LOCAL,
            danger_level=ToolDangerLevel.MODERATE,  # Custom endpoints may have varying risk levels
            properties={
                "plugin_name": {
                    "type": "string",
                    "description": "Plugin namespace (e.g., 'mindscape', 'yoast')",
                },
                "endpoint": {
                    "type": "string",
                    "description": "Endpoint path (e.g., 'analyze', 'submit_form')",
                },
                "payload": {
                    "type": "object",
                    "description": "Request payload as JSON object",
                    "default": {}
                }
            },
            required=["plugin_name", "endpoint"]
        )
        super().__init__(metadata)
        self.connection = connection
        self._init_wp_client()

    def _init_wp_client(self):
        """Same as other tools"""
        self.wp_base_url, self.auth_header = _init_wp_client_from_connection(self.connection)

    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute: Call plugin endpoint

        Args:
            input_data: Validated input parameters

        Returns:
            {
                "success": True,
                "data": {...}  # Plugin response
            }
        """
        plugin_name = input_data["plugin_name"]
        endpoint = input_data["endpoint"]
        payload = input_data.get("payload", {})

        async with aiohttp.ClientSession() as session:
            headers = {"Content-Type": "application/json"}
            if self.auth_header:
                headers["Authorization"] = self.auth_header

            url = f"{self.wp_base_url}/wp-json/{plugin_name}/v1/{endpoint}"

            async with session.post(
                url,
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=15)
            ) as response:
                if response.status in [200, 201]:
                    result = await response.json()
                    return {
                        "success": True,
                        "data": result
                    }
                else:
                    error_text = await response.text()
                    raise Exception(
                        f"Plugin endpoint error {response.status}: {error_text}"
                    )


# ============================================
# Factory functions
# ============================================

def create_wordpress_tools(connection: ToolConnection) -> List[MindscapeTool]:
    """
    Create all WordPress tool instances

    Args:
        connection: WordPress connection configuration

    Returns:
        List of WordPress tools

    Example:
        >>> wp_conn = ToolConnection(
        ...     id="my-wp",
        ...     tool_type="wordpress",
        ...     base_url="https://mysite.com",
        ...     api_key="admin",
        ...     api_secret="app_password"
        ... )
        >>> tools = create_wordpress_tools(wp_conn)
        >>> print(f"Created {len(tools)} tools")
    """
    return [
        # Content management
        WordPressListPostsTool(connection),
        WordPressGetPostTool(connection),
        WordPressCreateDraftTool(connection),
        WordPressUpdatePostTool(connection),

        # E-commerce management
        WordPressListOrdersTool(connection),
        WordPressUpdateOrderStatusTool(connection),

        # Integration
        WordPressCallPluginEndpointTool(connection),
    ]


def get_wordpress_tool_by_name(
    connection: ToolConnection,
    tool_name: str
) -> MindscapeTool:
    """
    Get a specific WordPress tool by name

    Args:
        connection: WordPress connection
        tool_name: Tool name (e.g., "wordpress.list_posts")

    Returns:
        Tool instance

    Raises:
        ValueError: Unknown tool name
    """
    tool_map = {
        "wordpress.list_posts": WordPressListPostsTool,
        "wordpress.get_post": WordPressGetPostTool,
        "wordpress.create_draft": WordPressCreateDraftTool,
        "wordpress.update_post": WordPressUpdatePostTool,
        "wordpress.list_orders": WordPressListOrdersTool,
        "wordpress.update_order_status": WordPressUpdateOrderStatusTool,
        "wordpress.call_plugin_endpoint": WordPressCallPluginEndpointTool,
    }

    tool_class = tool_map.get(tool_name)
    if not tool_class:
        available = list(tool_map.keys())
        raise ValueError(
            f"Unknown tool name: {tool_name}. "
            f"Available tools: {', '.join(available)}"
        )

    return tool_class(connection)
