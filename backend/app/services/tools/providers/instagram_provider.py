"""
Instagram Tool Discovery Provider

Discovers Instagram capabilities using Instagram Basic Display API and Graph API.
Supports: read posts, read media, read comments.
"""
import logging
from typing import List, Dict, Any
from backend.app.services.tools.discovery_provider import (
    ToolDiscoveryProvider,
    ToolConfig,
    DiscoveredTool
)

logger = logging.getLogger(__name__)


class InstagramDiscoveryProvider(ToolDiscoveryProvider):
    """
    Instagram Discovery Provider

    Discovers capabilities from Instagram using Instagram Basic Display API and Graph API.
    """

    @property
    def provider_name(self) -> str:
        return "instagram"

    @property
    def supported_connection_types(self) -> List[str]:
        return ["http_api"]

    async def discover(self, config: ToolConfig) -> List[DiscoveredTool]:
        """
        Discover Instagram capabilities

        Returns tools for:
        - Read posts/media
        - Read comments
        - Get user information
        """
        access_token = config.api_key
        if not access_token:
            raise ValueError("Instagram access token is required")

        discovered_tools = [
            DiscoveredTool(
                tool_id="instagram_get_media",
                display_name="Get Instagram Media",
                description="Get media posts from Instagram account",
                category="social_media",
                endpoint="https://graph.instagram.com/me/media",
                methods=["GET"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": "Number of media items to retrieve (default: 25, max: 100)",
                            "default": 25,
                            "maximum": 100
                        },
                        "fields": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Fields to include (e.g., 'id', 'caption', 'media_type', 'media_url')",
                            "default": ["id", "caption", "media_type", "media_url", "timestamp"]
                        }
                    },
                    "required": []
                },
                danger_level="low",
                metadata={
                    "api_version": "v18.0",
                    "operation": "read"
                }
            ),
            DiscoveredTool(
                tool_id="instagram_get_media_item",
                display_name="Get Instagram Media Item",
                description="Get specific media item details",
                category="social_media",
                endpoint="https://graph.instagram.com/{media_id}",
                methods=["GET"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "media_id": {
                            "type": "string",
                            "description": "Instagram media ID"
                        },
                        "fields": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Fields to include",
                            "default": ["id", "caption", "media_type", "media_url", "timestamp", "like_count", "comments_count"]
                        }
                    },
                    "required": ["media_id"]
                },
                danger_level="low",
                metadata={
                    "api_version": "v18.0",
                    "operation": "read"
                }
            ),
            DiscoveredTool(
                tool_id="instagram_get_user_info",
                display_name="Get Instagram User Information",
                description="Get authenticated user's Instagram account information",
                category="social_media",
                endpoint="https://graph.instagram.com/me",
                methods=["GET"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "fields": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "User fields to include",
                            "default": ["id", "username", "account_type"]
                        }
                    },
                    "required": []
                },
                danger_level="low",
                metadata={
                    "api_version": "v18.0",
                    "operation": "read"
                }
            )
        ]

        logger.info(f"Discovered {len(discovered_tools)} Instagram tools")
        return discovered_tools

    async def validate(self, config: ToolConfig) -> bool:
        """
        Validate Instagram configuration

        Checks:
        - Access token is provided
        """
        if not config.api_key:
            logger.error("Instagram validation failed: api_key (access_token) is required")
            return False

        return True

    def get_discovery_metadata(self) -> Dict[str, Any]:
        return {
            "provider": self.provider_name,
            "display_name": "Instagram",
            "description": "Instagram integration for reading posts and media",
            "supported_connection_types": self.supported_connection_types,
            "required_config": ["api_key"],
            "optional_config": ["api_secret"],
            "documentation_url": "https://developers.facebook.com/docs/instagram-basic-display-api",
            "notes": [
                "Requires Instagram OAuth 2.0 access token",
                "Supports: read media, read comments, get user info",
                "OAuth flow available for secure authentication",
                "Note: Instagram Basic Display API is read-only"
            ],
            "config_form_schema": {
                "api_key": {
                    "type": "password",
                    "label": "Access Token",
                    "placeholder": "Instagram OAuth access token",
                    "help": "Get from Instagram OAuth flow or Facebook Developer Portal"
                }
            }
        }

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "tool_type": {
                    "type": "string",
                    "const": "instagram"
                },
                "connection_type": {
                    "type": "string",
                    "enum": ["http_api"]
                },
                "api_key": {
                    "type": "string",
                    "description": "Instagram OAuth 2.0 access token"
                },
                "api_secret": {
                    "type": "string",
                    "description": "Instagram App Secret (optional, for OAuth refresh)"
                }
            },
            "required": ["tool_type", "connection_type", "api_key"]
        }

