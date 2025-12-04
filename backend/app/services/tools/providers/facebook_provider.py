"""
Facebook Tool Discovery Provider

Discovers Facebook capabilities using Facebook Graph API.
Supports: create posts, read posts, manage photos, manage comments.
"""
import logging
from typing import List, Dict, Any
from backend.app.services.tools.discovery_provider import (
    ToolDiscoveryProvider,
    ToolConfig,
    DiscoveredTool
)

logger = logging.getLogger(__name__)


class FacebookDiscoveryProvider(ToolDiscoveryProvider):
    """
    Facebook Discovery Provider

    Discovers capabilities from Facebook using Graph API.
    """

    @property
    def provider_name(self) -> str:
        return "facebook"

    @property
    def supported_connection_types(self) -> List[str]:
        return ["http_api"]

    async def discover(self, config: ToolConfig) -> List[DiscoveredTool]:
        """
        Discover Facebook capabilities

        Returns tools for:
        - Create posts
        - Read posts
        - Manage photos
        - Manage comments
        - Get page information
        """
        access_token = config.api_key
        if not access_token:
            raise ValueError("Facebook access token is required")

        discovered_tools = [
            DiscoveredTool(
                tool_id="facebook_create_post",
                display_name="Create Facebook Post",
                description="Create a new post on Facebook page or profile",
                category="social_media",
                endpoint="https://graph.facebook.com/v18.0/{page_id}/feed",
                methods=["POST"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "message": {
                            "type": "string",
                            "description": "Post message text"
                        },
                        "link": {
                            "type": "string",
                            "description": "URL to attach to the post (optional)"
                        },
                        "published": {
                            "type": "boolean",
                            "description": "Whether to publish immediately (default: true)",
                            "default": True
                        }
                    },
                    "required": ["message"]
                },
                danger_level="medium",
                metadata={
                    "api_version": "v18.0",
                    "operation": "write"
                }
            ),
            DiscoveredTool(
                tool_id="facebook_read_posts",
                display_name="Read Facebook Posts",
                description="Get posts from a Facebook page or profile",
                category="social_media",
                endpoint="https://graph.facebook.com/v18.0/{page_id}/posts",
                methods=["GET"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "page_id": {
                            "type": "string",
                            "description": "Facebook page ID"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Number of posts to retrieve (default: 25, max: 100)",
                            "default": 25,
                            "maximum": 100
                        },
                        "fields": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Fields to include (e.g., 'message', 'created_time', 'likes')",
                            "default": ["id", "message", "created_time"]
                        }
                    },
                    "required": ["page_id"]
                },
                danger_level="low",
                metadata={
                    "api_version": "v18.0",
                    "operation": "read"
                }
            ),
            DiscoveredTool(
                tool_id="facebook_upload_photo",
                display_name="Upload Photo to Facebook",
                description="Upload a photo to Facebook page or profile",
                category="social_media",
                endpoint="https://graph.facebook.com/v18.0/{page_id}/photos",
                methods=["POST"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "page_id": {
                            "type": "string",
                            "description": "Facebook page ID"
                        },
                        "url": {
                            "type": "string",
                            "description": "URL of the photo to upload"
                        },
                        "caption": {
                            "type": "string",
                            "description": "Photo caption (optional)"
                        },
                        "published": {
                            "type": "boolean",
                            "description": "Whether to publish immediately (default: true)",
                            "default": True
                        }
                    },
                    "required": ["page_id", "url"]
                },
                danger_level="medium",
                metadata={
                    "api_version": "v18.0",
                    "operation": "write"
                }
            ),
            DiscoveredTool(
                tool_id="facebook_get_page_info",
                display_name="Get Facebook Page Information",
                description="Get information about a Facebook page",
                category="social_media",
                endpoint="https://graph.facebook.com/v18.0/{page_id}",
                methods=["GET"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "page_id": {
                            "type": "string",
                            "description": "Facebook page ID"
                        },
                        "fields": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Fields to include (e.g., 'name', 'about', 'fan_count')",
                            "default": ["id", "name", "about", "fan_count"]
                        }
                    },
                    "required": ["page_id"]
                },
                danger_level="low",
                metadata={
                    "api_version": "v18.0",
                    "operation": "read"
                }
            )
        ]

        logger.info(f"Discovered {len(discovered_tools)} Facebook tools")
        return discovered_tools

    async def validate(self, config: ToolConfig) -> bool:
        """
        Validate Facebook configuration

        Checks:
        - Access token is provided
        """
        if not config.api_key:
            logger.error("Facebook validation failed: api_key (access_token) is required")
            return False

        return True

    def get_discovery_metadata(self) -> Dict[str, Any]:
        return {
            "provider": self.provider_name,
            "display_name": "Facebook",
            "description": "Facebook integration for posting, reading posts, and managing photos",
            "supported_connection_types": self.supported_connection_types,
            "required_config": ["api_key"],
            "optional_config": ["api_secret"],
            "documentation_url": "https://developers.facebook.com/docs/graph-api",
            "notes": [
                "Requires Facebook OAuth 2.0 access token",
                "Supports: create posts, read posts, upload photos, get page info",
                "OAuth flow available for secure authentication",
                "Requires Facebook App and appropriate permissions"
            ],
            "config_form_schema": {
                "api_key": {
                    "type": "password",
                    "label": "Access Token",
                    "placeholder": "Facebook OAuth access token",
                    "help": "Get from Facebook OAuth flow or Facebook Developer Portal"
                }
            }
        }

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "tool_type": {
                    "type": "string",
                    "const": "facebook"
                },
                "connection_type": {
                    "type": "string",
                    "enum": ["http_api"]
                },
                "api_key": {
                    "type": "string",
                    "description": "Facebook OAuth 2.0 access token"
                },
                "api_secret": {
                    "type": "string",
                    "description": "Facebook App Secret (optional, for OAuth refresh)"
                }
            },
            "required": ["tool_type", "connection_type", "api_key"]
        }

