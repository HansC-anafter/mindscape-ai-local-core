"""Factory helpers for GitHub provider tools."""

from typing import List, Optional

from backend.app.services.tools.base import MindscapeTool
from backend.app.services.tools.github.github_tools_core.contents import (
    GitHubReadFileTool,
)
from backend.app.services.tools.github.github_tools_core.issues import (
    GitHubCreateIssueTool,
    GitHubListIssuesTool,
)
from backend.app.services.tools.github.github_tools_core.pull_requests import (
    GitHubCreatePRTool,
)
from backend.app.services.tools.github.github_tools_core.repositories import (
    GitHubListReposTool,
    GitHubSearchCodeTool,
)


def create_github_tools(access_token: str) -> List[MindscapeTool]:
    """Create all GitHub tools for a connection."""
    return [
        GitHubListReposTool(access_token),
        GitHubReadFileTool(access_token),
        GitHubCreateIssueTool(access_token),
        GitHubListIssuesTool(access_token),
        GitHubCreatePRTool(access_token),
        GitHubSearchCodeTool(access_token),
    ]


def get_github_tool_by_name(tool_name: str, access_token: str) -> Optional[MindscapeTool]:
    """Get a specific GitHub tool by name."""
    tools_map = {
        "github_list_repos": GitHubListReposTool,
        "github_read_file": GitHubReadFileTool,
        "github_create_issue": GitHubCreateIssueTool,
        "github_list_issues": GitHubListIssuesTool,
        "github_create_pr": GitHubCreatePRTool,
        "github_search_code": GitHubSearchCodeTool,
    }

    tool_class = tools_map.get(tool_name)
    if not tool_class:
        return None

    return tool_class(access_token)
