"""
Twitter Tool Discovery Provider

Discovers Twitter/X capabilities using Twitter API v2.
Supports: create tweets, read tweets, search tweets, manage media.
"""
import logging
from typing import List, Dict, Any
from backend.app.services.tools.discovery_provider import (
    ToolDiscoveryProvider,
    ToolConfig,
    DiscoveredTool
)

logger = logging.getLogger(__name__)


class TwitterDiscoveryProvider(ToolDiscoveryProvider):
    """
    Twitter Discovery Provider

    Discovers capabilities from Twitter/X using Twitter API v2.
    """

    @property
    def provider_name(self) -> str:
        return "twitter"

    @property
    def supported_connection_types(self) -> List[str]:
        return ["http_api"]

    async def discover(self, config: ToolConfig) -> List[DiscoveredTool]:
        """
        Discover Twitter/X capabilities

        Returns tools for:
        - Create tweets
        - Read tweets
        - Search tweets
        - Manage media
        - Get user information
        """
        access_token = config.api_key
        if not access_token:
            raise ValueError("Twitter access token is required")

        discovered_tools = [
            DiscoveredTool(
                tool_id="twitter_create_tweet",
                display_name="Create Tweet",
                description="Post a new tweet to Twitter/X",
                category="social_media",
                endpoint="https://api.twitter.com/2/tweets",
                methods=["POST"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "Tweet text content (max 280 characters)",
                            "maxLength": 280
                        },
                        "reply_settings": {
                            "type": "string",
                            "enum": ["mentionedUsers", "following"],
                            "description": "Who can reply to this tweet"
                        },
                        "media_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Array of media IDs to attach to the tweet"
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
                tool_id="twitter_read_tweet",
                display_name="Read Tweet",
                description="Get information about a specific tweet",
                category="social_media",
                endpoint="https://api.twitter.com/2/tweets/{id}",
                methods=["GET"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "id": {
                            "type": "string",
                            "description": "Tweet ID"
                        },
                        "tweet_fields": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Additional tweet fields to include (e.g., 'created_at', 'author_id')",
                            "default": ["created_at", "author_id", "public_metrics"]
                        }
                    },
                    "required": ["id"]
                },
                danger_level="low",
                metadata={
                    "api_version": "v2",
                    "operation": "read"
                }
            ),
            DiscoveredTool(
                tool_id="twitter_search_tweets",
                display_name="Search Tweets",
                description="Search for recent tweets using query",
                category="social_media",
                endpoint="https://api.twitter.com/2/tweets/search/recent",
                methods=["GET"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query (e.g., 'from:username', '#hashtag', 'keyword')"
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of results (default: 10, max: 100)",
                            "default": 10,
                            "minimum": 10,
                            "maximum": 100
                        },
                        "tweet_fields": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Additional tweet fields to include",
                            "default": ["created_at", "author_id", "public_metrics"]
                        }
                    },
                    "required": ["query"]
                },
                danger_level="low",
                metadata={
                    "api_version": "v2",
                    "operation": "read"
                }
            ),
            DiscoveredTool(
                tool_id="twitter_upload_media",
                display_name="Upload Media",
                description="Upload media (images, videos) to Twitter",
                category="social_media",
                endpoint="https://upload.twitter.com/1.1/media/upload.json",
                methods=["POST"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "media": {
                            "type": "string",
                            "description": "Media file content (base64 encoded) or file path"
                        },
                        "media_category": {
                            "type": "string",
                            "enum": ["tweet_image", "tweet_video", "tweet_gif"],
                            "description": "Media category",
                            "default": "tweet_image"
                        }
                    },
                    "required": ["media"]
                },
                danger_level="medium",
                metadata={
                    "api_version": "v1.1",
                    "operation": "write"
                }
            ),
            DiscoveredTool(
                tool_id="twitter_get_user",
                display_name="Get User Information",
                description="Get authenticated user information",
                category="social_media",
                endpoint="https://api.twitter.com/2/users/me",
                methods=["GET"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "user_fields": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Additional user fields to include (e.g., 'description', 'public_metrics')",
                            "default": ["description", "public_metrics", "verified"]
                        }
                    },
                    "required": []
                },
                danger_level="low",
                metadata={
                    "api_version": "v2",
                    "operation": "read"
                }
            )
        ]

        logger.info(f"Discovered {len(discovered_tools)} Twitter tools")
        return discovered_tools

    async def validate(self, config: ToolConfig) -> bool:
        """
        Validate Twitter configuration

        Checks:
        - Access token (Bearer token) is provided
        - Token format validation (optional, can be enhanced with API call)
        """
        if not config.api_key:
            logger.error("Twitter validation failed: api_key (access_token) is required")
            return False

        access_token = config.api_key
        if not access_token.startswith("Bearer ") and len(access_token) < 10:
            logger.warning(
                "Twitter access token should be a valid Bearer token. "
                "Please verify you're using a valid Twitter OAuth token."
            )

        return True

    def get_discovery_metadata(self) -> Dict[str, Any]:
        return {
            "provider": self.provider_name,
            "display_name": "Twitter/X",
            "description": "Twitter/X integration for posting tweets, reading tweets, and managing media",
            "supported_connection_types": self.supported_connection_types,
            "required_config": ["api_key"],
            "optional_config": ["api_secret"],
            "documentation_url": "https://developer.twitter.com/en/docs/twitter-api",
            "notes": [
                "Requires Twitter OAuth 2.0 Bearer token",
                "Supports: create tweets, read tweets, search tweets, upload media, get user info",
                "OAuth flow available for secure authentication",
                "API v2 for tweets, API v1.1 for media upload"
            ],
            "config_form_schema": {
                "api_key": {
                    "type": "password",
                    "label": "Bearer Token",
                    "placeholder": "Bearer token from Twitter OAuth",
                    "help": "Get from Twitter OAuth flow or Twitter Developer Portal"
                }
            }
        }

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "tool_type": {
                    "type": "string",
                    "const": "twitter"
                },
                "connection_type": {
                    "type": "string",
                    "enum": ["http_api"]
                },
                "api_key": {
                    "type": "string",
                    "description": "Twitter OAuth 2.0 Bearer token"
                },
                "api_secret": {
                    "type": "string",
                    "description": "Twitter API secret (optional, for OAuth refresh)"
                }
            },
            "required": ["tool_type", "connection_type", "api_key"]
        }

