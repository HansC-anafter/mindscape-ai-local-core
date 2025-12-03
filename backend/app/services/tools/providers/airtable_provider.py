"""
Airtable Tool Discovery Provider

Discovers Airtable workspace capabilities using Airtable API.
Supports: list bases, read tables, create/update/delete records.
"""
import logging
from typing import List, Dict, Any
from backend.app.services.tools.discovery_provider import (
    ToolDiscoveryProvider,
    ToolConfig,
    DiscoveredTool
)

logger = logging.getLogger(__name__)


class AirtableDiscoveryProvider(ToolDiscoveryProvider):
    """
    Airtable Discovery Provider

    Discovers capabilities from an Airtable workspace using Airtable API.
    """

    @property
    def provider_name(self) -> str:
        return "airtable"

    @property
    def supported_connection_types(self) -> List[str]:
        return ["http_api"]

    async def discover(self, config: ToolConfig) -> List[DiscoveredTool]:
        """
        Discover Airtable workspace capabilities

        Returns tools for:
        - List bases
        - Read table records
        - Create records
        - Update records
        - Delete records
        """
        api_key = config.api_key
        if not api_key:
            raise ValueError("Airtable API key is required")

        discovered_tools = [
            DiscoveredTool(
                tool_id="airtable_list_bases",
                display_name="List Airtable Bases",
                description="List all bases in Airtable workspace",
                category="data",
                endpoint="https://api.airtable.com/v0/meta/bases",
                methods=["GET"],
                input_schema={
                    "type": "object",
                    "properties": {},
                    "required": []
                },
                danger_level="low",
                metadata={
                    "api_version": "v0",
                    "operation": "read"
                }
            ),
            DiscoveredTool(
                tool_id="airtable_read_table",
                display_name="Read Airtable Table",
                description="Read records from an Airtable table",
                category="data",
                endpoint="https://api.airtable.com/v0/{base_id}/{table_name}",
                methods=["GET"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "base_id": {
                            "type": "string",
                            "description": "Airtable base ID"
                        },
                        "table_name": {
                            "type": "string",
                            "description": "Table name or table ID"
                        },
                        "max_records": {
                            "type": "integer",
                            "description": "Maximum number of records to return (default: 100, max: 100)",
                            "default": 100
                        },
                        "view": {
                            "type": "string",
                            "description": "View name or view ID (optional)"
                        },
                        "filter_by_formula": {
                            "type": "string",
                            "description": "Formula to filter records (optional)"
                        }
                    },
                    "required": ["base_id", "table_name"]
                },
                danger_level="low",
                metadata={
                    "api_version": "v0",
                    "operation": "read"
                }
            ),
            DiscoveredTool(
                tool_id="airtable_create_record",
                display_name="Create Airtable Record",
                description="Create a new record in an Airtable table",
                category="data",
                endpoint="https://api.airtable.com/v0/{base_id}/{table_name}",
                methods=["POST"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "base_id": {
                            "type": "string",
                            "description": "Airtable base ID"
                        },
                        "table_name": {
                            "type": "string",
                            "description": "Table name or table ID"
                        },
                        "fields": {
                            "type": "object",
                            "description": "Field values for the new record"
                        }
                    },
                    "required": ["base_id", "table_name", "fields"]
                },
                danger_level="medium",
                metadata={
                    "api_version": "v0",
                    "operation": "write"
                }
            ),
            DiscoveredTool(
                tool_id="airtable_update_record",
                display_name="Update Airtable Record",
                description="Update an existing record in an Airtable table",
                category="data",
                endpoint="https://api.airtable.com/v0/{base_id}/{table_name}/{record_id}",
                methods=["PATCH"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "base_id": {
                            "type": "string",
                            "description": "Airtable base ID"
                        },
                        "table_name": {
                            "type": "string",
                            "description": "Table name or table ID"
                        },
                        "record_id": {
                            "type": "string",
                            "description": "Record ID to update"
                        },
                        "fields": {
                            "type": "object",
                            "description": "Field values to update"
                        }
                    },
                    "required": ["base_id", "table_name", "record_id", "fields"]
                },
                danger_level="medium",
                metadata={
                    "api_version": "v0",
                    "operation": "write"
                }
            ),
            DiscoveredTool(
                tool_id="airtable_delete_record",
                display_name="Delete Airtable Record",
                description="Delete a record from an Airtable table",
                category="data",
                endpoint="https://api.airtable.com/v0/{base_id}/{table_name}/{record_id}",
                methods=["DELETE"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "base_id": {
                            "type": "string",
                            "description": "Airtable base ID"
                        },
                        "table_name": {
                            "type": "string",
                            "description": "Table name or table ID"
                        },
                        "record_id": {
                            "type": "string",
                            "description": "Record ID to delete"
                        }
                    },
                    "required": ["base_id", "table_name", "record_id"]
                },
                danger_level="high",
                metadata={
                    "api_version": "v0",
                    "operation": "delete"
                }
            )
        ]

        logger.info(f"Discovered {len(discovered_tools)} Airtable tools")
        return discovered_tools

    async def validate(self, config: ToolConfig) -> bool:
        """
        Validate Airtable configuration

        Checks:
        - API key is provided
        - API key format is valid (starts with 'pat' for Personal Access Token)
        """
        if not config.api_key:
            logger.error("Airtable validation failed: api_key is required")
            return False

        api_key = config.api_key
        if not (api_key.startswith("pat") or api_key.startswith("key")):
            logger.warning(
                "Airtable API key should start with 'pat' (Personal Access Token) or 'key' (API Key). "
                "Please verify you're using a valid Airtable token."
            )

        return True

    def get_discovery_metadata(self) -> Dict[str, Any]:
        return {
            "provider": self.provider_name,
            "display_name": "Airtable",
            "description": "Airtable workspace integration for structured data management",
            "supported_connection_types": self.supported_connection_types,
            "required_config": ["api_key"],
            "optional_config": [],
            "documentation_url": "https://airtable.com/api",
            "notes": [
                "Requires Airtable Personal Access Token (create at airtable.com/developers/web/guides/personal-access-tokens)",
                "Supports: list bases, read tables, create/update/delete records",
                "OAuth 2.0 support can be added when needed"
            ],
            "config_form_schema": {
                "api_key": {
                    "type": "password",
                    "label": "Personal Access Token",
                    "placeholder": "pat...",
                    "help": "Create at airtable.com/developers/web/guides/personal-access-tokens"
                }
            }
        }

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "tool_type": {
                    "type": "string",
                    "const": "airtable"
                },
                "connection_type": {
                    "type": "string",
                    "enum": ["http_api"]
                },
                "api_key": {
                    "type": "string",
                    "description": "Airtable Personal Access Token (starts with 'pat')"
                }
            },
            "required": ["tool_type", "connection_type", "api_key"]
        }

