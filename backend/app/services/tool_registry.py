"""Generic DB-backed tool registry service."""

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
    discover_tool_capabilities_for_service,
    discover_wordpress_capabilities_for_service,
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
)
from backend.app.services.tool_registry_core.providers import (
    register_default_providers as register_default_tool_providers,
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
    """DB-backed tool registry facade."""

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
        """Load the registry from PostgreSQL."""
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
        """Load the registry from JSON fallback files."""
        load_registry_from_json(
            registry_file=self.registry_file,
            connections_file=self.connections_file,
            tools_by_id=self._tools,
            connections_by_key=self._connections,
            logger=logger,
        )

    def _save_registry(self):
        """Persist the registry to PostgreSQL."""
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
        """Persist the registry to JSON fallback files."""
        save_registry_to_json(
            registry_file=self.registry_file,
            connections_file=self.connections_file,
            tools_by_id=self._tools,
            connections_by_key=self._connections,
            logger=logger,
        )

    def register_discovery_provider(self, provider: ToolDiscoveryProvider):
        """Register a tool discovery provider."""
        provider_name = provider.provider_name

        if provider_name in self._discovery_providers:
            logger.warning(
                f"Provider '{provider_name}' already registered, overwriting"
            )

        self._discovery_providers[provider_name] = provider
        logger.debug(f"Registered discovery provider: {provider_name}")

    def _register_default_providers(self):
        """Register default platform-agnostic providers."""
        register_default_tool_providers(
            self.register_discovery_provider,
            logger=logger,
        )

    async def discover_tool_capabilities(
        self,
        provider_name: str,
        config: ToolConfig,
        connection_id: Optional[str] = None,
        profile_id: str = "default-user",
    ) -> Dict[str, Any]:
        """Discover tool capabilities using the canonical provider registry."""
        return await discover_tool_capabilities_for_service(
            self,
            provider_name=provider_name,
            config=config,
            connection_id=connection_id,
            profile_id=profile_id,
            register_dynamic_tool_fn=register_dynamic_tool,
            utc_now_fn=_utc_now,
            logger=logger,
        )

    def get_available_providers(self) -> List[Dict[str, Any]]:
        """Return available discovery provider metadata."""
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
        """Return registered tools with optional filters."""
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
        """Return one registered tool by ID."""
        return get_registered_tool(self._tools, tool_id)

    def update_tool(
        self,
        tool_id: str,
        enabled: Optional[bool] = None,
        read_only: Optional[bool] = None,
        allowed_agent_roles: Optional[List[str]] = None,
    ) -> Optional[RegisteredTool]:
        """Update registered tool settings."""
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
        """Return all tool connections, optionally filtered by profile."""
        return get_all_tool_connections(self._connections, profile_id=profile_id)

    def get_connection(
        self, connection_id: Optional[str] = None, profile_id: Optional[str] = None
    ) -> Any:
        """Return a tool connection or the underlying DB connection manager."""
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
        """Create a tool connection."""
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
        """Create a legacy WordPress connection."""
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
        """Delete a connection and its registered tools."""
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
        """Return tool connections for a profile."""
        return get_tool_connections_by_profile(
            self._connections,
            profile_id=profile_id,
            active_only=active_only,
        )

    def get_connections_by_tool_type(
        self, profile_id: str, tool_type: str
    ) -> List[ToolConnectionModel]:
        """Return profile connections for a tool type."""
        return get_tool_connections_by_type(
            self._connections,
            profile_id=profile_id,
            tool_type=tool_type,
        )

    def get_connections_by_role(
        self, profile_id: str, role_id: str
    ) -> List[ToolConnectionModel]:
        """Return profile connections associated with a role."""
        return get_tool_connections_by_role(
            get_connections_by_profile_fn=self.get_connections_by_profile,
            profile_id=profile_id,
            role_id=role_id,
        )

    def update_connection(self, connection: ToolConnectionModel) -> ToolConnectionModel:
        """Update a tool connection."""
        return update_tool_connection(
            self._connections,
            connection=connection,
            save_registry=self._save_registry,
            utc_now=_utc_now,
        )

    def record_connection_usage(self, connection_id: str, profile_id: str):
        """Record connection usage."""
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
        """Update connection validation status."""
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
        """Export profile connections as templates without secrets."""
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
        """Return tools available for an agent role."""
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
        """Infer the side-effect level for a discovered tool."""
        return infer_side_effect_level(provider_name, danger_level, tool_id, methods)

    async def discover_wordpress_capabilities(
        self,
        connection_id: str,
        wp_url: str,
        wp_username: str,
        wp_password: str,
    ) -> Dict[str, Any]:
        """Discover WordPress capabilities through the legacy compatibility wrapper."""
        return await discover_wordpress_capabilities_for_service(
            self,
            connection_id=connection_id,
            wp_url=wp_url,
            wp_username=wp_username,
            wp_password=wp_password,
            logger=logger,
        )
