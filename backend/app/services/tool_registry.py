"""
Tool Registry Service.

Generic tool registration service supporting multiple tool types discovery and management.

Design Principles:
- Platform neutral: not bound to any specific tool type
- Plugin-based: extend via ToolDiscoveryProvider
- Open-closed: extend functionality without modifying Core code
- PostgreSQL storage with JSON fallback for migration safety
"""

import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


import logging

from sqlalchemy import text

from backend.app.models.tool_registry import RegisteredTool, ToolConnectionModel
from backend.app.services.tool_registry_core.discovery import (
    build_dynamic_tool_connection,
    build_registered_tool,
    upsert_discovery_connection,
)
from backend.app.services.tool_registry_core.persistence import (
    load_registry_from_database,
    load_registry_from_json,
    save_registry_to_database,
    save_registry_to_json,
)
from backend.app.services.tools.discovery_provider import (
    ToolDiscoveryProvider,
    ToolConfig,
    DiscoveredTool,
    GenericHTTPToolProvider,
)
from backend.app.services.tool_registry_core.connections import (
    create_connection as create_tool_connection,
    create_connection_legacy as create_tool_connection_legacy,
    delete_connection as delete_tool_connection,
    export_as_templates as export_connection_templates,
    get_connection as get_tool_connection,
    get_connections as get_all_tool_connections,
    get_connections_by_profile as get_tool_connections_by_profile,
    get_connections_by_role as get_tool_connections_by_role,
    get_connections_by_tool_type as get_tool_connections_by_type,
    record_connection_usage as record_tool_connection_usage,
    update_connection as update_tool_connection,
    update_validation_status as update_tool_connection_validation_status,
)
from backend.app.services.tool_registry_core.tools import (
    get_available_provider_metadata,
    get_tool as get_registered_tool,
    get_tools as get_registered_tools,
    get_tools_for_agent_role as get_registered_tools_for_agent_role,
    infer_side_effect_level,
    update_tool as update_registered_tool,
)
from backend.app.services.tools.base import ToolConnection
from backend.app.services.stores.postgres_base import PostgresStoreBase

try:
    from backend.app.services.tools.registry import (
        register_dynamic_tool,
        unregister_dynamic_tool,
    )
except ImportError:
    # Fallback if registry not yet updated
    def register_dynamic_tool(tool_id: str, connection: ToolConnection):
        pass

    def unregister_dynamic_tool(tool_id: str):
        pass


logger = logging.getLogger(__name__)


