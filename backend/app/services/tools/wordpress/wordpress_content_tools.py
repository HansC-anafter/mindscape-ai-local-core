"""WordPress content management MindscapeTool implementations."""

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


class WordPressListPostsTool(MindscapeTool):
    """List WordPress posts."""

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
                    "maximum": 100,
                },
                "page": {
                    "type": "integer",
                    "description": "Page number (starts from 1)",
                    "default": 1,
                    "minimum": 1,
                },
                "status": {
                    "type": "string",
                    "description": "Post status filter",
                    "enum": ["publish", "draft", "pending", "private", "any"],
                    "default": "publish",
                },
                "search": {
                    "type": "string",
                    "description": "Search keyword (searches title and content)",
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
        """Execute list posts."""
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
                "status": status,
            }
            if search:
                params["search"] = search

            async with session.get(
                url,
                headers=headers,
                params=params,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                if response.status == 200:
                    posts = await response.json()
                    return {
                        "success": True,
                        "data": posts,
                        "count": len(posts),
                        "page": page,
                        "per_page": per_page,
                    }
                error_text = await response.text()
                raise Exception(
                    f"WordPress API error {response.status}: {error_text}"
                )


class WordPressGetPostTool(MindscapeTool):
    """Get a single WordPress post."""

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
                    "minimum": 1,
                }
            },
            required=["post_id"],
        )
        super().__init__(metadata)
        self.connection = connection
        self._init_wp_client()

    def _init_wp_client(self):
        """Initialize WordPress REST API client."""
        apply_wp_client_connection(self, self.connection)

    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute get post."""
        post_id = input_data["post_id"]

        async with aiohttp.ClientSession() as session:
            headers = {}
            if self.auth_header:
                headers["Authorization"] = self.auth_header

            url = f"{self.wp_base_url}/wp-json/wp/v2/posts/{post_id}"
            async with session.get(
                url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                if response.status == 200:
                    post = await response.json()
                    return {"success": True, "data": post}
                error_text = await response.text()
                raise Exception(
                    f"Failed to get post {post_id}: {response.status} - {error_text}"
                )


class WordPressCreateDraftTool(MindscapeTool):
    """Create a WordPress draft post."""

    def __init__(self, connection: ToolConnection):
        metadata = create_simple_tool_metadata(
            name="wordpress.create_draft",
            description="Create a draft post in WordPress (not published, requires manual review before publishing)",
            category=ToolCategory.CONTENT,
            source_type=ToolSourceType.LOCAL,
            danger_level=ToolDangerLevel.SAFE,
            properties={
                "title": {"type": "string", "description": "Post title"},
                "content": {
                    "type": "string",
                    "description": "Post content (HTML supported)",
                },
                "excerpt": {"type": "string", "description": "Post excerpt"},
                "meta": {"type": "object", "description": "Custom meta fields"},
            },
            required=["title", "content"],
        )
        super().__init__(metadata)
        self.connection = connection
        self._init_wp_client()

    def _init_wp_client(self):
        """Initialize WordPress REST API client."""
        apply_wp_client_connection(self, self.connection)

    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute create draft."""
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
                "status": "draft",
            }

            if excerpt:
                payload["excerpt"] = excerpt
            if meta:
                payload["meta"] = meta

            async with session.post(
                url,
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as response:
                if response.status in [200, 201]:
                    post = await response.json()
                    return {
                        "success": True,
                        "data": post,
                        "post_id": post["id"],
                        "edit_url": post.get("link"),
                    }
                error_text = await response.text()
                raise Exception(
                    f"Failed to create draft: {response.status} - {error_text}"
                )


class WordPressUpdatePostTool(MindscapeTool):
    """Update WordPress post."""

    def __init__(self, connection: ToolConnection):
        metadata = create_simple_tool_metadata(
            name="wordpress.update_post",
            description="Update existing WordPress post content, title, or other attributes",
            category=ToolCategory.CONTENT,
            source_type=ToolSourceType.LOCAL,
            danger_level=ToolDangerLevel.MODERATE,
            properties={
                "post_id": {
                    "type": "integer",
                    "description": "Post ID to update",
                    "minimum": 1,
                },
                "title": {"type": "string", "description": "New post title (optional)"},
                "content": {
                    "type": "string",
                    "description": "New post content (optional)",
                },
                "excerpt": {
                    "type": "string",
                    "description": "New post excerpt (optional)",
                },
                "status": {
                    "type": "string",
                    "description": "Post status (optional)",
                    "enum": ["draft", "pending", "publish"],
                },
            },
            required=["post_id"],
        )
        super().__init__(metadata)
        self.connection = connection
        self._init_wp_client()

    def _init_wp_client(self):
        """Initialize WordPress REST API client."""
        apply_wp_client_connection(self, self.connection)

    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute update post."""
        post_id = input_data["post_id"]

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
                timeout=aiohttp.ClientTimeout(total=15),
            ) as response:
                if response.status == 200:
                    post = await response.json()
                    return {
                        "success": True,
                        "data": post,
                        "post_id": post["id"],
                    }
                error_text = await response.text()
                raise Exception(
                    f"Failed to update post: {response.status} - {error_text}"
                )
