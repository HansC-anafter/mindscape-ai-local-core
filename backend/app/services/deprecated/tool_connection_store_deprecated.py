"""
Tool Connection Store Service (DEPRECATED - DO NOT USE)

This service has been fully deprecated and replaced by ToolRegistryService.
This file is kept for reference only and should not be imported or used.

Status: REMOVED FROM ACTIVE CODEBASE
- All functionality migrated to ToolRegistryService
- All routes migrated to /api/v1/tools/connections
- This file moved to deprecated/ directory

Migration: Use backend/scripts/migrate_tool_connections.py to migrate data.
"""

import sqlite3
import json
from datetime import datetime
from typing import List, Optional, Dict, Any
from pathlib import Path

from backend.app.models.tool_connection import ToolConnection, ToolConnectionTemplate


class ToolConnectionStore:
    """
    Store for tool connection configurations

    Manages tool connections (local and remote) for users.
    Note: API keys are stored encrypted in production.
    """

    def __init__(self, db_path: str = "data/my_agent_console.db"):
        self.db_path = db_path
        self._ensure_tables()

    def _ensure_tables(self):
        """Create tables if they don't exist"""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Tool connections table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tool_connections (
                id TEXT PRIMARY KEY,
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
                remote_cluster_url TEXT,
                remote_connection_id TEXT,
                config TEXT DEFAULT '{}',
                associated_roles TEXT DEFAULT '[]',
                is_active INTEGER DEFAULT 1,
                is_validated INTEGER DEFAULT 0,
                last_validated_at TEXT,
                validation_error TEXT,
                usage_count INTEGER DEFAULT 0,
                last_used_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                x_platform TEXT,
                FOREIGN KEY (profile_id) REFERENCES mindscape_profiles(id)
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

        conn.commit()
        conn.close()

    def save_connection(self, connection: ToolConnection) -> ToolConnection:
        """Save or update a tool connection"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        connection.updated_at = datetime.utcnow()

        cursor.execute("""
            INSERT OR REPLACE INTO tool_connections (
                id, profile_id, tool_type, connection_type, name, description, icon,
                api_key, api_secret, oauth_token, oauth_refresh_token, base_url,
                remote_cluster_url, remote_connection_id, config, associated_roles,
                is_active, is_validated, last_validated_at, validation_error,
                usage_count, last_used_at, created_at, updated_at, x_platform
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            connection.id,
            connection.profile_id,
            connection.tool_type,
            connection.connection_type,
            connection.name,
            connection.description,
            connection.icon,
            connection.api_key,  # TODO: Encrypt in production
            connection.api_secret,  # TODO: Encrypt in production
            connection.oauth_token,  # TODO: Encrypt in production
            connection.oauth_refresh_token,  # TODO: Encrypt in production
            connection.base_url,
            connection.remote_cluster_url,
            connection.remote_connection_id,
            json.dumps(connection.config),
            json.dumps(connection.associated_roles),
            1 if connection.is_active else 0,
            1 if connection.is_validated else 0,
            connection.last_validated_at.isoformat() if connection.last_validated_at else None,
            connection.validation_error,
            connection.usage_count,
            connection.last_used_at.isoformat() if connection.last_used_at else None,
            connection.created_at.isoformat(),
            connection.updated_at.isoformat(),
            json.dumps(connection.x_platform) if connection.x_platform else None,
        ))

        conn.commit()
        conn.close()

        return connection

    def get_connection(self, connection_id: str, profile_id: str) -> Optional[ToolConnection]:
        """Get a specific tool connection"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM tool_connections
            WHERE id = ? AND profile_id = ?
        """, (connection_id, profile_id))

        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return self._row_to_connection(row)

    def get_connections_by_profile(self, profile_id: str, active_only: bool = True) -> List[ToolConnection]:
        """Get all tool connections for a profile"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        if active_only:
            cursor.execute("""
                SELECT * FROM tool_connections
                WHERE profile_id = ? AND is_active = 1
                ORDER BY usage_count DESC, name ASC
            """, (profile_id,))
        else:
            cursor.execute("""
                SELECT * FROM tool_connections
                WHERE profile_id = ?
                ORDER BY usage_count DESC, name ASC
            """, (profile_id,))

        rows = cursor.fetchall()
        conn.close()

        return [self._row_to_connection(row) for row in rows]

    def get_connections_by_tool_type(self, profile_id: str, tool_type: str) -> List[ToolConnection]:
        """Get all connections for a specific tool type"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM tool_connections
            WHERE profile_id = ? AND tool_type = ? AND is_active = 1
            ORDER BY usage_count DESC, name ASC
        """, (profile_id, tool_type))

        rows = cursor.fetchall()
        conn.close()

        return [self._row_to_connection(row) for row in rows]

    def get_connections_by_role(self, profile_id: str, role_id: str) -> List[ToolConnection]:
        """Get all connections associated with a specific AI role"""
        connections = self.get_connections_by_profile(profile_id, active_only=True)
        return [conn for conn in connections if role_id in conn.associated_roles]

    def record_connection_usage(self, connection_id: str, profile_id: str):
        """Record that a connection was used"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE tool_connections
            SET usage_count = usage_count + 1,
                last_used_at = ?
            WHERE id = ? AND profile_id = ?
        """, (datetime.utcnow().isoformat(), connection_id, profile_id))

        conn.commit()
        conn.close()

    def update_validation_status(
        self,
        connection_id: str,
        profile_id: str,
        is_valid: bool,
        error_message: Optional[str] = None
    ):
        """Update validation status of a connection"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE tool_connections
            SET is_validated = ?,
                last_validated_at = ?,
                validation_error = ?
            WHERE id = ? AND profile_id = ?
        """, (
            1 if is_valid else 0,
            datetime.utcnow().isoformat(),
            error_message,
            connection_id,
            profile_id
        ))

        conn.commit()
        conn.close()

    def delete_connection(self, connection_id: str, profile_id: str) -> bool:
        """Delete a tool connection"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            DELETE FROM tool_connections
            WHERE id = ? AND profile_id = ?
        """, (connection_id, profile_id))

        deleted = cursor.rowcount > 0
        conn.commit()
        conn.close()

        return deleted

    def export_as_templates(self, profile_id: str) -> List[ToolConnectionTemplate]:
        """
        Export connections as templates (without sensitive data)

        Used for template export to console-kit.
        """
        connections = self.get_connections_by_profile(profile_id, active_only=True)

        templates = []
        for conn in connections:
            template = ToolConnectionTemplate(
                tool_type=conn.tool_type,
                name=conn.name,
                description=conn.description,
                icon=conn.icon,
                config_schema=self._generate_config_schema(conn),
                required_permissions=self._extract_required_permissions(conn),
                associated_roles=conn.associated_roles,
            )
            templates.append(template)

        return templates

    def _generate_config_schema(self, conn: ToolConnection) -> Dict[str, Any]:
        """Generate configuration schema for a connection (without actual values)"""
        schema = {
            "connection_type": conn.connection_type,
            "fields": {}
        }

        if conn.connection_type == "local":
            if conn.api_key:
                schema["fields"]["api_key"] = {"type": "string", "required": True, "sensitive": True}
            if conn.api_secret:
                schema["fields"]["api_secret"] = {"type": "string", "required": True, "sensitive": True}
            if conn.oauth_token:
                schema["fields"]["oauth_token"] = {"type": "string", "required": True, "sensitive": True}
            if conn.base_url:
                schema["fields"]["base_url"] = {"type": "string", "required": True, "example": conn.base_url}

        return schema

    def _extract_required_permissions(self, conn: ToolConnection) -> List[str]:
        """Extract required permissions from connection config"""
        # This is tool-specific logic
        # TODO: Implement based on tool type
        return conn.config.get("required_permissions", [])

    def _row_to_connection(self, row: sqlite3.Row) -> ToolConnection:
        """Convert database row to ToolConnection model"""
        return ToolConnection(
            id=row["id"],
            profile_id=row["profile_id"],
            tool_type=row["tool_type"],
            connection_type=row["connection_type"],
            name=row["name"],
            description=row["description"],
            icon=row["icon"],
            api_key=row["api_key"],  # TODO: Decrypt in production
            api_secret=row["api_secret"],  # TODO: Decrypt in production
            oauth_token=row["oauth_token"],  # TODO: Decrypt in production
            oauth_refresh_token=row["oauth_refresh_token"],  # TODO: Decrypt in production
            base_url=row["base_url"],
            remote_cluster_url=row["remote_cluster_url"],
            remote_connection_id=row["remote_connection_id"],
            config=json.loads(row["config"]) if row["config"] else {},
            associated_roles=json.loads(row["associated_roles"]) if row["associated_roles"] else [],
            is_active=bool(row["is_active"]),
            is_validated=bool(row["is_validated"]),
            last_validated_at=datetime.fromisoformat(row["last_validated_at"]) if row["last_validated_at"] else None,
            validation_error=row["validation_error"],
            usage_count=row["usage_count"],
            last_used_at=datetime.fromisoformat(row["last_used_at"]) if row["last_used_at"] else None,
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            x_platform=json.loads(row["x_platform"]) if row["x_platform"] else None,
        )
