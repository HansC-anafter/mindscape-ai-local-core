"""
Notion Tool Discovery Provider

Discovers Notion workspace capabilities using Notion API.
Supports read-only operations initially (search, read pages).
"""
import logging
from typing import List, Dict, Any, Optional
from backend.app.services.discovery_provider import (
    ToolDiscoveryProvider,
    ToolConfig,
    DiscoveredTool
)

logger = logging.getLogger(__name__)


class NotionDiscoveryProvider(ToolDiscoveryProvider):
    """
    Notion Discovery Provider

    Discovers capabilities from a Notion workspace using Notion API.
    Initially supports read-only operations.
    """

    @property
    def provider_name(self) -> str:
        return "notion"

    @property
    def supported_connection_types(self) -> List[str]:
        return ["http_api"]

    async def discover(self, config: ToolConfig) -> List[DiscoveredTool]:
        """
        Discover Notion workspace capabilities

        Returns read-only tools:
        - Search pages and databases
        - Read page content
        """
        api_key = config.api_key
        if not api_key:
            raise ValueError("Notion API key (integration token) is required")

        discovered_tools = [
            DiscoveredTool(
                tool_id="notion_search",
                display_name="Search Notion",
                description="Search pages and databases in Notion workspace",
                category="data",
                endpoint="https://api.notion.com/v1/search",
                methods=["POST"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query text"
                        },
                        "filter": {
                            "type": "object",
                            "description": "Filter options (page, database, etc.)",
                            "properties": {
                                "value": {
                                    "type": "string",
                                    "enum": ["page", "database"]
                                },
                                "property": {
                                    "type": "string",
                                    "enum": ["object"]
                                }
                            }
                        },
                        "sort": {
                            "type": "object",
                            "description": "Sort options"
                        }
                    },
                    "required": ["query"]
                },
                danger_level="low",
                metadata={
                    "api_version": "2022-06-28",
                    "operation": "read_only"
                }
            ),
            DiscoveredTool(
                tool_id="notion_read_page",
                display_name="Read Notion Page",
                description="Read content from a Notion page by page ID",
                category="data",
                endpoint="https://api.notion.com/v1/pages/{page_id}",
                methods=["GET"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "page_id": {
                            "type": "string",
                            "description": "Notion page ID (UUID format)"
                        }
                    },
                    "required": ["page_id"]
                },
                danger_level="low",
                metadata={
                    "api_version": "2022-06-28",
                    "operation": "read_only"
                }
            ),
            DiscoveredTool(
                tool_id="notion_read_database",
                display_name="Read Notion Database",
                description="Read database structure and query database entries",
                category="data",
                endpoint="https://api.notion.com/v1/databases/{database_id}",
                methods=["GET", "POST"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "database_id": {
                            "type": "string",
                            "description": "Notion database ID (UUID format)"
                        },
                        "filter": {
                            "type": "object",
                            "description": "Query filter (optional, for POST /query)"
                        },
                        "sorts": {
                            "type": "array",
                            "description": "Sort options (optional, for POST /query)"
                        }
                    },
                    "required": ["database_id"]
                },
                danger_level="low",
                metadata={
                    "api_version": "2022-06-28",
                    "operation": "read_only"
                }
            )
        ]

        logger.info(f"Discovered {len(discovered_tools)} Notion tools (read-only)")
        return discovered_tools

    async def validate(self, config: ToolConfig) -> bool:
        """
        Validate Notion configuration

        Checks:
        - API key (integration token) is provided
        - API key format is valid (starts with 'secret_')
        """
        if not config.api_key:
            logger.error("Notion validation failed: api_key is required")
            return False

        if not config.api_key.startswith("secret_"):
            logger.warning(
                "Notion API key should start with 'secret_'. "
                "Please verify you're using an Integration Token."
            )

        return True

    def get_discovery_metadata(self) -> Dict[str, Any]:
        return {
            "provider": self.provider_name,
            "display_name": "Notion",
            "description": "Notion workspace integration (read-only operations)",
            "supported_connection_types": self.supported_connection_types,
            "required_config": ["api_key"],
            "optional_config": [],
            "documentation_url": "https://developers.notion.com/",
            "notes": [
                "Requires Notion Integration Token (create at notion.so/my-integrations)",
                "Currently supports read-only operations (search, read pages/databases)",
                "Write operations (create/update) will be added when needed"
            ],
            "config_form_schema": {
                "api_key": {
                    "type": "password",
                    "label": "Integration Token",
                    "placeholder": "secret_...",
                    "help": "Create at notion.so/my-integrations"
                }
            }
        }

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "tool_type": {
                    "type": "string",
                    "const": "notion"
                },
                "connection_type": {
                    "type": "string",
                    "enum": ["http_api"]
                },
                "api_key": {
                    "type": "string",
                    "description": "Notion Integration Token (starts with 'secret_')"
                }
            },
            "required": ["tool_type", "connection_type", "api_key"]
        }