class ToolRegistryService(PostgresStoreBase):
    """
    Generic Tool Registration Service

    Features:
    - Tool type agnostic
    - Extend discovery logic via ToolDiscoveryProvider
    - Responsible for registration, querying, and management only
    """

    # Class-level flags to prevent repeated heavy init across instances
    _schema_ensured = False
    _registry_loaded = False
    _providers_registered = False
    _shared_tools: Dict[str, RegisteredTool] = {}
    _shared_connections: Dict[tuple, ToolConnectionModel] = {}
    _shared_providers: Dict[str, ToolDiscoveryProvider] = {}
    _shared_tables_ready = False

    def __init__(
        self,
        data_dir: str = "./data",
        db_path: Optional[str] = None,
        db_role: str = "core",
    ):
        super().__init__(db_role=db_role)
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # Legacy SQLite database path (retained for JSON fallback)
        if db_path:
            self.db_path = db_path
        else:
            self.db_path = str(self.data_dir / "tool_registry.db")

        # Legacy JSON files (for backward compatibility during migration)
        self.registry_file = self.data_dir / "tool_registry.json"
        self.connections_file = self.data_dir / "tool_connections.json"

        # Point instance caches to shared class-level caches
        self._tools = ToolRegistryService._shared_tools
        self._connections = ToolRegistryService._shared_connections
        self._discovery_providers = ToolRegistryService._shared_providers

        # Initialize database (only once per process)
        self._tables_ready = ToolRegistryService._shared_tables_ready
        if not ToolRegistryService._schema_ensured:
            self._ensure_tables()
            ToolRegistryService._shared_tables_ready = self._tables_ready
            ToolRegistryService._schema_ensured = True
        else:
            self._tables_ready = ToolRegistryService._shared_tables_ready

        # Load data only if tables exist (only once per process)
        if self._tables_ready and not ToolRegistryService._registry_loaded:
            self._load_registry()
            ToolRegistryService._registry_loaded = True

        # Register default providers (built-in) only once per process
        if not ToolRegistryService._providers_registered:
            self._register_default_providers()
            ToolRegistryService._providers_registered = True

    def _ensure_tables(self):
        """Validate required tables exist (managed by Alembic migrations)."""
        required_tables = {"tool_registry", "tool_connections"}
        with self.factory.get_connection(role=self.db_role) as conn:
            rows = conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
                )
            ).fetchall()
            existing = {row.table_name for row in rows}

        missing = required_tables - existing
        if missing:
            missing_str = ", ".join(sorted(missing))
            logger.warning(
                "Missing PostgreSQL tables: %s. "
                "Will be created by migration orchestrator in startup_event.",
                missing_str,
            )
            return
        self._tables_ready = True

    def _load_registry(self):
        """Load tool registry from PostgreSQL database"""
        try:
            load_registry_from_database(
                factory=self.factory,
                db_role=self.db_role,
                deserialize_json=self.deserialize_json,
                from_isoformat=self.from_isoformat,
                tools_by_id=self._tools,
                connections_by_key=self._connections,
                utc_now=_utc_now,
                logger=logger,
            )
            logger.info(
                f"Loaded {len(self._tools)} tools and {len(self._connections)} connections from database"
            )
        except Exception as e:
            logger.error(f"Error loading registry from database: {e}")
            self._load_registry_from_json()

    def _load_registry_from_json(self):
        """Load tool registry from JSON files (migration fallback)"""
        load_registry_from_json(
            registry_file=self.registry_file,
            connections_file=self.connections_file,
            tools_by_id=self._tools,
            connections_by_key=self._connections,
            logger=logger,
        )

    def _save_registry(self):
        """Save tool registry to PostgreSQL database"""
        try:
            save_registry_to_database(
                transaction=self.transaction,
                serialize_json=self.serialize_json,
                tools_by_id=self._tools,
                connections_by_key=self._connections,
            )
        except Exception as e:
            logger.error(f"Error saving registry to database: {e}")
            self._save_registry_to_json()

    def _save_registry_to_json(self):
        """Save tool registry to JSON files (migration fallback)"""
        save_registry_to_json(
            registry_file=self.registry_file,
            connections_file=self.connections_file,
            tools_by_id=self._tools,
            connections_by_key=self._connections,
            logger=logger,
        )

    def register_discovery_provider(self, provider: ToolDiscoveryProvider):
        """
        Register a tool discovery provider

        Purpose: Allow extensions or users to add custom tool types

        Args:
            provider: Tool discovery provider instance

        Example:
            # External extension registers WordPress provider
            registry.register_discovery_provider(WordPressToolProvider())

            # User custom provider
            registry.register_discovery_provider(MyCustomToolProvider())
        """
        provider_name = provider.provider_name

        if provider_name in self._discovery_providers:
            logger.warning(
                f"Provider '{provider_name}' already registered, overwriting"
            )

        self._discovery_providers[provider_name] = provider
        logger.debug(f"Registered discovery provider: {provider_name}")

    def _register_default_providers(self):
        """Register default providers (generic, platform-agnostic)"""
        # Register generic HTTP Provider (Core built-in)
        self.register_discovery_provider(GenericHTTPToolProvider())

        # Register local filesystem Provider (Core built-in)
        try:
            from backend.app.services.tools.providers.local_filesystem_provider import (
                LocalFilesystemDiscoveryProvider,
            )

            self.register_discovery_provider(LocalFilesystemDiscoveryProvider())
        except ImportError:
            logger.warning("Local filesystem provider not available")

        # Register Obsidian Provider (Core built-in)
        try:
            from backend.app.services.tools.providers.obsidian_provider import (
                ObsidianDiscoveryProvider,
            )

            self.register_discovery_provider(ObsidianDiscoveryProvider())
        except ImportError:
            logger.warning("Obsidian provider not available")

        # Register Notion Provider (Core built-in)
        try:
            from backend.app.services.tools.providers.notion_provider import (
                NotionDiscoveryProvider,
            )

            self.register_discovery_provider(NotionDiscoveryProvider())
        except ImportError:
            logger.warning("Notion provider not available")

        # Register Google Drive Provider (Core built-in)
        try:
            from backend.app.services.tools.providers.google_drive_provider import (
                GoogleDriveDiscoveryProvider,
            )

            self.register_discovery_provider(GoogleDriveDiscoveryProvider())
        except ImportError:
            logger.warning("Google Drive provider not available")

        # Canva Provider moved to capability pack
        # Removed: Canva is now installed as a capability pack
        # If needed, discovery provider will be loaded from the installed capability pack

        # Register Slack Provider (Core built-in)
        try:
            from backend.app.services.tools.providers.slack_provider import (
                SlackDiscoveryProvider,
            )

            self.register_discovery_provider(SlackDiscoveryProvider())
        except ImportError:
            logger.warning("Slack provider not available")

        # Register Airtable Provider (Core built-in)
        try:
            from backend.app.services.tools.providers.airtable_provider import (
                AirtableDiscoveryProvider,
            )

            self.register_discovery_provider(AirtableDiscoveryProvider())
        except ImportError:
            logger.warning("Airtable provider not available")

        # Register Google Sheets Provider (Core built-in)
        try:
            from backend.app.services.tools.providers.google_sheets_provider import (
                GoogleSheetsDiscoveryProvider,
            )

            self.register_discovery_provider(GoogleSheetsDiscoveryProvider())
        except ImportError:
            logger.warning("Google Sheets provider not available")

        # Register GitHub Provider (Core built-in)
        try:
            from backend.app.services.tools.providers.github_provider import (
                GitHubDiscoveryProvider,
            )

            self.register_discovery_provider(GitHubDiscoveryProvider())
        except ImportError:
            logger.warning("GitHub provider not available")

        # Register Twitter Provider (Core built-in)
        try:
            from backend.app.services.tools.providers.twitter_provider import (
                TwitterDiscoveryProvider,
            )

            self.register_discovery_provider(TwitterDiscoveryProvider())
        except ImportError:
            logger.warning("Twitter provider not available")

        # Register Facebook Provider (Core built-in)
        try:
            from backend.app.services.tools.providers.facebook_provider import (
                FacebookDiscoveryProvider,
            )

            self.register_discovery_provider(FacebookDiscoveryProvider())
        except ImportError:
            logger.warning("Facebook provider not available")

        # Register Instagram Provider (Core built-in)
        try:
            from backend.app.services.tools.providers.instagram_provider import (
                InstagramDiscoveryProvider,
            )

            self.register_discovery_provider(InstagramDiscoveryProvider())
        except ImportError:
            logger.warning("Instagram provider not available")

        # Register LinkedIn Provider (Core built-in)
        try:
            from backend.app.services.tools.providers.linkedin_provider import (
                LinkedInDiscoveryProvider,
            )

            self.register_discovery_provider(LinkedInDiscoveryProvider())
        except ImportError:
            logger.warning("LinkedIn provider not available")

        # Register YouTube Provider (Core built-in)
        try:
            from backend.app.services.tools.providers.youtube_provider import (
                YouTubeDiscoveryProvider,
            )

            self.register_discovery_provider(YouTubeDiscoveryProvider())
        except ImportError:
            logger.warning("YouTube provider not available")

        # Register Line Provider (Core built-in)
        try:
            from backend.app.services.tools.providers.line_provider import (
                LineDiscoveryProvider,
            )

            self.register_discovery_provider(LineDiscoveryProvider())
        except ImportError:
            logger.warning("Line provider not available")

    async def discover_tool_capabilities(
        self,
        provider_name: str,
        config: ToolConfig,
        connection_id: Optional[str] = None,
        profile_id: str = "default-user",
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

        # Remove old tools for this connection before registering new ones
        # This prevents tool accumulation when connection is updated
        tool_ids_to_remove = [
            tool_id
            for tool_id, tool in self._tools.items()
            if tool.site_id == connection_id and tool.provider == provider_name
        ]
        for tool_id in tool_ids_to_remove:
            del self._tools[tool_id]
            try:
                from backend.app.shared.tool_executor import unregister_dynamic_tool

                unregister_dynamic_tool(tool_id)
            except Exception as e:
                logger.warning(f"Failed to unregister dynamic tool {tool_id}: {e}")

        if tool_ids_to_remove:
            logger.info(
                f"Removed {len(tool_ids_to_remove)} old tools for connection {connection_id}"
            )

        # Register to local registry
        registered_tools = []
        for discovered_tool in discovered_tools:
            tool_id = f"{connection_id}.{discovered_tool.tool_id}"

            # Determine side_effect_level based on provider and danger_level
            side_effect_level = self._infer_side_effect_level(
                provider_name=provider_name,
                danger_level=discovered_tool.danger_level,
                tool_id=discovered_tool.tool_id,
                methods=discovered_tool.methods,
            )

            # Convert to RegisteredTool
            # Determine scope from connection (data_source_type indicates it's a data source)
            connection_model = self.get_connection(connection_id, profile_id=profile_id)
            tool_scope = "profile"  # Default scope
            tool_tenant_id = None
            tool_owner_profile_id = profile_id  # Default to profile_id

            if connection_model:
                # If connection has data_source_type, use its scope
                # Note: ToolConnectionModel doesn't have data_source_type, but we can check via DataSourceService
                # For now, use profile scope by default
                tool_scope = "profile"
                tool_owner_profile_id = connection_model.profile_id

                # TODO: When DataSource is fully integrated, check data_source_type
                # and set scope accordingly (tenant vs profile)

            registered_tool = build_registered_tool(
                tool_id=tool_id,
                connection_id=connection_id,
                provider_name=provider_name,
                discovered_tool=discovered_tool,
                side_effect_level=side_effect_level,
                tool_scope=tool_scope,
                tool_tenant_id=tool_tenant_id,
                tool_owner_profile_id=tool_owner_profile_id,
            )
            self._tools[tool_id] = registered_tool

            # Register in dynamic tool registry
            tool_connection = build_dynamic_tool_connection(
                connection_id=connection_id,
                config=config,
                display_name=discovered_tool.display_name,
            )
            register_dynamic_tool(tool_id, tool_connection)

            registered_tools.append(registered_tool.model_dump())

        upsert_discovery_connection(
            self._connections,
            profile_id=profile_id,
            connection_id=connection_id,
            provider_name=provider_name,
            config=config,
            utc_now=_utc_now,
        )

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
        return get_available_provider_metadata(self._discovery_providers)

    def get_tools(
        self,
        site_id: Optional[str] = None,
        category: Optional[str] = None,
        enabled_only: bool = True,
        scope: Optional[str] = None,
        tenant_id: Optional[str] = None,
        profile_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
    ) -> List[RegisteredTool]:
        """
        Get registered tools with filters

        Args:
            site_id: Filter by site/connection ID
            category: Filter by category
            enabled_only: Return only enabled tools
            scope: Filter by scope (system, tenant, profile, workspace)
            tenant_id: Filter by tenant ID (for tenant-scoped tools)
            profile_id: Filter by profile ID (for profile-scoped tools)
            workspace_id: Workspace ID (for applying overlay)

        Returns:
            List of RegisteredTool objects (with overlay applied if workspace_id provided)
        """
        return get_registered_tools(
            self._tools,
            site_id=site_id,
            category=category,
            enabled_only=enabled_only,
            scope=scope,
            tenant_id=tenant_id,
            profile_id=profile_id,
            workspace_id=workspace_id,
        )

    def get_tool(self, tool_id: str) -> Optional[RegisteredTool]:
        """Get a specific tool by ID"""
        return get_registered_tool(self._tools, tool_id)

    def update_tool(
        self,
        tool_id: str,
        enabled: Optional[bool] = None,
        read_only: Optional[bool] = None,
        allowed_agent_roles: Optional[List[str]] = None,
    ) -> Optional[RegisteredTool]:
        """Update tool settings"""
        return update_registered_tool(
            self._tools,
            save_registry=self._save_registry,
            tool_id=tool_id,
            enabled=enabled,
            read_only=read_only,
            allowed_agent_roles=allowed_agent_roles,
        )

    def get_connections(
        self, profile_id: Optional[str] = None
    ) -> List[ToolConnectionModel]:
        """
        Get all tool connections

        Args:
            profile_id: Optional profile ID to filter connections. If None, returns all connections.

        Returns:
            List of tool connections
        """
        return get_all_tool_connections(self._connections, profile_id=profile_id)

    def get_connection(
        self, connection_id: Optional[str] = None, profile_id: Optional[str] = None
    ) -> Any:
        """
        Get a specific connection

        Args:
            connection_id: Connection ID. If None, returns the underlying Postgres connection.
            profile_id: Optional profile ID. If None, searches across all profiles (backward compatibility).

        Returns:
            Tool connection if found, DB connection context manager if None, None otherwise
        """
        return get_tool_connection(
            self._connections,
            connection_id=connection_id,
            profile_id=profile_id,
            get_db_connection=super().get_connection,
        )

    def create_connection(
        self,
        connection: ToolConnectionModel,
    ) -> ToolConnectionModel:
        """
        Create a new tool connection

        Args:
            connection: ToolConnectionModel instance with all required fields

        Returns:
            Created connection
        """
        return create_tool_connection(
            self._connections,
            connection=connection,
            save_registry=self._save_registry,
            utc_now=_utc_now,
        )

    def create_connection_legacy(
        self,
        connection_id: str,
        name: str,
        wp_url: str,
        wp_username: str,
        wp_application_password: str,
        profile_id: str = "default-user",
    ) -> ToolConnectionModel:
        """
        Create a new WordPress connection (legacy method for backward compatibility)

        Args:
            connection_id: Connection ID
            name: Connection name
            wp_url: WordPress site URL
            wp_username: WordPress username
            wp_application_password: WordPress application password
            profile_id: Profile ID (defaults to "default-user")

        Returns:
            Created connection
        """
        return create_tool_connection_legacy(
            create_connection_fn=self.create_connection,
            connection_id=connection_id,
            name=name,
            wp_url=wp_url,
            wp_username=wp_username,
            wp_application_password=wp_application_password,
            profile_id=profile_id,
        )

    def delete_connection(
        self, connection_id: str, profile_id: Optional[str] = None
    ) -> bool:
        """
        Delete a connection and all its tools

        Args:
            connection_id: Connection ID
            profile_id: Optional profile ID. If None, deletes from all profiles (backward compatibility).

        Returns:
            True if deleted, False if not found
        """
        return delete_tool_connection(
            self._connections,
            self._tools,
            connection_id=connection_id,
            profile_id=profile_id,
            save_registry=self._save_registry,
            unregister_dynamic_tool_fn=unregister_dynamic_tool,
        )

    def get_connections_by_profile(
        self, profile_id: str, active_only: bool = True
    ) -> List[ToolConnectionModel]:
        """
        Get all tool connections for a profile

        Args:
            profile_id: Profile ID
            active_only: If True, return only active connections

        Returns:
            List of tool connections
        """
        return get_tool_connections_by_profile(
            self._connections,
            profile_id=profile_id,
            active_only=active_only,
        )

    def get_connections_by_tool_type(
        self, profile_id: str, tool_type: str
    ) -> List[ToolConnectionModel]:
        """
        Get all connections for a specific tool type

        Args:
            profile_id: Profile ID
            tool_type: Tool type (e.g., "wordpress", "notion")

        Returns:
            List of tool connections
        """
        return get_tool_connections_by_type(
            self._connections,
            profile_id=profile_id,
            tool_type=tool_type,
        )

    def get_connections_by_role(
        self, profile_id: str, role_id: str
    ) -> List[ToolConnectionModel]:
        """
        Get all connections associated with a specific AI role

        Args:
            profile_id: Profile ID
            role_id: AI role ID

        Returns:
            List of tool connections
        """
        return get_tool_connections_by_role(
            get_connections_by_profile_fn=self.get_connections_by_profile,
            profile_id=profile_id,
            role_id=role_id,
        )

    def update_connection(self, connection: ToolConnectionModel) -> ToolConnectionModel:
        """
        Update a tool connection

        Args:
            connection: Updated connection model

        Returns:
            Updated connection
        """
        return update_tool_connection(
            self._connections,
            connection=connection,
            save_registry=self._save_registry,
            utc_now=_utc_now,
        )

    def record_connection_usage(self, connection_id: str, profile_id: str):
        """
        Record that a connection was used

        Args:
            connection_id: Connection ID
            profile_id: Profile ID
        """
        record_tool_connection_usage(
            self._connections,
            connection_id=connection_id,
            profile_id=profile_id,
            save_registry=self._save_registry,
            utc_now=_utc_now,
        )

    def update_validation_status(
        self,
        connection_id: str,
        profile_id: str,
        is_valid: bool,
        error_message: Optional[str] = None,
    ):
        """
        Update validation status of a connection

        Args:
            connection_id: Connection ID
            profile_id: Profile ID
            is_valid: Whether connection is valid
            error_message: Optional error message
        """
        update_tool_connection_validation_status(
            self._connections,
            connection_id=connection_id,
            profile_id=profile_id,
            is_valid=is_valid,
            error_message=error_message,
            save_registry=self._save_registry,
            utc_now=_utc_now,
        )

    def export_as_templates(self, profile_id: str) -> List[Dict[str, Any]]:
        """
        Export connections as templates (without sensitive data)

        Args:
            profile_id: Profile ID

        Returns:
            List of connection templates
        """
        return export_connection_templates(
            get_connections_by_profile_fn=self.get_connections_by_profile,
            profile_id=profile_id,
        )

    def get_tools_for_agent_role(
        self,
        agent_role: str,
        profile_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
    ) -> List[RegisteredTool]:
        """
        Get tools available for a specific agent role

        Args:
            agent_role: Agent role name
            profile_id: Profile ID (for scope filtering)
            tenant_id: Tenant ID (for scope filtering)
            workspace_id: Workspace ID (for applying overlay)

        Returns:
            List of tools available for the agent role (with overlay applied if workspace_id provided)
        """
        return get_registered_tools_for_agent_role(
            get_tools_fn=self.get_tools,
            agent_role=agent_role,
            profile_id=profile_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
        )

    def _infer_side_effect_level(
        self, provider_name: str, danger_level: str, tool_id: str, methods: List[str]
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
        return infer_side_effect_level(provider_name, danger_level, tool_id, methods)

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
            # Try to register WordPress provider from external extension
            try:
                from backend.app.extensions.console_kit import (
                    register_console_kit_tools,
                )

                register_console_kit_tools(self)
            except ImportError:
                logger.warning(
                    "WordPress provider not available (external extension not installed)"
                )

        # Use generic discovery method
        config = ToolConfig(
            tool_type="wordpress",
            connection_type="http_api",
            base_url=wp_url,
            api_key=wp_username,
            api_secret=wp_password,
        )

        return await self.discover_tool_capabilities(
            provider_name="wordpress", config=config, connection_id=connection_id
        )
