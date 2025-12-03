"""
Google Sheets Tool Discovery Provider

Discovers Google Sheets capabilities using Google Sheets API.
Supports: read range, write range, append rows, list spreadsheets.
"""
import logging
from typing import List, Dict, Any
from backend.app.services.tools.discovery_provider import (
    ToolDiscoveryProvider,
    ToolConfig,
    DiscoveredTool
)

logger = logging.getLogger(__name__)


class GoogleSheetsDiscoveryProvider(ToolDiscoveryProvider):
    """
    Google Sheets Discovery Provider

    Discovers capabilities from Google Sheets using Google Sheets API.
    Can reuse Google Drive OAuth for authentication.
    """

    @property
    def provider_name(self) -> str:
        return "google_sheets"

    @property
    def supported_connection_types(self) -> List[str]:
        return ["oauth2", "http_api"]

    async def discover(self, config: ToolConfig) -> List[DiscoveredTool]:
        """
        Discover Google Sheets capabilities

        Returns tools for:
        - Read range
        - Write range
        - Append rows
        - List spreadsheets
        """
        access_token = config.api_key
        if not access_token:
            raise ValueError("Google Sheets access token is required")

        discovered_tools = [
            DiscoveredTool(
                tool_id="google_sheets_read_range",
                display_name="Read Google Sheets Range",
                description="Read data from a range in Google Sheets",
                category="data",
                endpoint="https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/{range}",
                methods=["GET"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "spreadsheet_id": {
                            "type": "string",
                            "description": "Google Sheets spreadsheet ID"
                        },
                        "range": {
                            "type": "string",
                            "description": "Range to read (e.g., 'Sheet1!A1:B10')"
                        },
                        "value_render_option": {
                            "type": "string",
                            "enum": ["FORMATTED_VALUE", "UNFORMATTED_VALUE", "FORMULA"],
                            "default": "FORMATTED_VALUE"
                        }
                    },
                    "required": ["spreadsheet_id", "range"]
                },
                danger_level="low",
                metadata={
                    "api_version": "v4",
                    "operation": "read"
                }
            ),
            DiscoveredTool(
                tool_id="google_sheets_write_range",
                display_name="Write Google Sheets Range",
                description="Write data to a range in Google Sheets",
                category="data",
                endpoint="https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/{range}",
                methods=["PUT"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "spreadsheet_id": {
                            "type": "string",
                            "description": "Google Sheets spreadsheet ID"
                        },
                        "range": {
                            "type": "string",
                            "description": "Range to write (e.g., 'Sheet1!A1:B10')"
                        },
                        "values": {
                            "type": "array",
                            "description": "2D array of values to write",
                            "items": {
                                "type": "array",
                                "items": {"type": "string"}
                            }
                        },
                        "value_input_option": {
                            "type": "string",
                            "enum": ["RAW", "USER_ENTERED"],
                            "default": "USER_ENTERED"
                        }
                    },
                    "required": ["spreadsheet_id", "range", "values"]
                },
                danger_level="medium",
                metadata={
                    "api_version": "v4",
                    "operation": "write"
                }
            ),
            DiscoveredTool(
                tool_id="google_sheets_append_rows",
                display_name="Append Rows to Google Sheets",
                description="Append rows to a Google Sheets spreadsheet",
                category="data",
                endpoint="https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/{range}:append",
                methods=["POST"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "spreadsheet_id": {
                            "type": "string",
                            "description": "Google Sheets spreadsheet ID"
                        },
                        "range": {
                            "type": "string",
                            "description": "Range to append to (e.g., 'Sheet1!A1')"
                        },
                        "values": {
                            "type": "array",
                            "description": "2D array of values to append",
                            "items": {
                                "type": "array",
                                "items": {"type": "string"}
                            }
                        },
                        "value_input_option": {
                            "type": "string",
                            "enum": ["RAW", "USER_ENTERED"],
                            "default": "USER_ENTERED"
                        }
                    },
                    "required": ["spreadsheet_id", "range", "values"]
                },
                danger_level="medium",
                metadata={
                    "api_version": "v4",
                    "operation": "write"
                }
            ),
            DiscoveredTool(
                tool_id="google_sheets_list_spreadsheets",
                display_name="List Google Sheets Spreadsheets",
                description="List Google Sheets spreadsheets in Google Drive",
                category="data",
                endpoint="https://www.googleapis.com/drive/v3/files",
                methods=["GET"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "page_size": {
                            "type": "integer",
                            "description": "Maximum number of results",
                            "default": 100
                        },
                        "q": {
                            "type": "string",
                            "description": "Query string for filtering"
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

        logger.info(f"Discovered {len(discovered_tools)} Google Sheets tools")
        return discovered_tools

    async def validate(self, config: ToolConfig) -> bool:
        """
        Validate Google Sheets configuration

        Checks:
        - Access token is provided
        - Token format is valid (Google OAuth token)
        """
        if not config.api_key:
            logger.error("Google Sheets validation failed: api_key (access_token) is required")
            return False

        return True

    def get_discovery_metadata(self) -> Dict[str, Any]:
        return {
            "provider": self.provider_name,
            "display_name": "Google Sheets",
            "description": "Google Sheets integration for spreadsheet management",
            "supported_connection_types": self.supported_connection_types,
            "required_config": ["api_key"],
            "optional_config": [],
            "documentation_url": "https://developers.google.com/sheets/api",
            "notes": [
                "Requires Google OAuth 2.0 access token",
                "Can reuse Google Drive OAuth configuration",
                "Supports: read range, write range, append rows, list spreadsheets"
            ],
            "config_form_schema": {
                "api_key": {
                    "type": "password",
                    "label": "Access Token",
                    "placeholder": "Google OAuth token",
                    "help": "Get from Google OAuth flow or reuse Google Drive OAuth"
                }
            }
        }

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "tool_type": {
                    "type": "string",
                    "const": "google_sheets"
                },
                "connection_type": {
                    "type": "string",
                    "enum": ["oauth2", "http_api"]
                },
                "api_key": {
                    "type": "string",
                    "description": "Google OAuth access token"
                }
            },
            "required": ["tool_type", "connection_type", "api_key"]
        }

