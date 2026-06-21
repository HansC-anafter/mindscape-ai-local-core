"""Repository and code-search GitHub tools."""

from typing import Any, Dict

import aiohttp

from backend.app.services.tools.base import MindscapeTool
from backend.app.services.tools.schemas import (
    ToolCategory,
    ToolInputSchema,
    ToolMetadata,
)


class GitHubListReposTool(MindscapeTool):
    """List repositories for authenticated user or organization."""

    def __init__(self, access_token: str):
        self.access_token = access_token
        self.base_url = "https://api.github.com"

        metadata = ToolMetadata(
            name="github_list_repos",
            description="List repositories for authenticated user or organization",
            input_schema=ToolInputSchema(
                type="object",
                properties={
                    "type": {
                        "type": "string",
                        "description": "Repository type filter (all, owner, member)",
                        "enum": ["all", "owner", "member"],
                        "default": "all",
                    },
                    "sort": {
                        "type": "string",
                        "description": "Sort by (created, updated, pushed, full_name)",
                        "enum": ["created", "updated", "pushed", "full_name"],
                        "default": "updated",
                    },
                    "direction": {
                        "type": "string",
                        "description": "Sort direction (asc, desc)",
                        "enum": ["asc", "desc"],
                        "default": "desc",
                    },
                    "per_page": {
                        "type": "integer",
                        "description": "Results per page (default: 30, max: 100)",
                        "default": 30,
                    },
                    "page": {
                        "type": "integer",
                        "description": "Page number",
                        "default": 1,
                    },
                },
                required=[],
            ),
            category=ToolCategory.INTEGRATION,
            source_type="builtin",
            provider="github",
            danger_level="low",
        )
        super().__init__(metadata)

    async def execute(
        self,
        type: str = "all",
        sort: str = "updated",
        direction: str = "desc",
        per_page: int = 30,
        page: int = 1,
    ) -> Dict[str, Any]:
        """List repositories."""
        url = f"{self.base_url}/user/repos"

        headers = {
            "Authorization": f"token {self.access_token}",
            "Accept": "application/vnd.github.v3+json",
        }

        params = {
            "type": type,
            "sort": sort,
            "direction": direction,
            "per_page": min(per_page, 100),
            "page": page,
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"GitHub API error: {response.status} - {error_text}")

                result = await response.json()

                return {
                    "success": True,
                    "repositories": result,
                    "count": len(result),
                }


class GitHubSearchCodeTool(MindscapeTool):
    """Search code in GitHub repositories."""

    def __init__(self, access_token: str):
        self.access_token = access_token
        self.base_url = "https://api.github.com"

        metadata = ToolMetadata(
            name="github_search_code",
            description="Search code in GitHub repositories",
            input_schema=ToolInputSchema(
                type="object",
                properties={
                    "q": {
                        "type": "string",
                        "description": "Search query (e.g., 'addClass in:file language:js')",
                    },
                    "sort": {
                        "type": "string",
                        "description": "Sort by (indexed)",
                        "enum": ["indexed"],
                        "default": "indexed",
                    },
                    "order": {
                        "type": "string",
                        "description": "Sort order (asc, desc)",
                        "enum": ["asc", "desc"],
                        "default": "desc",
                    },
                    "per_page": {
                        "type": "integer",
                        "description": "Results per page (default: 30, max: 100)",
                        "default": 30,
                    },
                    "page": {
                        "type": "integer",
                        "description": "Page number",
                        "default": 1,
                    },
                },
                required=["q"],
            ),
            category=ToolCategory.INTEGRATION,
            source_type="builtin",
            provider="github",
            danger_level="low",
        )
        super().__init__(metadata)

    async def execute(
        self,
        q: str,
        sort: str = "indexed",
        order: str = "desc",
        per_page: int = 30,
        page: int = 1,
    ) -> Dict[str, Any]:
        """Search code in GitHub repositories."""
        url = f"{self.base_url}/search/code"

        headers = {
            "Authorization": f"token {self.access_token}",
            "Accept": "application/vnd.github.v3+json",
        }

        params = {
            "q": q,
            "sort": sort,
            "order": order,
            "per_page": min(per_page, 100),
            "page": page,
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"GitHub API error: {response.status} - {error_text}")

                result = await response.json()

                return {
                    "success": True,
                    "total_count": result.get("total_count", 0),
                    "items": result.get("items", []),
                    "count": len(result.get("items", [])),
                }
