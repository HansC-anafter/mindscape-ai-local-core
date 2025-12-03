"""
GitHub Tools

Tools for GitHub repository integration.
Supports: list repos, read files, create issues, list issues, create PR, search code.
"""
import aiohttp
import logging
from typing import Dict, Any, Optional, List
from backend.app.services.tools.base import MindscapeTool
from backend.app.services.tools.schemas import ToolMetadata, ToolInputSchema

logger = logging.getLogger(__name__)


class GitHubListReposTool(MindscapeTool):
    """List repositories for authenticated user or organization"""

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
                        "default": "all"
                    },
                    "sort": {
                        "type": "string",
                        "description": "Sort by (created, updated, pushed, full_name)",
                        "enum": ["created", "updated", "pushed", "full_name"],
                        "default": "updated"
                    },
                    "direction": {
                        "type": "string",
                        "description": "Sort direction (asc, desc)",
                        "enum": ["asc", "desc"],
                        "default": "desc"
                    },
                    "per_page": {
                        "type": "integer",
                        "description": "Results per page (default: 30, max: 100)",
                        "default": 30
                    },
                    "page": {
                        "type": "integer",
                        "description": "Page number",
                        "default": 1
                    }
                },
                required=[]
            ),
            category="code",
            source_type="builtin",
            provider="github",
            danger_level="low"
        )
        super().__init__(metadata)

    async def execute(
        self,
        type: str = "all",
        sort: str = "updated",
        direction: str = "desc",
        per_page: int = 30,
        page: int = 1
    ) -> Dict[str, Any]:
        """List repositories"""
        url = f"{self.base_url}/user/repos"

        headers = {
            "Authorization": f"token {self.access_token}",
            "Accept": "application/vnd.github.v3+json"
        }

        params = {
            "type": type,
            "sort": sort,
            "direction": direction,
            "per_page": min(per_page, 100),
            "page": page
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
                    "count": len(result)
                }


class GitHubReadFileTool(MindscapeTool):
    """Read file content from GitHub repository"""

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
                        "description": "Repository owner (username or organization)"
                    },
                    "repo": {
                        "type": "string",
                        "description": "Repository name"
                    },
                    "path": {
                        "type": "string",
                        "description": "File path in repository"
                    },
                    "ref": {
                        "type": "string",
                        "description": "Branch, tag, or commit SHA (default: main/master)"
                    }
                },
                required=["owner", "repo", "path"]
            ),
            category="code",
            source_type="builtin",
            provider="github",
            danger_level="low"
        )
        super().__init__(metadata)

    async def execute(
        self,
        owner: str,
        repo: str,
        path: str,
        ref: Optional[str] = None
    ) -> Dict[str, Any]:
        """Read file content from GitHub repository"""
        url = f"{self.base_url}/repos/{owner}/{repo}/contents/{path}"

        headers = {
            "Authorization": f"token {self.access_token}",
            "Accept": "application/vnd.github.v3+json"
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

                # Decode base64 content if file is not too large
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
                    "encoding": result.get("encoding")
                }


