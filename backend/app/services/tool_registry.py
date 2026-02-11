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
from backend.app.services.tools.discovery_provider import (
    ToolDiscoveryProvider,
    ToolConfig,
    DiscoveredTool,
    GenericHTTPToolProvider,
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

        # In-memory cache
        # Tools: keyed by tool_id
        self._tools: Dict[str, RegisteredTool] = {}
        # Connections: keyed by (profile_id, connection_id) tuple for multi-tenant support
        self._connections: Dict[tuple, ToolConnectionModel] = {}

        # Discovery providers registry
        self._discovery_providers: Dict[str, ToolDiscoveryProvider] = {}

        # Initialize database
        self._ensure_tables()

        # Load data (from SQLite, fallback to JSON for migration)
        self._load_registry()

        # Register default providers (built-in)
        self._register_default_providers()

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
            raise RuntimeError(
                "Missing PostgreSQL tables: "
                f"{missing_str}. Run: alembic -c backend/alembic.ini upgrade head"
            )

    def _load_registry(self):
        """Load tool registry from PostgreSQL database"""

        def _coerce_datetime(value: Optional[Any]) -> Optional[datetime]:
            if value is None:
                return None
            if isinstance(value, datetime):
                return value
            return self.from_isoformat(value)

        try:
            with self.factory.get_connection(role=self.db_role) as conn:
                rows = conn.execute(text("SELECT * FROM tool_registry")).fetchall()
                for row in rows:
                    try:
                        tool_data = {
                            "tool_id": row.tool_id,
                            "site_id": row.site_id,
                            "provider": row.provider,
                            "display_name": row.display_name,
                            "origin_capability_id": row.origin_capability_id,
                            "category": row.category,
                            "description": row.description,
                            "endpoint": row.endpoint,
                            "methods": self.deserialize_json(row.methods, []),
                            "danger_level": row.danger_level,
                            "input_schema": self.deserialize_json(row.input_schema, {}),
                            "enabled": (
                                bool(row.enabled) if row.enabled is not None else True
                            ),
                            "read_only": (
                                bool(row.read_only)
                                if row.read_only is not None
                                else False
                            ),
                            "allowed_agent_roles": self.deserialize_json(
                                row.allowed_agent_roles, []
                            ),
                            "side_effect_level": row.side_effect_level,
                            "capability_code": row.capability_code or "",
                            "risk_class": row.risk_class or "readonly",
                            "created_at": _coerce_datetime(row.created_at)
                            or _utc_now(),
                            "updated_at": _coerce_datetime(row.updated_at)
                            or _utc_now(),
                            "scope": row.scope or "profile",
                            "tenant_id": row.tenant_id,
                            "owner_profile_id": row.owner_profile_id,
                        }
                        self._tools[row.tool_id] = RegisteredTool(**tool_data)
                    except Exception as e:
                        logger.warning(f"Error loading tool {row.tool_id}: {e}")

            with self.factory.get_connection(role=self.db_role) as conn:
                rows = conn.execute(text("SELECT * FROM tool_connections")).fetchall()
                for row in rows:
                    try:
                        conn_data = {
                            "id": row.id,
                            "profile_id": row.profile_id,
                            "tool_type": row.tool_type,
                            "connection_type": row.connection_type,
                            "name": row.name,
                            "description": row.description,
                            "icon": row.icon,
                            "api_key": row.api_key,
                            "api_secret": row.api_secret,
                            "oauth_token": row.oauth_token,
                            "oauth_refresh_token": row.oauth_refresh_token,
                            "base_url": row.base_url,
                            "wp_url": getattr(row, "wp_url", None),
                            "wp_username": getattr(row, "wp_username", None),
                            "wp_application_password": getattr(
                                row, "wp_application_password", None
                            ),
                            "remote_cluster_url": row.remote_cluster_url,
                            "remote_connection_id": row.remote_connection_id,
                            "config": self.deserialize_json(row.config, {}),
                            "associated_roles": self.deserialize_json(
                                row.associated_roles, []
                            ),
                            "enabled": (
                                bool(row.enabled) if row.enabled is not None else True
                            ),
                            "is_active": (
                                bool(row.is_active)
                                if row.is_active is not None
                                else True
                            ),
                            "is_validated": (
                                bool(row.is_validated)
                                if row.is_validated is not None
                                else False
                            ),
                            "last_validated_at": _coerce_datetime(
                                row.last_validated_at
                            ),
                            "validation_error": row.validation_error,
                            "usage_count": row.usage_count or 0,
                            "last_used_at": _coerce_datetime(row.last_used_at),
                            "last_discovery": _coerce_datetime(
                                getattr(row, "last_discovery", None)
                            ),
                            "discovery_method": getattr(row, "discovery_method", None),
                            "x_platform": self.deserialize_json(
                                getattr(row, "x_platform", None), None
                            ),
                            "created_at": _coerce_datetime(row.created_at)
                            or _utc_now(),
                            "updated_at": _coerce_datetime(row.updated_at)
                            or _utc_now(),
                        }
                        connection = ToolConnectionModel(**conn_data)
                        self._connections[(row.profile_id, row.id)] = connection
                    except Exception as e:
                        logger.warning(f"Error loading connection {row.id}: {e}")

            logger.info(
                f"Loaded {len(self._tools)} tools and {len(self._connections)} connections from database"
            )

        except Exception as e:
            logger.error(f"Error loading registry from database: {e}")
            self._load_registry_from_json()

    def _load_registry_from_json(self):
        """Load tool registry from JSON files (migration fallback)"""
        if self.registry_file.exists():
            try:
                with open(self.registry_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._tools = {
                        tool_id: RegisteredTool(**tool_data)
                        for tool_id, tool_data in data.items()
                    }
            except Exception as e:
                logger.error(f"Error loading tool registry from JSON: {e}")
                self._tools = {}

        if self.connections_file.exists():
            try:
                with open(self.connections_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._connections = {}
                    for key, conn_data in data.items():
                        try:
                            conn = ToolConnectionModel(**conn_data)
                            profile_id = (
                                conn.profile_id
                                if hasattr(conn, "profile_id") and conn.profile_id
                                else "default-user"
                            )
                            self._connections[(profile_id, conn.id)] = conn

                            # Remote tools are now registered via system capability packs in cloud repo

                        except Exception as e:
                            logger.warning(f"Error loading connection {key}: {e}")
            except Exception as e:
                logger.error(f"Error loading connections from JSON: {e}")
                self._connections = {}

    def _save_registry(self):
        """Save tool registry to PostgreSQL database"""
        try:
            with self.transaction() as conn:
                for tool_id, tool in self._tools.items():
                    conn.execute(
                        text(
                            """
                            INSERT INTO tool_registry (
                                tool_id, site_id, provider, display_name, origin_capability_id,
                                category, description, endpoint, methods, danger_level,
                                input_schema, enabled, read_only, allowed_agent_roles,
                                side_effect_level, scope, tenant_id, owner_profile_id,
                                capability_code, risk_class, created_at, updated_at
                            ) VALUES (
                                :tool_id, :site_id, :provider, :display_name, :origin_capability_id,
                                :category, :description, :endpoint, :methods, :danger_level,
                                :input_schema, :enabled, :read_only, :allowed_agent_roles,
                                :side_effect_level, :scope, :tenant_id, :owner_profile_id,
                                :capability_code, :risk_class, :created_at, :updated_at
                            )
                            ON CONFLICT (tool_id) DO UPDATE SET
                                site_id = EXCLUDED.site_id,
                                provider = EXCLUDED.provider,
                                display_name = EXCLUDED.display_name,
                                origin_capability_id = EXCLUDED.origin_capability_id,
                                category = EXCLUDED.category,
                                description = EXCLUDED.description,
                                endpoint = EXCLUDED.endpoint,
                                methods = EXCLUDED.methods,
                                danger_level = EXCLUDED.danger_level,
                                input_schema = EXCLUDED.input_schema,
                                enabled = EXCLUDED.enabled,
                                read_only = EXCLUDED.read_only,
                                allowed_agent_roles = EXCLUDED.allowed_agent_roles,
                                side_effect_level = EXCLUDED.side_effect_level,
                                scope = EXCLUDED.scope,
                                tenant_id = EXCLUDED.tenant_id,
                                owner_profile_id = EXCLUDED.owner_profile_id,
                                capability_code = EXCLUDED.capability_code,
                                risk_class = EXCLUDED.risk_class,
                                created_at = EXCLUDED.created_at,
                                updated_at = EXCLUDED.updated_at
                        """
                        ),
                        {
                            "tool_id": tool.tool_id,
                            "site_id": tool.site_id,
                            "provider": tool.provider,
                            "display_name": tool.display_name,
                            "origin_capability_id": tool.origin_capability_id,
                            "category": tool.category,
                            "description": tool.description,
                            "endpoint": tool.endpoint,
                            "methods": self.serialize_json(tool.methods),
                            "danger_level": tool.danger_level,
                            "input_schema": self.serialize_json(
                                tool.input_schema.dict()
                            ),
                            "enabled": tool.enabled,
                            "read_only": tool.read_only,
                            "allowed_agent_roles": self.serialize_json(
                                tool.allowed_agent_roles
                            ),
                            "side_effect_level": tool.side_effect_level,
                            "scope": tool.scope or "profile",
                            "tenant_id": tool.tenant_id,
                            "owner_profile_id": tool.owner_profile_id,
                            "capability_code": tool.capability_code,
                            "risk_class": tool.risk_class,
                            "created_at": tool.created_at,
                            "updated_at": tool.updated_at,
                        },
                    )

                for (profile_id, conn_id), connection in self._connections.items():
                    conn.execute(
                        text(
                            """
                            INSERT INTO tool_connections (
                                id, profile_id, tool_type, connection_type, name, description, icon,
                                api_key, api_secret, oauth_token, oauth_refresh_token, base_url,
                                wp_url, wp_username, wp_application_password,
                                remote_cluster_url, remote_connection_id, config, associated_roles,
                                enabled, is_active, is_validated, last_validated_at, validation_error,
                                usage_count, last_used_at, last_discovery, discovery_method,
                                x_platform, created_at, updated_at
                            ) VALUES (
                                :id, :profile_id, :tool_type, :connection_type, :name, :description, :icon,
                                :api_key, :api_secret, :oauth_token, :oauth_refresh_token, :base_url,
                                :wp_url, :wp_username, :wp_application_password,
                                :remote_cluster_url, :remote_connection_id, :config, :associated_roles,
                                :enabled, :is_active, :is_validated, :last_validated_at, :validation_error,
                                :usage_count, :last_used_at, :last_discovery, :discovery_method,
                                :x_platform, :created_at, :updated_at
                            )
                            ON CONFLICT (profile_id, id) DO UPDATE SET
                                tool_type = EXCLUDED.tool_type,
                                connection_type = EXCLUDED.connection_type,
                                name = EXCLUDED.name,
                                description = EXCLUDED.description,
                                icon = EXCLUDED.icon,
                                api_key = EXCLUDED.api_key,
                                api_secret = EXCLUDED.api_secret,
                                oauth_token = EXCLUDED.oauth_token,
                                oauth_refresh_token = EXCLUDED.oauth_refresh_token,
                                base_url = EXCLUDED.base_url,
                                wp_url = EXCLUDED.wp_url,
                                wp_username = EXCLUDED.wp_username,
                                wp_application_password = EXCLUDED.wp_application_password,
                                remote_cluster_url = EXCLUDED.remote_cluster_url,
                                remote_connection_id = EXCLUDED.remote_connection_id,
                                config = EXCLUDED.config,
                                associated_roles = EXCLUDED.associated_roles,
                                enabled = EXCLUDED.enabled,
                                is_active = EXCLUDED.is_active,
                                is_validated = EXCLUDED.is_validated,
                                last_validated_at = EXCLUDED.last_validated_at,
                                validation_error = EXCLUDED.validation_error,
                                usage_count = EXCLUDED.usage_count,
                                last_used_at = EXCLUDED.last_used_at,
                                last_discovery = EXCLUDED.last_discovery,
                                discovery_method = EXCLUDED.discovery_method,
                                x_platform = EXCLUDED.x_platform,
                                created_at = EXCLUDED.created_at,
                                updated_at = EXCLUDED.updated_at
                        """
                        ),
                        {
                            "id": connection.id,
                            "profile_id": connection.profile_id,
                            "tool_type": connection.tool_type,
                            "connection_type": connection.connection_type,
                            "name": connection.name,
                            "description": connection.description,
                            "icon": connection.icon,
                            "api_key": connection.api_key,
                            "api_secret": connection.api_secret,
                            "oauth_token": connection.oauth_token,
                            "oauth_refresh_token": connection.oauth_refresh_token,
                            "base_url": connection.base_url,
                            "wp_url": connection.wp_url,
                            "wp_username": connection.wp_username,
                            "wp_application_password": connection.wp_application_password,
                            "remote_cluster_url": connection.remote_cluster_url,
                            "remote_connection_id": connection.remote_connection_id,
                            "config": self.serialize_json(connection.config),
                            "associated_roles": self.serialize_json(
                                connection.associated_roles
                            ),
                            "enabled": connection.enabled,
                            "is_active": connection.is_active,
                            "is_validated": connection.is_validated,
                            "last_validated_at": connection.last_validated_at,
                            "validation_error": connection.validation_error,
                            "usage_count": connection.usage_count,
                            "last_used_at": connection.last_used_at,
                            "last_discovery": connection.last_discovery,
                            "discovery_method": connection.discovery_method,
                            "x_platform": self.serialize_json(connection.x_platform),
                            "created_at": connection.created_at,
                            "updated_at": connection.updated_at,
                        },
                    )

        except Exception as e:
            logger.error(f"Error saving registry to database: {e}")
            self._save_registry_to_json()

    def _save_registry_to_json(self):
        """Save tool registry to JSON files (migration fallback)"""
        try:
            with open(self.registry_file, "w", encoding="utf-8") as f:
                json.dump(
                    {tool_id: tool.dict() for tool_id, tool in self._tools.items()},
                    f,
                    indent=2,
                    ensure_ascii=False,
                    default=str,
                )
        except Exception as e:
            logger.error(f"Error saving tool registry to JSON: {e}")

        try:
            with open(self.connections_file, "w", encoding="utf-8") as f:
                connections_dict = {
                    f"{profile_id}:{conn_id}": conn.dict()
                    for (profile_id, conn_id), conn in self._connections.items()
                }
                json.dump(
                    connections_dict, f, indent=2, ensure_ascii=False, default=str
                )
        except Exception as e:
            logger.error(f"Error saving connections to JSON: {e}")

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
        logger.info(f"Registered discovery provider: {provider_name}")

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

            # Determine capability_code and risk_class for Runtime Profile support
            # capability_code defaults to origin_capability_id (e.g., "wp" for WordPress tools)
            capability_code = (
                discovered_tool.tool_id.split(".")[0]
                if "." in discovered_tool.tool_id
                else discovered_tool.tool_id
            )

            # risk_class maps from side_effect_level
            risk_class_mapping = {
                "readonly": "readonly",
                "soft_write": "soft_write",
                "external_write": "external_write",
            }
            risk_class = risk_class_mapping.get(side_effect_level, "readonly")

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
                scope=tool_scope,
                tenant_id=tool_tenant_id,
                owner_profile_id=tool_owner_profile_id,
                capability_code=capability_code,  # Runtime Profile support
                risk_class=risk_class,  # Runtime Profile support
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
        key = (profile_id, connection_id)
        if key in self._connections:
            conn = self._connections[key]
            # Update config with new configuration
            if config.custom_config:
                conn.config.update(config.custom_config)
            conn.last_discovery = _utc_now()
            conn.updated_at = _utc_now()
            self._save_registry()
        else:
            conn = ToolConnectionModel(
                id=connection_id,
                profile_id=profile_id,
                name=f"{provider_name} - {connection_id}",
                tool_type=config.tool_type,
                connection_type=config.connection_type,
                base_url=config.base_url,
                api_key=config.api_key,
                api_secret=config.api_secret,
                # Legacy WordPress fields for backward compatibility
                wp_url=config.base_url if config.tool_type == "wordpress" else None,
                wp_username=config.api_key if config.tool_type == "wordpress" else None,
                wp_application_password=(
                    config.api_secret if config.tool_type == "wordpress" else None
                ),
                config=config.custom_config.copy() if config.custom_config else {},
                last_discovery=_utc_now(),
                discovery_method=provider_name,
            )
            self._connections[key] = conn

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
        tools = list(self._tools.values())

        if site_id:
            tools = [t for t in tools if t.site_id == site_id]

        if category:
            tools = [t for t in tools if t.category == category]

        if enabled_only:
            tools = [t for t in tools if t.enabled]

        # Scope filtering
        if scope:
            tools = [t for t in tools if t.scope == scope]

        if tenant_id:
            tools = [t for t in tools if t.tenant_id == tenant_id]

        if profile_id:
            # Include tools that are accessible to this profile:
            # - system scope (no owner)
            # - tenant scope (same tenant)
            # - profile scope (same profile)
            tools = [
                t
                for t in tools
                if (
                    t.scope == "system"
                    or (t.scope == "tenant" and t.tenant_id == tenant_id)
                    or (t.scope == "profile" and t.owner_profile_id == profile_id)
                )
            ]

        # Apply workspace overlay if workspace_id is provided
        if workspace_id:
            from backend.app.services.tool_overlay_service import ToolOverlayService

            overlay_service = ToolOverlayService()
            tools = overlay_service.apply_tools_overlay(tools, workspace_id)

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
        if profile_id:
            return [
                conn
                for (pid, _), conn in self._connections.items()
                if pid == profile_id
            ]
        return list(self._connections.values())

    def get_connection(
        self, connection_id: str, profile_id: Optional[str] = None
    ) -> Optional[ToolConnectionModel]:
        """
        Get a specific connection

        Args:
            connection_id: Connection ID
            profile_id: Optional profile ID. If None, searches across all profiles (backward compatibility).

        Returns:
            Tool connection if found, None otherwise
        """
        if profile_id:
            return self._connections.get((profile_id, connection_id))

        # Backward compatibility: search across all profiles
        for (pid, cid), conn in self._connections.items():
            if cid == connection_id:
                return conn
        return None

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
        connection.updated_at = _utc_now()
        if not connection.created_at:
            connection.created_at = _utc_now()

        # Store with (profile_id, connection_id) as key
        self._connections[(connection.profile_id, connection.id)] = connection
        self._save_registry()
        return connection

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
        conn = ToolConnectionModel(
            id=connection_id,
            profile_id=profile_id,
            name=name,
            tool_type="wordpress",
            connection_type="local",
            wp_url=wp_url,
            wp_username=wp_username,
            wp_application_password=wp_application_password,
            base_url=wp_url,
            api_key=wp_username,
            api_secret=wp_application_password,
        )
        return self.create_connection(conn)

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
        deleted = False

        if profile_id:
            key = (profile_id, connection_id)
            if key in self._connections:
                # Remove all tools for this connection
                tool_ids_to_remove = [
                    tool_id
                    for tool_id, tool in self._tools.items()
                    if tool.site_id == connection_id
                ]
                for tool_id in tool_ids_to_remove:
                    del self._tools[tool_id]
                    unregister_dynamic_tool(tool_id)

                del self._connections[key]
                deleted = True
        else:
            # Backward compatibility: search and delete across all profiles
            keys_to_delete = [
                key
                for key, conn in self._connections.items()
                if conn.id == connection_id
            ]
            for key in keys_to_delete:
                # Remove all tools for this connection
                tool_ids_to_remove = [
                    tool_id
                    for tool_id, tool in self._tools.items()
                    if tool.site_id == connection_id
                ]
                for tool_id in tool_ids_to_remove:
                    del self._tools[tool_id]
                    unregister_dynamic_tool(tool_id)

                del self._connections[key]
                deleted = True

        if deleted:
            self._save_registry()

        return deleted

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
        connections = [
            conn for (pid, _), conn in self._connections.items() if pid == profile_id
        ]

        if active_only:
            connections = [conn for conn in connections if conn.is_active]

        # Sort by usage_count descending, then name ascending
        connections.sort(key=lambda c: (-c.usage_count, c.name))
        return connections

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
        connections = [
            conn
            for (pid, _), conn in self._connections.items()
            if pid == profile_id and conn.tool_type == tool_type and conn.is_active
        ]

        # Sort by usage_count descending, then name ascending
        connections.sort(key=lambda c: (-c.usage_count, c.name))
        return connections

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
        connections = self.get_connections_by_profile(profile_id, active_only=True)
        return [conn for conn in connections if role_id in conn.associated_roles]

    def update_connection(self, connection: ToolConnectionModel) -> ToolConnectionModel:
        """
        Update a tool connection

        Args:
            connection: Updated connection model

        Returns:
            Updated connection
        """
        connection.updated_at = _utc_now()
        self._connections[(connection.profile_id, connection.id)] = connection
        self._save_registry()
        return connection

    def record_connection_usage(self, connection_id: str, profile_id: str):
        """
        Record that a connection was used

        Args:
            connection_id: Connection ID
            profile_id: Profile ID
        """
        key = (profile_id, connection_id)
        if key in self._connections:
            conn = self._connections[key]
            conn.usage_count += 1
            conn.last_used_at = _utc_now()
            conn.updated_at = _utc_now()
            self._save_registry()

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
        key = (profile_id, connection_id)
        if key in self._connections:
            conn = self._connections[key]
            conn.is_validated = is_valid
            conn.last_validated_at = _utc_now()
            conn.validation_error = error_message
            conn.updated_at = _utc_now()
            self._save_registry()

    def export_as_templates(self, profile_id: str) -> List[Dict[str, Any]]:
        """
        Export connections as templates (without sensitive data)

        Args:
            profile_id: Profile ID

        Returns:
            List of connection templates
        """
        from backend.app.models.tool_connection import ToolConnectionTemplate

        connections = self.get_connections_by_profile(profile_id, active_only=True)

        templates = []
        for conn in connections:
            # Generate config schema without actual values
            config_schema = {"connection_type": conn.connection_type, "fields": {}}

            if conn.connection_type == "local":
                if conn.api_key:
                    config_schema["fields"]["api_key"] = {
                        "type": "string",
                        "required": True,
                        "sensitive": True,
                    }
                if conn.api_secret:
                    config_schema["fields"]["api_secret"] = {
                        "type": "string",
                        "required": True,
                        "sensitive": True,
                    }
                if conn.oauth_token:
                    config_schema["fields"]["oauth_token"] = {
                        "type": "string",
                        "required": True,
                        "sensitive": True,
                    }
                if conn.base_url:
                    config_schema["fields"]["base_url"] = {
                        "type": "string",
                        "required": True,
                        "example": conn.base_url,
                    }

            # Extract required permissions from config
            required_permissions = conn.config.get("required_permissions", [])

            template = ToolConnectionTemplate(
                tool_type=conn.tool_type,
                name=conn.name,
                description=conn.description,
                icon=conn.icon,
                config_schema=config_schema,
                required_permissions=required_permissions,
                associated_roles=conn.associated_roles,
            )
            templates.append(template.dict())

        return templates

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
        # Get tools with scope filtering
        tools = self.get_tools(
            enabled_only=True,
            profile_id=profile_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
        )

        # Filter by agent role
        filtered_tools = []
        for tool in tools:
            # If tool has allowed_agent_roles, check if role is allowed
            if tool.allowed_agent_roles:
                if agent_role not in tool.allowed_agent_roles:
                    continue

            filtered_tools.append(tool)

        return filtered_tools

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
        # Rule 1: GET-only methods = readonly
        read_only_methods = ["GET"]
        if methods and all(m.upper() in read_only_methods for m in methods):
            return "readonly"

        # Rule 2: Provider-based rules
        provider_lower = provider_name.lower()

        # External providers (WordPress, Notion, Google Drive)
        if provider_lower in ["wordpress", "notion", "google_drive"]:
            # Read operations (list, read, search) = readonly
            if any(
                keyword in tool_id.lower()
                for keyword in ["read", "list", "search", "get"]
            ):
                return "readonly"
            # Write operations = external_write
            return "external_write"

        # Local filesystem provider
        if provider_lower == "local_filesystem":
            # Read operations = readonly
            if any(
                keyword in tool_id.lower() for keyword in ["read", "list", "search"]
            ):
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
