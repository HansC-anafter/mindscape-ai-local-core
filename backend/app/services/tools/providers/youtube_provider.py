"""
YouTube Tool Discovery Provider

Discovers YouTube capabilities using YouTube Data API v3.
Supports: upload videos, read video info, manage playlists, search videos.
"""
import logging
from typing import List, Dict, Any
from backend.app.services.tools.discovery_provider import (
    ToolDiscoveryProvider,
    ToolConfig,
    DiscoveredTool
)

logger = logging.getLogger(__name__)


class YouTubeDiscoveryProvider(ToolDiscoveryProvider):
    """
    YouTube Discovery Provider

    Discovers capabilities from YouTube using YouTube Data API v3.
    """

    @property
    def provider_name(self) -> str:
        return "youtube"

    @property
    def supported_connection_types(self) -> List[str]:
        return ["http_api"]

    async def discover(self, config: ToolConfig) -> List[DiscoveredTool]:
        """
        Discover YouTube capabilities

        Returns tools for:
        - Upload videos
        - Read video information
        - Manage playlists
        - Search videos
        """
        access_token = config.api_key
        if not access_token:
            raise ValueError("YouTube access token is required")

        discovered_tools = [
            DiscoveredTool(
                tool_id="youtube_upload_video",
                display_name="Upload YouTube Video",
                description="Upload a video to YouTube",
                category="social_media",
                endpoint="https://www.googleapis.com/upload/youtube/v3/videos",
                methods=["POST"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "video_file": {
                            "type": "string",
                            "description": "Video file path or base64 encoded content"
                        },
                        "title": {
                            "type": "string",
                            "description": "Video title"
                        },
                        "description": {
                            "type": "string",
                            "description": "Video description"
                        },
                        "privacy_status": {
                            "type": "string",
                            "enum": ["private", "unlisted", "public"],
                            "description": "Video privacy status",
                            "default": "private"
                        },
                        "category_id": {
                            "type": "string",
                            "description": "Video category ID (optional)"
                        }
                    },
                    "required": ["video_file", "title"]
                },
                danger_level="high",
                metadata={
                    "api_version": "v3",
                    "operation": "write"
                }
            ),
            DiscoveredTool(
                tool_id="youtube_get_video",
                display_name="Get YouTube Video Information",
                description="Get information about a specific YouTube video",
                category="social_media",
                endpoint="https://www.googleapis.com/youtube/v3/videos",
                methods=["GET"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "video_id": {
                            "type": "string",
                            "description": "YouTube video ID"
                        },
                        "part": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Parts to include (e.g., 'snippet', 'statistics', 'contentDetails')",
                            "default": ["snippet", "statistics", "contentDetails"]
                        }
                    },
                    "required": ["video_id"]
                },
                danger_level="low",
                metadata={
                    "api_version": "v3",
                    "operation": "read"
                }
            ),
            DiscoveredTool(
                tool_id="youtube_search_videos",
                display_name="Search YouTube Videos",
                description="Search for videos on YouTube",
                category="social_media",
                endpoint="https://www.googleapis.com/youtube/v3/search",
                methods=["GET"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "q": {
                            "type": "string",
                            "description": "Search query"
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of results (default: 25, max: 50)",
                            "default": 25,
                            "maximum": 50
                        },
                        "type": {
                            "type": "string",
                            "enum": ["video", "channel", "playlist"],
                            "description": "Type of search result",
                            "default": "video"
                        }
                    },
                    "required": ["q"]
                },
                danger_level="low",
                metadata={
                    "api_version": "v3",
                    "operation": "read"
                }
            ),
            DiscoveredTool(
                tool_id="youtube_create_playlist",
                display_name="Create YouTube Playlist",
                description="Create a new YouTube playlist",
                category="social_media",
                endpoint="https://www.googleapis.com/youtube/v3/playlists",
                methods=["POST"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "Playlist title"
                        },
                        "description": {
                            "type": "string",
                            "description": "Playlist description"
                        },
                        "privacy_status": {
                            "type": "string",
                            "enum": ["private", "unlisted", "public"],
                            "description": "Playlist privacy status",
                            "default": "private"
                        }
                    },
                    "required": ["title"]
                },
                danger_level="medium",
                metadata={
                    "api_version": "v3",
                    "operation": "write"
                }
            ),
            DiscoveredTool(
                tool_id="youtube_get_channel",
                display_name="Get YouTube Channel Information",
                description="Get authenticated user's YouTube channel information",
                category="social_media",
                endpoint="https://www.googleapis.com/youtube/v3/channels",
                methods=["GET"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "part": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Parts to include (e.g., 'snippet', 'statistics', 'contentDetails')",
                            "default": ["snippet", "statistics"]
                        }
                    },
                    "required": []
                },
                danger_level="low",
                metadata={
                    "api_version": "v3",
                    "operation": "read"
                }
            )
        ]

        logger.info(f"Discovered {len(discovered_tools)} YouTube tools")
        return discovered_tools

    async def validate(self, config: ToolConfig) -> bool:
        """
        Validate YouTube configuration

        Checks:
        - Access token is provided
        """
        if not config.api_key:
            logger.error("YouTube validation failed: api_key (access_token) is required")
            return False

        return True

    def get_discovery_metadata(self) -> Dict[str, Any]:
        return {
            "provider": self.provider_name,
            "display_name": "YouTube",
            "description": "YouTube integration for uploading videos, reading video info, and managing playlists",
            "supported_connection_types": self.supported_connection_types,
            "required_config": ["api_key"],
            "optional_config": ["api_secret"],
            "documentation_url": "https://developers.google.com/youtube/v3",
            "notes": [
                "Requires YouTube OAuth 2.0 access token",
                "Supports: upload videos, read video info, manage playlists, search videos",
                "OAuth flow available for secure authentication",
                "Requires Google Cloud project and YouTube Data API enabled"
            ],
            "config_form_schema": {
                "api_key": {
                    "type": "password",
                    "label": "Access Token",
                    "placeholder": "YouTube OAuth access token",
                    "help": "Get from YouTube OAuth flow or Google Cloud Console"
                }
            }
        }

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "tool_type": {
                    "type": "string",
                    "const": "youtube"
                },
                "connection_type": {
                    "type": "string",
                    "enum": ["http_api"]
                },
                "api_key": {
                    "type": "string",
                    "description": "YouTube OAuth 2.0 access token"
                },
                "api_secret": {
                    "type": "string",
                    "description": "Google Client Secret (optional, for OAuth refresh)"
                }
            },
            "required": ["tool_type", "connection_type", "api_key"]
        }

