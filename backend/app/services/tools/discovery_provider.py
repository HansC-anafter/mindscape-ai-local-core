"""
Tool Discovery Provider - Abstract Interface

Defines the abstract interface for tool discovery providers, allowing different
platforms/tool types to implement their own discovery logic.

Purpose:
- Core provides abstract interface, agnostic to specific tool types
- Extensions implement specific discovery logic (WordPress, Notion, GitHub, etc.)
- Open-source users can freely add custom tool providers

Design Principles:
- Completely platform-neutral, not bound to any specific service
- Extend through registration mechanism, no Core code modification
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class ToolConfig(BaseModel):
    """
    Generic tool configuration

    Purpose: Describes how to connect to external tools/services
    Features: Platform-neutral, supports multiple connection types
    """

    tool_type: str = Field(
        ...,
        description="Tool type (e.g., 'wordpress', 'notion', 'github')"
    )

    connection_type: str = Field(
        ...,
        description="Connection type: 'http_api' | 'mcp' | 'local_script' | 'custom'"
    )

    base_url: Optional[str] = Field(
        None,
        description="Service URL (for HTTP API connections)"
    )

    api_key: Optional[str] = Field(
        None,
        description="API Key (for authentication)"
    )

    api_secret: Optional[str] = Field(
        None,
        description="API Secret (for authentication)"
    )

    custom_config: Dict[str, Any] = Field(
        default_factory=dict,
        description="Custom configuration (tool-specific settings)"
    )


class DiscoveredTool(BaseModel):
    """
    Discovered tool capability

    Purpose: Describes available tools discovered from external services
    Features: Standardized format, platform-agnostic
    """

    tool_id: str = Field(
        ...,
        description="Unique tool identifier"
    )

    display_name: str = Field(
        ...,
        description="Tool display name"
    )

    description: str = Field(
        ...,
        description="Tool description"
    )

    category: str = Field(
        ...,
        description="Tool category (e.g., 'content', 'data', 'automation')"
    )

    endpoint: Optional[str] = Field(
        None,
        description="Tool endpoint (for HTTP API)"
    )

    methods: List[str] = Field(
        default_factory=list,
        description="Supported HTTP methods (e.g., ['GET', 'POST'])"
    )

    input_schema: Dict[str, Any] = Field(
        default_factory=dict,
        description="Input parameters JSON Schema"
    )

    output_schema: Optional[Dict[str, Any]] = Field(
        None,
        description="Output format JSON Schema"
    )

    danger_level: str = Field(
        default="low",
        description="Danger level: 'low' | 'medium' | 'high'"
    )

    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata"
    )


class ToolDiscoveryProvider(ABC):
    """
    Tool Discovery Provider Abstract Interface

    Purpose: Define how to discover available tool capabilities from external services
    Implementation: Each platform/tool type implements its own discovery logic

    Design Pattern: Strategy Pattern
    - Core depends on abstraction, not concrete implementations
    - Extensions provide concrete implementations
    - Dynamically extend through registration mechanism

    Example Implementations:
    - WordPressToolProvider (Community Extension)
    - NotionToolProvider (Community Extension)
    - GitHubToolProvider (Community Extension)
    - CustomAPIProvider (User-defined)
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """
        Provider name

        Returns: Unique identifier (e.g., 'wordpress', 'notion', 'custom')
        Purpose: Register and lookup providers
        """
        pass

    @property
    @abstractmethod
    def supported_connection_types(self) -> List[str]:
        """
        Supported connection types

        Returns: ['http_api', 'mcp', 'local_script'], etc.
        Purpose: UI display and validation
        """
        pass

    @abstractmethod
    async def discover(self, config: ToolConfig) -> List[DiscoveredTool]:
        """
        Discover available tools from configuration

        Args:
            config: Tool connection configuration

        Returns:
            List of discovered tools

        Raises:
            ValueError: Invalid configuration
            ConnectionError: Cannot connect to service

        Purpose:
        - Connect to external service (e.g., WordPress REST API)
        - Scan available capabilities (e.g., endpoints provided by WordPress Plugin)
        - Convert to standardized DiscoveredTool format
        """
        pass

    @abstractmethod
    async def validate(self, config: ToolConfig) -> bool:
        """
        Validate configuration

        Args:
            config: Tool connection configuration

        Returns:
            True if configuration is valid and can connect

        Purpose:
        - Check required fields
        - Test connection
        - Verify authentication credentials
        """
        pass

    def get_discovery_metadata(self) -> Dict[str, Any]:
        """
        Get discovery provider metadata

        Returns:
            Provider metadata (for UI display)

        Purpose:
        - Display available tool types in frontend
        - Show required configuration fields
        - Display usage instructions
        """
        return {
            "provider": self.provider_name,
            "description": f"{self.provider_name} tool discovery provider",
            "supported_connection_types": self.supported_connection_types,
            "required_config": ["base_url", "api_key"],
            "optional_config": ["api_secret", "custom_config"],
            "documentation_url": None
        }

    def get_config_schema(self) -> Dict[str, Any]:
        """
        Get configuration JSON Schema

        Returns:
            Configuration JSON Schema (for frontend form generation)

        Purpose:
        - Auto-generate configuration forms
        - Validate user input
        """
        return {
            "type": "object",
            "properties": {
                "tool_type": {
                    "type": "string",
                    "const": self.provider_name
                },
                "connection_type": {
                    "type": "string",
                    "enum": self.supported_connection_types
                },
                "base_url": {
                    "type": "string",
                    "format": "uri",
                    "description": "Service URL"
                },
                "api_key": {
                    "type": "string",
                    "description": "API Key"
                },
                "api_secret": {
                    "type": "string",
                    "description": "API Secret"
                }
            },
            "required": ["tool_type", "connection_type"]
        }


class GenericHTTPToolProvider(ToolDiscoveryProvider):
    """
    Generic HTTP API Tool Provider

    Purpose: Core built-in, supports any service compliant with REST API standards
    Features:
    - No dedicated plugin required
    - User manually configures endpoints and parameters
    - Suitable for simple API integrations
    """

    @property
    def provider_name(self) -> str:
        return "generic_http"

    @property
    def supported_connection_types(self) -> List[str]:
        return ["http_api"]

    async def discover(self, config: ToolConfig) -> List[DiscoveredTool]:
        """
        Generic HTTP provider does not auto-discover, requires manual tool definition
        """
        # Could implement simple OpenAPI/Swagger spec parsing here
        # Currently returns empty list, user needs to manually register
        return []

    async def validate(self, config: ToolConfig) -> bool:
        """Validate HTTP connection"""
        if not config.base_url:
            return False

        # Can add simple ping test
        # import aiohttp
        # async with aiohttp.ClientSession() as session:
        #     async with session.get(config.base_url) as resp:
        #         return resp.status < 500

        return True

    def get_discovery_metadata(self) -> Dict[str, Any]:
        return {
            "provider": self.provider_name,
            "description": "Generic HTTP API tool (manual configuration)",
            "supported_connection_types": self.supported_connection_types,
            "required_config": ["base_url"],
            "optional_config": ["api_key", "api_secret"],
            "documentation_url": "https://docs.mindscape-ai.com/tools/generic-http",
            "notes": "Suitable for simple REST API integrations, requires manual tool endpoint definition"
        }