class GitHubCreateIssueTool(MindscapeTool):
    """Create an issue in GitHub repository"""

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
                        "description": "Repository owner (username or organization)"
                    },
                    "repo": {
                        "type": "string",
                        "description": "Repository name"
                    },
                    "title": {
                        "type": "string",
                        "description": "Issue title"
                    },
                    "body": {
                        "type": "string",
                        "description": "Issue body (markdown supported)"
                    },
                    "labels": {
                        "type": "array",
                        "description": "Labels to add to issue",
                        "items": {"type": "string"}
                    },
                    "assignees": {
                        "type": "array",
                        "description": "Usernames to assign issue to",
                        "items": {"type": "string"}
                    }
                },
                required=["owner", "repo", "title"]
            ),
            category="code",
            source_type="builtin",
            provider="github",
            danger_level="medium"
        )
        super().__init__(metadata)

    async def execute(
        self,
        owner: str,
        repo: str,
        title: str,
        body: Optional[str] = None,
        labels: Optional[List[str]] = None,
        assignees: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Create an issue in GitHub repository"""
        url = f"{self.base_url}/repos/{owner}/{repo}/issues"

        headers = {
            "Authorization": f"token {self.access_token}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json"
        }

        payload = {
            "title": title
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
                        "state": result.get("state")
                    }
                }


class GitHubListIssuesTool(MindscapeTool):
    """List issues in GitHub repository"""

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
                        "description": "Repository owner (username or organization)"
                    },
                    "repo": {
                        "type": "string",
                        "description": "Repository name"
                    },
                    "state": {
                        "type": "string",
                        "description": "Issue state (open, closed, all)",
                        "enum": ["open", "closed", "all"],
                        "default": "open"
                    },
                    "labels": {
                        "type": "string",
                        "description": "Comma-separated list of label names"
                    },
                    "sort": {
                        "type": "string",
                        "description": "Sort by (created, updated, comments)",
                        "enum": ["created", "updated", "comments"],
                        "default": "created"
                    },
                    "direction": {
                        "type": "string",
                        "description": "Sort direction (asc, desc)",
                        "enum": ["asc", "desc"],
                        "default": "desc"
                    },
                    "per_page": {
                        "type": "integer",
                        "description": "Results per page (default: 30, max: 100)",
                        "default": 30
                    },
                    "page": {
                        "type": "integer",
                        "description": "Page number",
                        "default": 1
                    }
                },
                required=["owner", "repo"]
            ),
            category="code",
            source_type="builtin",
            provider="github",
            danger_level="low"
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
        page: int = 1
    ) -> Dict[str, Any]:
        """List issues in GitHub repository"""
        url = f"{self.base_url}/repos/{owner}/{repo}/issues"

        headers = {
            "Authorization": f"token {self.access_token}",
            "Accept": "application/vnd.github.v3+json"
        }

        params = {
            "state": state,
            "sort": sort,
            "direction": direction,
            "per_page": min(per_page, 100),
            "page": page
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
                    "count": len(result)
                }


class GitHubCreatePRTool(MindscapeTool):
    """Create a pull request in GitHub repository"""

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
                        "description": "Repository owner (username or organization)"
                    },
                    "repo": {
                        "type": "string",
                        "description": "Repository name"
                    },
                    "title": {
                        "type": "string",
                        "description": "Pull request title"
                    },
                    "head": {
                        "type": "string",
                        "description": "Branch name to merge from (e.g., 'feature-branch')"
                    },
                    "base": {
                        "type": "string",
                        "description": "Branch name to merge into (e.g., 'main')",
                        "default": "main"
                    },
                    "body": {
                        "type": "string",
                        "description": "Pull request body (markdown supported)"
                    },
                    "draft": {
                        "type": "boolean",
                        "description": "Create as draft PR",
                        "default": False
                    }
                },
                required=["owner", "repo", "title", "head"]
            ),
            category="code",
            source_type="builtin",
            provider="github",
            danger_level="high"
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
        draft: bool = False
    ) -> Dict[str, Any]:
        """Create a pull request in GitHub repository"""
        url = f"{self.base_url}/repos/{owner}/{repo}/pulls"

        headers = {
            "Authorization": f"token {self.access_token}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json"
        }

        payload = {
            "title": title,
            "head": head,
            "base": base,
            "draft": draft
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
                        "state": result.get("state")
                    }
                }


class GitHubSearchCodeTool(MindscapeTool):
    """Search code in GitHub repositories"""

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
                        "description": "Search query (e.g., 'addClass in:file language:js')"
                    },
                    "sort": {
                        "type": "string",
                        "description": "Sort by (indexed)",
                        "enum": ["indexed"],
                        "default": "indexed"
                    },
                    "order": {
                        "type": "string",
                        "description": "Sort order (asc, desc)",
                        "enum": ["asc", "desc"],
                        "default": "desc"
                    },
                    "per_page": {
                        "type": "integer",
                        "description": "Results per page (default: 30, max: 100)",
                        "default": 30
                    },
                    "page": {
                        "type": "integer",
                        "description": "Page number",
                        "default": 1
                    }
                },
                required=["q"]
            ),
            category="code",
            source_type="builtin",
            provider="github",
            danger_level="low"
        )
        super().__init__(metadata)

    async def execute(
        self,
        q: str,
        sort: str = "indexed",
        order: str = "desc",
        per_page: int = 30,
        page: int = 1
    ) -> Dict[str, Any]:
        """Search code in GitHub repositories"""
        url = f"{self.base_url}/search/code"

        headers = {
            "Authorization": f"token {self.access_token}",
            "Accept": "application/vnd.github.v3+json"
        }

        params = {
            "q": q,
            "sort": sort,
            "order": order,
            "per_page": min(per_page, 100),
            "page": page
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
                    "count": len(result.get("items", []))
                }


def create_github_tools(access_token: str) -> List[MindscapeTool]:
    """Create all GitHub tools for a connection"""
    return [
        GitHubListReposTool(access_token),
        GitHubReadFileTool(access_token),
        GitHubCreateIssueTool(access_token),
        GitHubListIssuesTool(access_token),
        GitHubCreatePRTool(access_token),
        GitHubSearchCodeTool(access_token)
    ]


def get_github_tool_by_name(tool_name: str, access_token: str) -> Optional[MindscapeTool]:
    """Get a specific GitHub tool by name"""
    tools_map = {
        "github_list_repos": GitHubListReposTool,
        "github_read_file": GitHubReadFileTool,
        "github_create_issue": GitHubCreateIssueTool,
        "github_list_issues": GitHubListIssuesTool,
        "github_create_pr": GitHubCreatePRTool,
        "github_search_code": GitHubSearchCodeTool
    }

    tool_class = tools_map.get(tool_name)
    if not tool_class:
        return None

    return tool_class(access_token)

