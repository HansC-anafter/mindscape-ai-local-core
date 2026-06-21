"""Repository content GitHub tools."""

import logging
from typing import Any, Dict, Optional

import aiohttp

from backend.app.services.tools.base import MindscapeTool
from backend.app.services.tools.schemas import (
    ToolCategory,
    ToolInputSchema,
    ToolMetadata,
)

logger = logging.getLogger(__name__)


class GitHubReadFileTool(MindscapeTool):
    """Read file content from GitHub repository."""

    def __init__(self, access_token: str):
        self.access_token = access_token
        self.base_url = "https://api.github.com"

        metadata = ToolMetadata(
            name="github_read_file",
            description="Read file content from GitHub repository",
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
                    "path": {
                        "type": "string",
                        "description": "File path in repository",
                    },
                    "ref": {
                        "type": "string",
                        "description": "Branch, tag, or commit SHA (default: main/master)",
                    },
                },
                required=["owner", "repo", "path"],
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
        path: str,
        ref: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Read file content from GitHub repository."""
        url = f"{self.base_url}/repos/{owner}/{repo}/contents/{path}"

        headers = {
            "Authorization": f"token {self.access_token}",
            "Accept": "application/vnd.github.v3+json",
        }

        params = {}
        if ref:
            params["ref"] = ref

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"GitHub API error: {response.status} - {error_text}")

                result = await response.json()

                content = result.get("content", "")
                if content and result.get("encoding") == "base64":
                    import base64

                    try:
                        content = base64.b64decode(content).decode("utf-8")
                    except Exception as e:
                        logger.warning(f"Failed to decode file content: {e}")

                return {
                    "success": True,
                    "name": result.get("name"),
                    "path": result.get("path"),
                    "sha": result.get("sha"),
                    "size": result.get("size"),
                    "content": content,
                    "encoding": result.get("encoding"),
                }
