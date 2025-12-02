"""
Google Drive Tool Discovery Provider

Discovers Google Drive capabilities using Google Drive API.
Supports read-only operations initially (list files, read files).

Note: OAuth 2.0 flow will be implemented in a separate service.
This provider focuses on tool discovery after authentication.
"""
import logging
from typing import List, Dict, Any, Optional
from backend.app.services.discovery_provider import (
    ToolDiscoveryProvider,
    ToolConfig,
    DiscoveredTool
)

logger = logging.getLogger(__name__)


class GoogleDriveDiscoveryProvider(ToolDiscoveryProvider):
    """
    Google Drive Discovery Provider

    Discovers capabilities from Google Drive using Google Drive API.
    Initially supports read-only operations.
    """

    @property
    def provider_name(self) -> str:
        return "google_drive"

    @property
    def supported_connection_types(self) -> List[str]:
        return ["http_api", "oauth2"]

    async def discover(self, config: ToolConfig) -> List[DiscoveredTool]:
        """
        Discover Google Drive capabilities

        Returns read-only tools:
        - List files and folders
        - Read file content
        """
        access_token = config.api_key
        if not access_token:
            raise ValueError("Google Drive access token is required")

        discovered_tools = [
            DiscoveredTool(
                tool_id="google_drive_list_files",
                display_name="List Google Drive Files",
                description="List files and folders in Google Drive",
                category="data",
                endpoint="https://www.googleapis.com/drive/v3/files",
                methods=["GET"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "folder_id": {
                            "type": "string",
                            "description": "Folder ID to list (default: 'root' for root folder)"
                        },
                        "page_size": {
                            "type": "integer",
                            "description": "Maximum number of results (default: 100, max: 1000)",
                            "default": 100
                        },
                        "page_token": {
                            "type": "string",
                            "description": "Page token for pagination"
                        },
                        "q": {
                            "type": "string",
                            "description": "Query string for filtering (e.g., \"mimeType='application/pdf'\")"
                        }
                    },
                    "required": []
                },
                danger_level="low",
                metadata={
                    "api_version": "v3",
                    "operation": "read_only"
                }
            ),
            DiscoveredTool(
                tool_id="google_drive_read_file",
                display_name="Read Google Drive File",
                description="Read file content from Google Drive by file ID",
                category="data",
                endpoint="https://www.googleapis.com/drive/v3/files/{file_id}",
                methods=["GET"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "file_id": {
                            "type": "string",
                            "description": "Google Drive file ID"
                        },
                        "export_format": {
                            "type": "string",
                            "description": "Export format for Google Docs/Sheets/Slides (e.g., 'text/plain', 'application/pdf')",
                            "enum": ["text/plain", "text/html", "application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"]
                        }
                    },
                    "required": ["file_id"]
                },
                danger_level="low",
                metadata={
                    "api_version": "v3",
                    "operation": "read_only"
                }
            )
        ]

        logger.info(f"Discovered {len(discovered_tools)} Google Drive tools (read-only)")
        return discovered_tools

    async def validate(self, config: ToolConfig) -> bool:
        """
        Validate Google Drive configuration

        Checks:
        - Access token is provided
        - Token format is valid (basic check)
        """
        if not config.api_key:
            logger.error("Google Drive validation failed: api_key (access_token) is required")
            return False

        if not config.api_key.startswith("ya29.") and not config.api_key.startswith("1//"):
            logger.warning(
                "Google Drive access token format may be invalid. "
                "Expected OAuth 2.0 access token or refresh token."
            )

        return True

    def get_discovery_metadata(self) -> Dict[str, Any]:
        return {
            "provider": self.provider_name,
            "display_name": "Google Drive",
            "description": "Google Drive integration (read-only operations)",
            "supported_connection_types": self.supported_connection_types,
            "required_config": ["api_key"],
            "optional_config": ["api_secret"],
            "documentation_url": "https://developers.google.com/drive/api",
            "notes": [
                "Requires OAuth 2.0 access token",
                "Currently supports read-only operations (list files, read files)",
                "Write operations (create/update) will be added when needed",
                "OAuth flow implementation in separate service"
            ],
            "config_form_schema": {
                "api_key": {
                    "type": "password",
                    "label": "Access Token",
                    "placeholder": "ya29...",
                    "help": "OAuth 2.0 access token from Google"
                }
            }
        }

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "tool_type": {
                    "type": "string",
                    "const": "google_drive"
                },
                "connection_type": {
                    "type": "string",
                    "enum": ["http_api", "oauth2"]
                },
                "api_key": {
                    "type": "string",
                    "description": "Google Drive OAuth 2.0 access token"
                },
                "api_secret": {
                    "type": "string",
                    "description": "Refresh token (optional, for token refresh)"
                }
            },
            "required": ["tool_type", "connection_type", "api_key"]
        }
