"""
LinkedIn Tool Discovery Provider

Discovers LinkedIn capabilities using LinkedIn API.
Supports: create posts, read posts, manage profile, search connections.
"""
import logging
from typing import List, Dict, Any
from backend.app.services.tools.discovery_provider import (
    ToolDiscoveryProvider,
    ToolConfig,
    DiscoveredTool
)

logger = logging.getLogger(__name__)


class LinkedInDiscoveryProvider(ToolDiscoveryProvider):
    """
    LinkedIn Discovery Provider

    Discovers capabilities from LinkedIn using LinkedIn API.
    """

    @property
    def provider_name(self) -> str:
        return "linkedin"

    @property
    def supported_connection_types(self) -> List[str]:
        return ["http_api"]

    async def discover(self, config: ToolConfig) -> List[DiscoveredTool]:
        """
        Discover LinkedIn capabilities

        Returns tools for:
        - Create posts (articles)
        - Read posts
        - Manage profile
        - Search connections
        """
        access_token = config.api_key
        if not access_token:
            raise ValueError("LinkedIn access token is required")

        discovered_tools = [
            DiscoveredTool(
                tool_id="linkedin_create_post",
                display_name="Create LinkedIn Post",
                description="Create a new post on LinkedIn",
                category="social_media",
                endpoint="https://api.linkedin.com/v2/ugcPosts",
                methods=["POST"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "Post text content"
                        },
                        "visibility": {
                            "type": "string",
                            "enum": ["PUBLIC", "CONNECTIONS"],
                            "description": "Post visibility",
                            "default": "PUBLIC"
                        }
                    },
                    "required": ["text"]
                },
                danger_level="medium",
                metadata={
                    "api_version": "v2",
                    "operation": "write"
                }
            ),
            DiscoveredTool(
                tool_id="linkedin_get_profile",
                display_name="Get LinkedIn Profile",
                description="Get authenticated user's LinkedIn profile information",
                category="social_media",
                endpoint="https://api.linkedin.com/v2/me",
                methods=["GET"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "fields": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Profile fields to include",
                            "default": ["id", "firstName", "lastName", "headline"]
                        }
                    },
                    "required": []
                },
                danger_level="low",
                metadata={
                    "api_version": "v2",
                    "operation": "read"
                }
            ),
            DiscoveredTool(
                tool_id="linkedin_search_people",
                display_name="Search LinkedIn People",
                description="Search for people on LinkedIn",
                category="social_media",
                endpoint="https://api.linkedin.com/v2/people-search",
                methods=["GET"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "keywords": {
                            "type": "string",
                            "description": "Search keywords"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Number of results (default: 10, max: 100)",
                            "default": 10,
                            "maximum": 100
                        }
                    },
                    "required": ["keywords"]
                },
                danger_level="low",
                metadata={
                    "api_version": "v2",
                    "operation": "read"
                }
            )
        ]

        logger.info(f"Discovered {len(discovered_tools)} LinkedIn tools")
        return discovered_tools

    async def validate(self, config: ToolConfig) -> bool:
        """
        Validate LinkedIn configuration

        Checks:
        - Access token is provided
        """
        if not config.api_key:
            logger.error("LinkedIn validation failed: api_key (access_token) is required")
            return False

        return True

    def get_discovery_metadata(self) -> Dict[str, Any]:
        return {
            "provider": self.provider_name,
            "display_name": "LinkedIn",
            "description": "LinkedIn integration for posting, reading posts, and managing profile",
            "supported_connection_types": self.supported_connection_types,
            "required_config": ["api_key"],
            "optional_config": ["api_secret"],
            "documentation_url": "https://docs.microsoft.com/en-us/linkedin/",
            "notes": [
                "Requires LinkedIn OAuth 2.0 access token",
                "Supports: create posts, read profile, search people",
                "OAuth flow available for secure authentication",
                "Requires LinkedIn App and appropriate permissions"
            ],
            "config_form_schema": {
                "api_key": {
                    "type": "password",
                    "label": "Access Token",
                    "placeholder": "LinkedIn OAuth access token",
                    "help": "Get from LinkedIn OAuth flow or LinkedIn Developer Portal"
                }
            }
        }

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "tool_type": {
                    "type": "string",
                    "const": "linkedin"
                },
                "connection_type": {
                    "type": "string",
                    "enum": ["http_api"]
                },
                "api_key": {
                    "type": "string",
                    "description": "LinkedIn OAuth 2.0 access token"
                },
                "api_secret": {
                    "type": "string",
                    "description": "LinkedIn Client Secret (optional, for OAuth refresh)"
                }
            },
            "required": ["tool_type", "connection_type", "api_key"]
        }

