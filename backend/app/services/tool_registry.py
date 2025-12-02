"""
Tool Registry Service.

Generic tool registration service supporting multiple tool types discovery and management.

Design Principles:
- Platform neutral: not bound to any specific tool type
- Plugin-based: extend via ToolDiscoveryProvider
- Open-closed: extend functionality without modifying Core code
"""
import json
import os
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
import logging

from backend.app.models.tool_registry import RegisteredTool, ToolConnectionModel
from backend.app.services.tools.discovery_provider import (
    ToolDiscoveryProvider,
    ToolConfig,
    DiscoveredTool,
    GenericHTTPToolProvider
)
from backend.app.services.tools.base import ToolConnection
try:
    from backend.app.services.tools.registry import register_dynamic_tool, unregister_dynamic_tool
except ImportError:
    # Fallback if registry not yet updated
    def register_dynamic_tool(tool_id: str, connection: ToolConnection):
        pass
    def unregister_dynamic_tool(tool_id: str):
        pass

logger = logging.getLogger(__name__)


class ToolRegistryService:
    """
    Generic Tool Registration Service

    Features:
    - Tool type agnostic
    - Extend discovery logic via ToolDiscoveryProvider
    - Responsible for registration, querying, and management only
    """

    def __init__(self, data_dir: str = "./data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.registry_file = self.data_dir / "tool_registry.json"
        self.connections_file = self.data_dir / "tool_connections.json"

        # In-memory cache
        self._tools: Dict[str, RegisteredTool] = {}
        self._connections: Dict[str, ToolConnectionModel] = {}

        # Discovery providers registry
        self._discovery_providers: Dict[str, ToolDiscoveryProvider] = {}

        # Load data
        self._load_registry()

        # Register default providers (built-in)
        self._register_default_providers()

    def _load_registry(self):
        """Load tool registry from disk"""
        if self.registry_file.exists():
            try:
                with open(self.registry_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._tools = {
                        tool_id: RegisteredTool(**tool_data)
                        for tool_id, tool_data in data.items()
                    }
            except Exception as e:
                print(f"Error loading tool registry: {e}")
                self._tools = {}

        if self.connections_file.exists():
            try:
                with open(self.connections_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._connections = {
                        conn_id: ToolConnectionModel(**conn_data)
                        for conn_id, conn_data in data.items()
                    }
            except Exception as e:
                print(f"Error loading connections: {e}")
                self._connections = {}

    def _save_registry(self):
        """Save tool registry to disk"""
        try:
            with open(self.registry_file, 'w', encoding='utf-8') as f:
                json.dump(
                    {tool_id: tool.dict() for tool_id, tool in self._tools.items()},
                    f,
                    indent=2,
                    ensure_ascii=False,
                    default=str
                )
        except Exception as e:
            print(f"Error saving tool registry: {e}")

        try:
            with open(self.connections_file, 'w', encoding='utf-8') as f:
                json.dump(
                    {conn_id: conn.dict() for conn_id, conn in self._connections.items()},
                    f,
                    indent=2,
                    ensure_ascii=False,
                    default=str
                )
        except Exception as e:
            print(f"Error saving connections: {e}")

    def register_discovery_provider(self, provider: ToolDiscoveryProvider):
        """
        Register a tool discovery provider

        Purpose: Allow extensions or users to add custom tool types

        Args:
            provider: Tool discovery provider instance

        Example:
            # Console-Kit Extension registers WordPress provider
            registry.register_discovery_provider(WordPressToolProvider())

            # User custom provider
            registry.register_discovery_provider(MyCustomToolProvider())
        """
        provider_name = provider.provider_name

        if provider_name in self._discovery_providers:
            logger.warning(f"Provider '{provider_name}' already registered, overwriting")

        self._discovery_providers[provider_name] = provider
        logger.info(f"Registered discovery provider: {provider_name}")

    def _register_default_providers(self):
        """Register default providers (generic, platform-agnostic)"""
        # Register generic HTTP Provider (Core built-in)
        self.register_discovery_provider(GenericHTTPToolProvider())

        # Register local filesystem Provider (Core built-in)
        try:
            from backend.app.services.tools.providers.local_filesystem_provider import LocalFilesystemDiscoveryProvider
            self.register_discovery_provider(LocalFilesystemDiscoveryProvider())
        except ImportError:
            logger.warning("Local filesystem provider not available")

        # Register Obsidian Provider (Core built-in)
        try:
            from backend.app.services.tools.providers.obsidian_provider import ObsidianDiscoveryProvider
            self.register_discovery_provider(ObsidianDiscoveryProvider())
        except ImportError:
            logger.warning("Obsidian provider not available")

        # Register Notion Provider (Core built-in)
        try:
            from backend.app.services.tools.providers.notion_provider import NotionDiscoveryProvider
            self.register_discovery_provider(NotionDiscoveryProvider())
        except ImportError:
            logger.warning("Notion provider not available")

        # Register Google Drive Provider (Core built-in)
        try:
            from backend.app.services.tools.providers.google_drive_provider import GoogleDriveDiscoveryProvider
            self.register_discovery_provider(GoogleDriveDiscoveryProvider())
        except ImportError:
            logger.warning("Google Drive provider not available")

        # Register Canva Provider (Core built-in)
        try:
            from backend.app.services.tools.providers.canva_provider import CanvaDiscoveryProvider
            self.register_discovery_provider(CanvaDiscoveryProvider())
        except ImportError:
            logger.warning("Canva provider not available")

    async def discover_tool_capabilities(
        self,
        provider_name: str,
        config: ToolConfig,
        connection_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Discover tool capabilities using specified provider

        Args:
            provider_name: Provider name (e.g., 'wordpress', 'notion')
            config: Tool configuration
            connection_id: Optional connection ID (for association)

        Returns:
            {
                "provider": "wordpress",
                "connection_id": "wp-site-1",
                "discovered_tools": [...],
                "discovery_metadata": {...}
            }

        Raises:
            ValueError: Unknown provider or invalid configuration

        Example:
            # Discover tools using WordPress provider
            result = await registry.discover_tool_capabilities(
                provider_name="wordpress",
                config=ToolConfig(
                    tool_type="wordpress",
                    connection_type="http_api",
                    base_url="https://mysite.com",
                    api_key="username",
                    api_secret="password"
                ),
                connection_id="my-wp-site"
            )
        """
        # Get provider
        provider = self._discovery_providers.get(provider_name)
        if not provider:
            available = list(self._discovery_providers.keys())
            raise ValueError(
                f"Unknown discovery provider: '{provider_name}'. "
                f"Available providers: {available}"
            )

        # Validate configuration
        logger.info(f"Validating config for provider '{provider_name}'...")
        is_valid = await provider.validate(config)
        if not is_valid:
            raise ValueError(f"Invalid configuration for provider '{provider_name}'")

        # Discover tools
        logger.info(f"Discovering tools using provider '{provider_name}'...")
        discovered_tools = await provider.discover(config)

        # Generate connection ID if not provided
        if not connection_id:
            connection_id = f"{provider_name}-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        # Register to local registry
        registered_tools = []
        for discovered_tool in discovered_tools:
            tool_id = f"{connection_id}.{discovered_tool.tool_id}"

            # Determine side_effect_level based on provider and danger_level
            side_effect_level = self._infer_side_effect_level(
                provider_name=provider_name,
                danger_level=discovered_tool.danger_level,
                tool_id=discovered_tool.tool_id,
                methods=discovered_tool.methods
            )

            # Convert to RegisteredTool
            registered_tool = RegisteredTool(
                tool_id=tool_id,
                site_id=connection_id,
                provider=provider_name,
                display_name=discovered_tool.display_name,
                origin_capability_id=discovered_tool.tool_id,
                category=discovered_tool.category,
                description=discovered_tool.description,
                endpoint=discovered_tool.endpoint,
                methods=discovered_tool.methods,
                danger_level=discovered_tool.danger_level,
                input_schema=discovered_tool.input_schema,
                enabled=True,
                read_only=(discovered_tool.danger_level == "high"),
                side_effect_level=side_effect_level,
            )

            self._tools[tool_id] = registered_tool

            # Register in dynamic tool registry
            tool_connection = ToolConnection(
                id=connection_id,
                tool_type=config.tool_type,
                connection_type=config.connection_type,
                api_key=config.api_key,
                api_secret=config.api_secret,
                base_url=config.base_url,
                name=discovered_tool.display_name,
            )
            register_dynamic_tool(tool_id, tool_connection)

            registered_tools.append(registered_tool.dict())

        # Update/Create connection record
        if connection_id in self._connections:
            conn = self._connections[connection_id]
            conn.last_discovery = datetime.now()
        else:
            conn = ToolConnectionModel(
                id=connection_id,
                name=f"{provider_name} - {connection_id}",
                wp_url=config.base_url,  # Legacy field, should be generalized
                wp_username=config.api_key,
                wp_application_password=config.api_secret,
                last_discovery=datetime.now(),
                discovery_method=provider_name,
            )
            self._connections[connection_id] = conn

        # Save to disk
        self._save_registry()

        logger.info(
            f"Successfully discovered {len(registered_tools)} tools "
            f"using provider '{provider_name}'"
        )

        return {
            "provider": provider_name,
            "connection_id": connection_id,
            "discovered_tools": registered_tools,
            "discovery_metadata": provider.get_discovery_metadata(),
        }

    def get_available_providers(self) -> List[Dict[str, Any]]:
        """
        Get all available tool discovery providers

        Returns:
            List of providers (for UI display)

        Example:
            providers = registry.get_available_providers()
            # [
            #     {
            #         "provider": "generic_http",
            #         "description": "Generic HTTP API tool",
            #         "supported_connection_types": ["http_api"],
            #         ...
            #     },
            #     {
            #         "provider": "wordpress",
            #         "description": "WordPress site capability discovery",
            #         ...
            #     }
            # ]
        """
        return [
            provider.get_discovery_metadata()
            for provider in self._discovery_providers.values()
        ]

    def get_tools(
        self,
        site_id: Optional[str] = None,
        category: Optional[str] = None,
        enabled_only: bool = True,
    ) -> List[RegisteredTool]:
        """Get registered tools with filters"""
        tools = list(self._tools.values())

        if site_id:
            tools = [t for t in tools if t.site_id == site_id]

        if category:
            tools = [t for t in tools if t.category == category]

        if enabled_only:
            tools = [t for t in tools if t.enabled]

        return tools

    def get_tool(self, tool_id: str) -> Optional[RegisteredTool]:
        """Get a specific tool by ID"""
        return self._tools.get(tool_id)

    def update_tool(
        self,
        tool_id: str,
        enabled: Optional[bool] = None,
        read_only: Optional[bool] = None,
        allowed_agent_roles: Optional[List[str]] = None,
    ) -> Optional[RegisteredTool]:
        """Update tool settings"""
        tool = self._tools.get(tool_id)
        if not tool:
            return None

        if enabled is not None:
            tool.enabled = enabled
        if read_only is not None:
            tool.read_only = read_only
        if allowed_agent_roles is not None:
            tool.allowed_agent_roles = allowed_agent_roles

        tool.updated_at = datetime.now()
        self._save_registry()

        return tool

    def get_connections(self) -> List[ToolConnectionModel]:
        """Get all tool connections"""
        return list(self._connections.values())

    def get_connection(self, connection_id: str) -> Optional[ToolConnectionModel]:
        """Get a specific connection"""
        return self._connections.get(connection_id)

    def create_connection(
        self,
        connection_id: str,
        name: str,
        wp_url: str,
        wp_username: str,
        wp_application_password: str,
    ) -> ToolConnectionModel:
        """Create a new WordPress connection"""
        conn = ToolConnectionModel(
            id=connection_id,
            name=name,
            wp_url=wp_url,
            wp_username=wp_username,
            wp_application_password=wp_application_password,
        )
        self._connections[connection_id] = conn
        self._save_registry()
        return conn

    def delete_connection(self, connection_id: str) -> bool:
        """Delete a connection and all its tools"""
        if connection_id not in self._connections:
            return False

        # Remove all tools for this connection
        tool_ids_to_remove = [
            tool_id for tool_id, tool in self._tools.items()
            if tool.site_id == connection_id
        ]
        for tool_id in tool_ids_to_remove:
            del self._tools[tool_id]
            # Unregister from dynamic tool registry
            unregister_dynamic_tool(tool_id)

        del self._connections[connection_id]
        self._save_registry()
        return True

    def get_tools_for_agent_role(self, agent_role: str) -> List[RegisteredTool]:
        """Get tools available for a specific agent role"""
        tools = []
        for tool in self._tools.values():
            if not tool.enabled:
                continue

            # If tool has allowed_agent_roles, check if role is allowed
            if tool.allowed_agent_roles:
                if agent_role not in tool.allowed_agent_roles:
                    continue

            tools.append(tool)

        return tools

    def _infer_side_effect_level(
        self,
        provider_name: str,
        danger_level: str,
        tool_id: str,
        methods: List[str]
    ) -> str:
        """
        Infer side_effect_level for a tool based on provider and characteristics

        Mapping rules:
        1. GET-only methods = readonly (reading from external is safe)
        2. External providers with write operations = external_write
        3. Local filesystem write = external_write
        4. High danger_level = external_write (conservative)
        5. Default = soft_write (conservative)

        Args:
            provider_name: Provider name (wordpress, notion, google_drive, etc.)
            danger_level: Tool danger level (low, medium, high)
            tool_id: Tool identifier (for pattern matching)
            methods: HTTP methods supported by tool

        Returns:
            side_effect_level: "readonly", "soft_write", or "external_write"
        """
        # Rule 1: GET-only methods = readonly
        read_only_methods = ["GET"]
        if methods and all(m.upper() in read_only_methods for m in methods):
            return "readonly"

        # Rule 2: Provider-based rules
        provider_lower = provider_name.lower()

        # External providers (WordPress, Notion, Google Drive)
        if provider_lower in ["wordpress", "notion", "google_drive"]:
            # Read operations (list, read, search) = readonly
            if any(keyword in tool_id.lower() for keyword in ["read", "list", "search", "get"]):
                return "readonly"
            # Write operations = external_write
            return "external_write"

        # Local filesystem provider
        if provider_lower == "local_filesystem":
            # Read operations = readonly
            if any(keyword in tool_id.lower() for keyword in ["read", "list", "search"]):
                return "readonly"
            # Write operations = external_write (writes to local files)
            return "external_write"

        # Rule 3: High danger level = external_write (conservative)
        if danger_level == "high":
            return "external_write"

        # Rule 4: Default = soft_write (conservative, requires CTA)
        return "soft_write"

    async def discover_wordpress_capabilities(
        self,
        connection_id: str,
        wp_url: str,
        wp_username: str,
        wp_password: str,
    ) -> Dict[str, Any]:
        """
        Discover WordPress capabilities (backward compatibility method)

        This method is kept for backward compatibility with legacy endpoints.
        New code should use discover_tool_capabilities() with provider="wordpress".

        Args:
            connection_id: Connection identifier
            wp_url: WordPress site URL
            wp_username: WordPress username
            wp_password: WordPress application password

        Returns:
            Discovery result dictionary
        """
        from backend.app.services.tools.discovery_provider import ToolConfig

        # Check if WordPress provider is registered
        if "wordpress" not in self._discovery_providers:
            # Try to register WordPress provider from console-kit extension
            try:
                from backend.app.extensions.console_kit import register_console_kit_tools
                register_console_kit_tools(self)
            except ImportError:
                logger.warning("WordPress provider not available (console-kit extension not installed)")

        # Use generic discovery method
        config = ToolConfig(
            tool_type="wordpress",
            connection_type="http_api",
            base_url=wp_url,
            api_key=wp_username,
            api_secret=wp_password
        )

        return await self.discover_tool_capabilities(
            provider_name="wordpress",
            config=config,
            connection_id=connection_id
        )

