"""
Tool Registry Service.

Generic tool registration service supporting multiple tool types discovery and management.

Design Principles:
- Platform neutral: not bound to any specific tool type
- Plugin-based: extend via ToolDiscoveryProvider
- Open-closed: extend functionality without modifying Core code
- SQLite storage for consistency with other services
"""
import json
import os
import sqlite3
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

    def __init__(self, data_dir: str = "./data", db_path: Optional[str] = None):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # SQLite database path
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
        """Create database tables if they don't exist"""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Tool registry table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tool_registry (
                tool_id TEXT PRIMARY KEY,
                site_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                display_name TEXT NOT NULL,
                origin_capability_id TEXT NOT NULL,
                category TEXT NOT NULL,
                description TEXT NOT NULL,
                endpoint TEXT NOT NULL,
                methods TEXT NOT NULL,
                danger_level TEXT DEFAULT 'low',
                input_schema TEXT DEFAULT '{}',
                enabled INTEGER DEFAULT 1,
                read_only INTEGER DEFAULT 0,
                allowed_agent_roles TEXT DEFAULT '[]',
                side_effect_level TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        # Tool connections table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tool_connections (
                id TEXT NOT NULL,
                profile_id TEXT NOT NULL,
                tool_type TEXT NOT NULL,
                connection_type TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                icon TEXT,
                api_key TEXT,
                api_secret TEXT,
                oauth_token TEXT,
                oauth_refresh_token TEXT,
                base_url TEXT,
                wp_url TEXT,
                wp_username TEXT,
                wp_application_password TEXT,
                remote_cluster_url TEXT,
                remote_connection_id TEXT,
                config TEXT DEFAULT '{}',
                associated_roles TEXT DEFAULT '[]',
                enabled INTEGER DEFAULT 1,
                is_active INTEGER DEFAULT 1,
                is_validated INTEGER DEFAULT 0,
                last_validated_at TEXT,
                validation_error TEXT,
                usage_count INTEGER DEFAULT 0,
                last_used_at TEXT,
                last_discovery TEXT,
                discovery_method TEXT,
                x_platform TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (profile_id, id)
            )
        """)

        # Indexes
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_tool_connections_profile
            ON tool_connections(profile_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_tool_connections_type
            ON tool_connections(tool_type)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_tool_connections_active
            ON tool_connections(is_active)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_tool_registry_site
            ON tool_registry(site_id)
        """)

        conn.commit()
        conn.close()

    def _load_registry(self):
        """Load tool registry from SQLite database"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Load tools
            cursor.execute("SELECT * FROM tool_registry")
            rows = cursor.fetchall()
            for row in rows:
                try:
                    tool_data = {
                        "tool_id": row["tool_id"],
                        "site_id": row["site_id"],
                        "provider": row["provider"],
                        "display_name": row["display_name"],
                        "origin_capability_id": row["origin_capability_id"],
                        "category": row["category"],
                        "description": row["description"],
                        "endpoint": row["endpoint"],
                        "methods": json.loads(row["methods"]) if row["methods"] else [],
                        "danger_level": row["danger_level"],
                        "input_schema": json.loads(row["input_schema"]) if row["input_schema"] else {},
                        "enabled": bool(row["enabled"]),
                        "read_only": bool(row["read_only"]),
                        "allowed_agent_roles": json.loads(row["allowed_agent_roles"]) if row["allowed_agent_roles"] else [],
                        "side_effect_level": row["side_effect_level"],
                        "created_at": datetime.fromisoformat(row["created_at"]) if row["created_at"] else datetime.utcnow(),
                        "updated_at": datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else datetime.utcnow(),
                    }
                    self._tools[row["tool_id"]] = RegisteredTool(**tool_data)
                except Exception as e:
                    logger.warning(f"Error loading tool {row['tool_id']}: {e}")

            # Load connections
            cursor.execute("SELECT * FROM tool_connections")
            rows = cursor.fetchall()
            for row in rows:
                try:
                    conn_data = {
                        "id": row["id"],
                        "profile_id": row["profile_id"],
                        "tool_type": row["tool_type"],
                        "connection_type": row["connection_type"],
                        "name": row["name"],
                        "description": row["description"],
                        "icon": row["icon"],
                        "api_key": row["api_key"],
                        "api_secret": row["api_secret"],
                        "oauth_token": row["oauth_token"],
                        "oauth_refresh_token": row["oauth_refresh_token"],
                        "base_url": row["base_url"],
                        "wp_url": row["wp_url"],
                        "wp_username": row["wp_username"],
                        "wp_application_password": row["wp_application_password"],
                        "remote_cluster_url": row["remote_cluster_url"],
                        "remote_connection_id": row["remote_connection_id"],
                        "config": json.loads(row["config"]) if row["config"] else {},
                        "associated_roles": json.loads(row["associated_roles"]) if row["associated_roles"] else [],
                        "enabled": bool(row["enabled"]),
                        "is_active": bool(row["is_active"]),
                        "is_validated": bool(row["is_validated"]),
                        "last_validated_at": datetime.fromisoformat(row["last_validated_at"]) if row["last_validated_at"] else None,
                        "validation_error": row["validation_error"],
                        "usage_count": row["usage_count"],
                        "last_used_at": datetime.fromisoformat(row["last_used_at"]) if row["last_used_at"] else None,
                        "last_discovery": datetime.fromisoformat(row["last_discovery"]) if row["last_discovery"] else None,
                        "discovery_method": row["discovery_method"],
                        "x_platform": json.loads(row["x_platform"]) if row["x_platform"] else None,
                        "created_at": datetime.fromisoformat(row["created_at"]) if row["created_at"] else datetime.utcnow(),
                        "updated_at": datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else datetime.utcnow(),
                    }
                    connection = ToolConnectionModel(**conn_data)
                    self._connections[(row["profile_id"], row["id"])] = connection
                except Exception as e:
                    logger.warning(f"Error loading connection {row['id']}: {e}")

            conn.close()
            logger.info(f"Loaded {len(self._tools)} tools and {len(self._connections)} connections from database")

        except sqlite3.OperationalError as e:
            # Table doesn't exist yet, try loading from JSON for migration
            logger.info("Database tables not found, attempting to load from JSON files for migration")
            self._load_registry_from_json()
        except Exception as e:
            logger.error(f"Error loading registry from database: {e}")
            # Fallback to JSON
            self._load_registry_from_json()

    def _load_registry_from_json(self):
        """Load tool registry from JSON files (migration fallback)"""
        if self.registry_file.exists():
            try:
                with open(self.registry_file, 'r', encoding='utf-8') as f:
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
                with open(self.connections_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._connections = {}
                    for key, conn_data in data.items():
                        try:
                            conn = ToolConnectionModel(**conn_data)
                            profile_id = conn.profile_id if hasattr(conn, 'profile_id') and conn.profile_id else 'default-user'
                            self._connections[(profile_id, conn.id)] = conn
                        except Exception as e:
                            logger.warning(f"Error loading connection {key}: {e}")
            except Exception as e:
                logger.error(f"Error loading connections from JSON: {e}")
                self._connections = {}

    def _save_registry(self):
        """Save tool registry to SQLite database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Save tools
            for tool_id, tool in self._tools.items():
                cursor.execute("""
                    INSERT OR REPLACE INTO tool_registry (
                        tool_id, site_id, provider, display_name, origin_capability_id,
                        category, description, endpoint, methods, danger_level,
                        input_schema, enabled, read_only, allowed_agent_roles,
                        side_effect_level, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    tool.tool_id,
                    tool.site_id,
                    tool.provider,
                    tool.display_name,
                    tool.origin_capability_id,
                    tool.category,
                    tool.description,
                    tool.endpoint,
                    json.dumps(tool.methods),
                    tool.danger_level,
                    json.dumps(tool.input_schema.dict()),
                    1 if tool.enabled else 0,
                    1 if tool.read_only else 0,
                    json.dumps(tool.allowed_agent_roles),
                    tool.side_effect_level,
                    tool.created_at.isoformat(),
                    tool.updated_at.isoformat(),
                ))

            # Save connections
            for (profile_id, conn_id), connection in self._connections.items():
                cursor.execute("""
                    INSERT OR REPLACE INTO tool_connections (
                        id, profile_id, tool_type, connection_type, name, description, icon,
                        api_key, api_secret, oauth_token, oauth_refresh_token, base_url,
                        wp_url, wp_username, wp_application_password,
                        remote_cluster_url, remote_connection_id, config, associated_roles,
                        enabled, is_active, is_validated, last_validated_at, validation_error,
                        usage_count, last_used_at, last_discovery, discovery_method,
                        x_platform, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    connection.id,
                    connection.profile_id,
                    connection.tool_type,
                    connection.connection_type,
                    connection.name,
                    connection.description,
                    connection.icon,
                    connection.api_key,
                    connection.api_secret,
                    connection.oauth_token,
                    connection.oauth_refresh_token,
                    connection.base_url,
                    connection.wp_url,
                    connection.wp_username,
                    connection.wp_application_password,
                    connection.remote_cluster_url,
                    connection.remote_connection_id,
                    json.dumps(connection.config),
                    json.dumps(connection.associated_roles),
                    1 if connection.enabled else 0,
                    1 if connection.is_active else 0,
                    1 if connection.is_validated else 0,
                    connection.last_validated_at.isoformat() if connection.last_validated_at else None,
                    connection.validation_error,
                    connection.usage_count,
                    connection.last_used_at.isoformat() if connection.last_used_at else None,
                    connection.last_discovery.isoformat() if connection.last_discovery else None,
                    connection.discovery_method,
                    json.dumps(connection.x_platform) if connection.x_platform else None,
                    connection.created_at.isoformat(),
                    connection.updated_at.isoformat(),
                ))

            conn.commit()
            conn.close()

        except Exception as e:
            logger.error(f"Error saving registry to database: {e}")
            # Fallback to JSON for migration
            self._save_registry_to_json()

    def _save_registry_to_json(self):
        """Save tool registry to JSON files (migration fallback)"""
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
            logger.error(f"Error saving tool registry to JSON: {e}")

        try:
            with open(self.connections_file, 'w', encoding='utf-8') as f:
                connections_dict = {
                    f"{profile_id}:{conn_id}": conn.dict()
                    for (profile_id, conn_id), conn in self._connections.items()
                }
                json.dump(
                    connections_dict,
                    f,
                    indent=2,
                    ensure_ascii=False,
                    default=str
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
        connection_id: Optional[str] = None,
        profile_id: str = "default-user"
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
        key = (profile_id, connection_id)
        if key in self._connections:
            conn = self._connections[key]
            conn.last_discovery = datetime.utcnow()
            conn.updated_at = datetime.utcnow()
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
                wp_application_password=config.api_secret if config.tool_type == "wordpress" else None,
                last_discovery=datetime.utcnow(),
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

    def get_connections(self, profile_id: Optional[str] = None) -> List[ToolConnectionModel]:
        """
        Get all tool connections

        Args:
            profile_id: Optional profile ID to filter connections. If None, returns all connections.

        Returns:
            List of tool connections
        """
        if profile_id:
            return [
                conn for (pid, _), conn in self._connections.items()
                if pid == profile_id
            ]
        return list(self._connections.values())

    def get_connection(self, connection_id: str, profile_id: Optional[str] = None) -> Optional[ToolConnectionModel]:
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
        connection.updated_at = datetime.utcnow()
        if not connection.created_at:
            connection.created_at = datetime.utcnow()

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

    def delete_connection(self, connection_id: str, profile_id: Optional[str] = None) -> bool:
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
                    tool_id for tool_id, tool in self._tools.items()
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
                key for key, conn in self._connections.items()
                if conn.id == connection_id
            ]
            for key in keys_to_delete:
                # Remove all tools for this connection
                tool_ids_to_remove = [
                    tool_id for tool_id, tool in self._tools.items()
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

    def get_connections_by_profile(self, profile_id: str, active_only: bool = True) -> List[ToolConnectionModel]:
        """
        Get all tool connections for a profile

        Args:
            profile_id: Profile ID
            active_only: If True, return only active connections

        Returns:
            List of tool connections
        """
        connections = [
            conn for (pid, _), conn in self._connections.items()
            if pid == profile_id
        ]

        if active_only:
            connections = [conn for conn in connections if conn.is_active]

        # Sort by usage_count descending, then name ascending
        connections.sort(key=lambda c: (-c.usage_count, c.name))
        return connections

    def get_connections_by_tool_type(self, profile_id: str, tool_type: str) -> List[ToolConnectionModel]:
        """
        Get all connections for a specific tool type

        Args:
            profile_id: Profile ID
            tool_type: Tool type (e.g., "wordpress", "notion")

        Returns:
            List of tool connections
        """
        connections = [
            conn for (pid, _), conn in self._connections.items()
            if pid == profile_id and conn.tool_type == tool_type and conn.is_active
        ]

        # Sort by usage_count descending, then name ascending
        connections.sort(key=lambda c: (-c.usage_count, c.name))
        return connections

    def get_connections_by_role(self, profile_id: str, role_id: str) -> List[ToolConnectionModel]:
        """
        Get all connections associated with a specific AI role

        Args:
            profile_id: Profile ID
            role_id: AI role ID

        Returns:
            List of tool connections
        """
        connections = self.get_connections_by_profile(profile_id, active_only=True)
        return [
            conn for conn in connections
            if role_id in conn.associated_roles
        ]

    def update_connection(self, connection: ToolConnectionModel) -> ToolConnectionModel:
        """
        Update a tool connection

        Args:
            connection: Updated connection model

        Returns:
            Updated connection
        """
        connection.updated_at = datetime.utcnow()
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
            conn.last_used_at = datetime.utcnow()
            conn.updated_at = datetime.utcnow()
            self._save_registry()

    def update_validation_status(
        self,
        connection_id: str,
        profile_id: str,
        is_valid: bool,
        error_message: Optional[str] = None
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
            conn.last_validated_at = datetime.utcnow()
            conn.validation_error = error_message
            conn.updated_at = datetime.utcnow()
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
            config_schema = {
                "connection_type": conn.connection_type,
                "fields": {}
            }

            if conn.connection_type == "local":
                if conn.api_key:
                    config_schema["fields"]["api_key"] = {"type": "string", "required": True, "sensitive": True}
                if conn.api_secret:
                    config_schema["fields"]["api_secret"] = {"type": "string", "required": True, "sensitive": True}
                if conn.oauth_token:
                    config_schema["fields"]["oauth_token"] = {"type": "string", "required": True, "sensitive": True}
                if conn.base_url:
                    config_schema["fields"]["base_url"] = {"type": "string", "required": True, "example": conn.base_url}

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

