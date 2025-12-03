"""
GitHub Tool Discovery Provider

Discovers GitHub repository capabilities using GitHub API.
Supports: list repos, read files, create issues, list issues, create PR, search code.
"""
import logging
from typing import List, Dict, Any
from backend.app.services.tools.discovery_provider import (
    ToolDiscoveryProvider,
    ToolConfig,
    DiscoveredTool
)

logger = logging.getLogger(__name__)


class GitHubDiscoveryProvider(ToolDiscoveryProvider):
    """
    GitHub Discovery Provider

    Discovers capabilities from GitHub using GitHub API.
    """

    @property
    def provider_name(self) -> str:
        return "github"

    @property
    def supported_connection_types(self) -> List[str]:
        return ["oauth2", "http_api"]

    async def discover(self, config: ToolConfig) -> List[DiscoveredTool]:
        """
        Discover GitHub capabilities

        Returns tools for:
        - List repositories
        - Read files
        - Create issues
        - List issues
        - Create pull requests
        - Search code
        """
        access_token = config.api_key
        if not access_token:
            raise ValueError("GitHub access token is required")

        discovered_tools = [
            DiscoveredTool(
                tool_id="github_list_repos",
                display_name="List GitHub Repositories",
                description="List repositories for authenticated user or organization",
                category="code",
                endpoint="https://api.github.com/user/repos",
                methods=["GET"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "type": {
                            "type": "string",
                            "enum": ["all", "owner", "member"],
                            "default": "all"
                        },
                        "sort": {
                            "type": "string",
                            "enum": ["created", "updated", "pushed", "full_name"],
                            "default": "updated"
                        }
                    },
                    "required": []
                },
                danger_level="low",
                metadata={
                    "api_version": "v3",
                    "operation": "read"
                }
            ),
            DiscoveredTool(
                tool_id="github_read_file",
                display_name="Read GitHub File",
                description="Read file content from GitHub repository",
                category="code",
                endpoint="https://api.github.com/repos/{owner}/{repo}/contents/{path}",
                methods=["GET"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "owner": {
                            "type": "string",
                            "description": "Repository owner"
                        },
                        "repo": {
                            "type": "string",
                            "description": "Repository name"
                        },
                        "path": {
                            "type": "string",
                            "description": "File path in repository"
                        }
                    },
                    "required": ["owner", "repo", "path"]
                },
                danger_level="low",
                metadata={
                    "api_version": "v3",
                    "operation": "read"
                }
            ),
            DiscoveredTool(
                tool_id="github_create_issue",
                display_name="Create GitHub Issue",
                description="Create an issue in GitHub repository",
                category="code",
                endpoint="https://api.github.com/repos/{owner}/{repo}/issues",
                methods=["POST"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "owner": {
                            "type": "string",
                            "description": "Repository owner"
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
                            "description": "Issue body"
                        }
                    },
                    "required": ["owner", "repo", "title"]
                },
                danger_level="medium",
                metadata={
                    "api_version": "v3",
                    "operation": "write"
                }
            ),
            DiscoveredTool(
                tool_id="github_list_issues",
                display_name="List GitHub Issues",
                description="List issues in GitHub repository",
                category="code",
                endpoint="https://api.github.com/repos/{owner}/{repo}/issues",
                methods=["GET"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "owner": {
                            "type": "string",
                            "description": "Repository owner"
                        },
                        "repo": {
                            "type": "string",
                            "description": "Repository name"
                        },
                        "state": {
                            "type": "string",
                            "enum": ["open", "closed", "all"],
                            "default": "open"
                        }
                    },
                    "required": ["owner", "repo"]
                },
                danger_level="low",
                metadata={
                    "api_version": "v3",
                    "operation": "read"
                }
            ),
            DiscoveredTool(
                tool_id="github_create_pr",
                display_name="Create GitHub Pull Request",
                description="Create a pull request in GitHub repository",
                category="code",
                endpoint="https://api.github.com/repos/{owner}/{repo}/pulls",
                methods=["POST"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "owner": {
                            "type": "string",
                            "description": "Repository owner"
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
                            "description": "Branch to merge from"
                        },
                        "base": {
                            "type": "string",
                            "description": "Branch to merge into",
                            "default": "main"
                        }
                    },
                    "required": ["owner", "repo", "title", "head"]
                },
                danger_level="high",
                metadata={
                    "api_version": "v3",
                    "operation": "write"
                }
            ),
            DiscoveredTool(
                tool_id="github_search_code",
                display_name="Search GitHub Code",
                description="Search code in GitHub repositories",
                category="code",
                endpoint="https://api.github.com/search/code",
                methods=["GET"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "q": {
                            "type": "string",
                            "description": "Search query"
                        }
                    },
                    "required": ["q"]
                },
                danger_level="low",
                metadata={
                    "api_version": "v3",
                    "operation": "read"
                }
            )
        ]

        logger.info(f"Discovered {len(discovered_tools)} GitHub tools")
        return discovered_tools

    async def validate(self, config: ToolConfig) -> bool:
        """
        Validate GitHub configuration

        Checks:
        - Access token is provided
        - Token format is valid (starts with 'ghp_' for Personal Access Token or 'gho_' for OAuth token)
        """
        if not config.api_key:
            logger.error("GitHub validation failed: api_key (access_token) is required")
            return False

        access_token = config.api_key
        if not (access_token.startswith("ghp_") or access_token.startswith("gho_") or access_token.startswith("github_pat_")):
            logger.warning(
                "GitHub access token should start with 'ghp_' (Personal Access Token), 'gho_' (OAuth token), or 'github_pat_' (Fine-grained token). "
                "Please verify you're using a valid GitHub token."
            )

        return True

    def get_discovery_metadata(self) -> Dict[str, Any]:
        return {
            "provider": self.provider_name,
            "display_name": "GitHub",
            "description": "GitHub repository integration for code management",
            "supported_connection_types": self.supported_connection_types,
            "required_config": ["api_key"],
            "optional_config": [],
            "documentation_url": "https://docs.github.com/en/rest",
            "notes": [
                "Requires GitHub OAuth access token or Personal Access Token",
                "Supports: list repos, read files, create issues, list issues, create PR, search code",
                "OAuth flow available for secure authentication"
            ],
            "config_form_schema": {
                "api_key": {
                    "type": "password",
                    "label": "Access Token",
                    "placeholder": "ghp_... or gho_...",
                    "help": "Get from GitHub OAuth flow or create Personal Access Token at github.com/settings/tokens"
                }
            }
        }

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "tool_type": {
                    "type": "string",
                    "const": "github"
                },
                "connection_type": {
                    "type": "string",
                    "enum": ["oauth2", "http_api"]
                },
                "api_key": {
                    "type": "string",
                    "description": "GitHub access token (OAuth token gho_ or Personal Access Token ghp_)"
                }
            },
            "required": ["tool_type", "connection_type", "api_key"]
        }

