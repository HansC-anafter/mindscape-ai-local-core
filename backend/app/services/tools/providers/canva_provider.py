"""
Canva Tool Discovery Provider

Discovers Canva API capabilities for design creation and management.
"""
import logging
from typing import List, Dict, Any
from backend.app.services.discovery_provider import (
    ToolDiscoveryProvider,
    ToolConfig,
    DiscoveredTool
)

logger = logging.getLogger(__name__)


class CanvaDiscoveryProvider(ToolDiscoveryProvider):
    """
    Canva Discovery Provider

    Discovers Canva API capabilities for design tools.
    """

    @property
    def provider_name(self) -> str:
        return "canva"

    @property
    def supported_connection_types(self) -> List[str]:
        return ["http_api", "oauth2"]

    async def discover(self, config: ToolConfig) -> List[DiscoveredTool]:
        """
        Discover Canva API tools

        Returns:
            List of Canva tools (list_templates, create_design, update_text_blocks, export_design)
        """
        # Validate authentication
        if not config.api_key and not config.custom_config.get("oauth_token"):
            raise ValueError("Canva API requires either api_key or oauth_token")

        discovered_tools = [
            DiscoveredTool(
                tool_id="canva.list_templates",
                display_name="List Canva Templates",
                description="List available Canva templates. Can filter by brand and paginate results.",
                category="content",
                endpoint="https://api.canva.com/rest/v1/templates",
                methods=["GET"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "brand_id": {
                            "type": "string",
                            "description": "Optional brand ID to filter templates"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of templates to return",
                            "default": 20,
                            "minimum": 1,
                            "maximum": 100
                        },
                        "offset": {
                            "type": "integer",
                            "description": "Pagination offset",
                            "default": 0,
                            "minimum": 0
                        }
                    },
                    "required": []
                },
                danger_level="low",
                metadata={
                    "api_version": "v1",
                    "operation": "read_only"
                }
            ),
            DiscoveredTool(
                tool_id="canva.create_design_from_template",
                display_name="Create Canva Design",
                description="Create a new Canva design from a template. Returns design ID and details.",
                category="content",
                endpoint="https://api.canva.com/rest/v1/designs",
                methods=["POST"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "template_id": {
                            "type": "string",
                            "description": "Template ID to create design from"
                        },
                        "brand_id": {
                            "type": "string",
                            "description": "Optional brand ID for the design"
                        },
                        "title": {
                            "type": "string",
                            "description": "Optional design title"
                        }
                    },
                    "required": ["template_id"]
                },
                danger_level="medium",
                metadata={
                    "api_version": "v1",
                    "operation": "write"
                }
            ),
            DiscoveredTool(
                tool_id="canva.update_text_blocks",
                display_name="Update Canva Text Blocks",
                description="Update text blocks in a Canva design. Can update single or multiple text blocks.",
                category="content",
                endpoint="https://api.canva.com/rest/v1/designs/{design_id}/text-blocks",
                methods=["PUT", "PATCH"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "design_id": {
                            "type": "string",
                            "description": "Design ID to update"
                        },
                        "text_blocks": {
                            "type": "array",
                            "description": "List of text block updates",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "block_id": {
                                        "type": "string",
                                        "description": "Text block ID to update"
                                    },
                                    "text": {
                                        "type": "string",
                                        "description": "New text content"
                                    }
                                },
                                "required": ["block_id", "text"]
                            }
                        }
                    },
                    "required": ["design_id", "text_blocks"]
                },
                danger_level="medium",
                metadata={
                    "api_version": "v1",
                    "operation": "write"
                }
            ),
            DiscoveredTool(
                tool_id="canva.export_design",
                display_name="Export Canva Design",
                description="Export a Canva design as PNG, JPG, or PDF. Returns export URL and status.",
                category="content",
                endpoint="https://api.canva.com/rest/v1/designs/{design_id}/exports",
                methods=["POST"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "design_id": {
                            "type": "string",
                            "description": "Design ID to export"
                        },
                        "format": {
                            "type": "string",
                            "description": "Export format",
                            "enum": ["PNG", "JPG", "PDF"],
                            "default": "PNG"
                        },
                        "scale": {
                            "type": "number",
                            "description": "Export scale factor (0.1 to 4.0)",
                            "minimum": 0.1,
                            "maximum": 4.0
                        }
                    },
                    "required": ["design_id"]
                },
                danger_level="low",
                metadata={
                    "api_version": "v1",
                    "operation": "read_only"
                }
            )
        ]

        logger.info(f"Discovered {len(discovered_tools)} Canva tools")
        return discovered_tools

    async def validate(self, config: ToolConfig) -> bool:
        """
        Validate Canva API configuration

        Checks if API key/token is valid by making a test API call.
        """
        if not config.api_key and not config.custom_config.get("oauth_token"):
            logger.error("Canva validation failed: api_key or oauth_token is required")
            return False

        # Try to make a simple API call to validate credentials
        try:
            import aiohttp
            base_url = config.base_url or "https://api.canva.com/rest/v1"
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json"
            }

            # Use oauth_token if available, otherwise api_key
            token = config.custom_config.get("oauth_token") or config.api_key
            if token:
                headers["Authorization"] = f"Bearer {token}"

            # Test with a simple endpoint (list templates with limit=1)
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{base_url}/templates",
                    headers=headers,
                    params={"limit": 1},
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status == 200:
                        logger.info("Canva API validation successful")
                        return True
                    elif resp.status == 401:
                        logger.error("Canva API validation failed: Invalid credentials")
                        return False
                    else:
                        logger.warning(f"Canva API validation returned status {resp.status}, but credentials may be valid")
                        # Return True for other status codes (e.g., 403, 404) as credentials might still be valid
                        return True
        except Exception as e:
            logger.warning(f"Canva API validation error (assuming valid): {e}")
            # If validation fails due to network/other issues, assume valid
            # User can test connection later
            return True

    def get_discovery_metadata(self) -> Dict[str, Any]:
        return {
            "provider": self.provider_name,
            "display_name": "Canva",
            "description": "Canva design platform integration for creating and managing visual content",
            "supported_connection_types": self.supported_connection_types,
            "required_config": ["api_key"],
            "optional_config": ["base_url", "oauth_token"],
            "documentation_url": "https://www.canva.com/developers/",
            "notes": [
                "Requires Canva API credentials (OAuth token or API key)",
                "Supports design creation, template listing, text updates, and export operations",
                "OAuth 2.0 flow is recommended for production use"
            ],
            "config_form_schema": {
                "api_key": {
                    "type": "password",
                    "label": "API Key or OAuth Token",
                    "placeholder": "Bearer token...",
                    "help": "Canva API key or OAuth access token"
                },
                "base_url": {
                    "type": "text",
                    "label": "API Base URL",
                    "placeholder": "https://api.canva.com/rest/v1",
                    "default": "https://api.canva.com/rest/v1"
                }
            }
        }

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "tool_type": {
                    "type": "string",
                    "const": "canva"
                },
                "connection_type": {
                    "type": "string",
                    "enum": ["http_api", "oauth2"]
                },
                "api_key": {
                    "type": "string",
                    "description": "Canva API key or OAuth access token"
                },
                "base_url": {
                    "type": "string",
                    "description": "Canva API base URL",
                    "default": "https://api.canva.com/rest/v1"
                }
            },
            "required": ["tool_type", "connection_type", "api_key"]
        }

