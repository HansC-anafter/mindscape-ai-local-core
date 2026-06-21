"""Issue-related GitHub tools."""

from typing import Any, Dict, List, Optional

import aiohttp

from backend.app.services.tools.base import MindscapeTool
from backend.app.services.tools.schemas import (
    ToolCategory,
    ToolInputSchema,
    ToolMetadata,
)


class GitHubCreateIssueTool(MindscapeTool):
    """Create an issue in GitHub repository."""

    def __init__(self, access_token: str):
        self.access_token = access_token
        self.base_url = "https://api.github.com"

        metadata = ToolMetadata(
            name="github_create_issue",
            description="Create an issue in GitHub repository",
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
                        "description": "Issue title",
                    },
                    "body": {
                        "type": "string",
                        "description": "Issue body (markdown supported)",
                    },
                    "labels": {
                        "type": "array",
                        "description": "Labels to add to issue",
                        "items": {"type": "string"},
                    },
                    "assignees": {
                        "type": "array",
                        "description": "Usernames to assign issue to",
                        "items": {"type": "string"},
                    },
                },
                required=["owner", "repo", "title"],
            ),
            category=ToolCategory.INTEGRATION,
            source_type="builtin",
            provider="github",
            danger_level="medium",
        )
        super().__init__(metadata)

    async def execute(
        self,
        owner: str,
        repo: str,
        title: str,
        body: Optional[str] = None,
        labels: Optional[List[str]] = None,
        assignees: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Create an issue in GitHub repository."""
        url = f"{self.base_url}/repos/{owner}/{repo}/issues"

        headers = {
            "Authorization": f"token {self.access_token}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json",
        }

        payload = {
            "title": title,
        }

        if body:
            payload["body"] = body
        if labels:
            payload["labels"] = labels
        if assignees:
            payload["assignees"] = assignees

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as response:
                if response.status != 201:
                    error_text = await response.text()
                    raise Exception(f"GitHub API error: {response.status} - {error_text}")

                result = await response.json()

                return {
                    "success": True,
                    "issue": {
                        "id": result.get("id"),
                        "number": result.get("number"),
                        "title": result.get("title"),
                        "url": result.get("html_url"),
                        "state": result.get("state"),
                    },
                }


class GitHubListIssuesTool(MindscapeTool):
    """List issues in GitHub repository."""

    def __init__(self, access_token: str):
        self.access_token = access_token
        self.base_url = "https://api.github.com"

        metadata = ToolMetadata(
            name="github_list_issues",
            description="List issues in GitHub repository",
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
                    "state": {
                        "type": "string",
                        "description": "Issue state (open, closed, all)",
                        "enum": ["open", "closed", "all"],
                        "default": "open",
                    },
                    "labels": {
                        "type": "string",
                        "description": "Comma-separated list of label names",
                    },
                    "sort": {
                        "type": "string",
                        "description": "Sort by (created, updated, comments)",
                        "enum": ["created", "updated", "comments"],
                        "default": "created",
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
                required=["owner", "repo"],
            ),
            category=ToolCategory.INTEGRATION,
            source_type="builtin",
            provider="github",
            danger_level="low",
        )
        super().__init__(metadata)

    async def execute(
        self,
        owner: str,
        repo: str,
        state: str = "open",
        labels: Optional[str] = None,
        sort: str = "created",
        direction: str = "desc",
        per_page: int = 30,
        page: int = 1,
    ) -> Dict[str, Any]:
        """List issues in GitHub repository."""
        url = f"{self.base_url}/repos/{owner}/{repo}/issues"

        headers = {
            "Authorization": f"token {self.access_token}",
            "Accept": "application/vnd.github.v3+json",
        }

        params = {
            "state": state,
            "sort": sort,
            "direction": direction,
            "per_page": min(per_page, 100),
            "page": page,
        }

        if labels:
            params["labels"] = labels

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"GitHub API error: {response.status} - {error_text}")

                result = await response.json()

                return {
                    "success": True,
                    "issues": result,
                    "count": len(result),
                }
