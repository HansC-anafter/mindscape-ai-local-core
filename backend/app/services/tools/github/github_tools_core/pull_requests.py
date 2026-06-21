"""Pull request GitHub tools."""

from typing import Any, Dict, Optional

import aiohttp

from backend.app.services.tools.base import MindscapeTool
from backend.app.services.tools.schemas import (
    ToolCategory,
    ToolInputSchema,
    ToolMetadata,
)


class GitHubCreatePRTool(MindscapeTool):
    """Create a pull request in GitHub repository."""

    def __init__(self, access_token: str):
        self.access_token = access_token
        self.base_url = "https://api.github.com"

        metadata = ToolMetadata(
            name="github_create_pr",
            description="Create a pull request in GitHub repository",
            input_schema=ToolInputSchema(
                type="object",
                properties={
                    "owner": {
                        "type": "string",
                        "description": "Repository owner (username or organization)",
                    },
                    "repo": {
                        "type": "string",
                        "description": "Repository name",
                    },
                    "title": {
                        "type": "string",
                        "description": "Pull request title",
                    },
                    "head": {
                        "type": "string",
                        "description": "Branch name to merge from (e.g., 'feature-branch')",
                    },
                    "base": {
                        "type": "string",
                        "description": "Branch name to merge into (e.g., 'main')",
                        "default": "main",
                    },
                    "body": {
                        "type": "string",
                        "description": "Pull request body (markdown supported)",
                    },
                    "draft": {
                        "type": "boolean",
                        "description": "Create as draft PR",
                        "default": False,
                    },
                },
                required=["owner", "repo", "title", "head"],
            ),
            category=ToolCategory.INTEGRATION,
            source_type="builtin",
            provider="github",
            danger_level="high",
        )
        super().__init__(metadata)

    async def execute(
        self,
        owner: str,
        repo: str,
        title: str,
        head: str,
        base: str = "main",
        body: Optional[str] = None,
        draft: bool = False,
    ) -> Dict[str, Any]:
        """Create a pull request in GitHub repository."""
        url = f"{self.base_url}/repos/{owner}/{repo}/pulls"

        headers = {
            "Authorization": f"token {self.access_token}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json",
        }

        payload = {
            "title": title,
            "head": head,
            "base": base,
            "draft": draft,
        }

        if body:
            payload["body"] = body

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as response:
                if response.status != 201:
                    error_text = await response.text()
                    raise Exception(f"GitHub API error: {response.status} - {error_text}")

                result = await response.json()

                return {
                    "success": True,
                    "pull_request": {
                        "id": result.get("id"),
                        "number": result.get("number"),
                        "title": result.get("title"),
                        "url": result.get("html_url"),
                        "state": result.get("state"),
                    },
                }
