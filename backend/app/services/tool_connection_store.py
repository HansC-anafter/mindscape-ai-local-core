"""
Tool Connection Store Service
Manages persistent storage for tool connection configurations

DEPRECATED: This service is deprecated in favor of ToolRegistryService.
Please use ToolRegistryService for new code.

Migration: Use backend/scripts/migrate_tool_connections.py to migrate data.
"""

import logging
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)
from typing import List, Optional, Dict, Any

from sqlalchemy import text

from backend.app.models.tool_connection import ToolConnection, ToolConnectionTemplate
from backend.app.services.stores.postgres_base import PostgresStoreBase

logger = logging.getLogger(__name__)


class ToolConnectionStore(PostgresStoreBase):
    """
    Store for tool connection configurations

    Manages tool connections (local and remote) for users.
    Note: API keys are stored encrypted in production.
    """

    def __init__(self, db_path: Optional[str] = None, db_role: str = "core"):
        super().__init__(db_role=db_role)
        self.db_path = db_path

    def save_connection(self, connection: ToolConnection) -> ToolConnection:
        """Save or update a tool connection"""
        connection.updated_at = _utc_now()

        with self.transaction() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO tool_connections (
                        id, profile_id, tool_type, connection_type, name, description, icon,
                        api_key, api_secret, oauth_token, oauth_refresh_token, base_url,
                        remote_cluster_url, remote_connection_id, config, associated_roles,
                        enabled, is_active, is_validated, last_validated_at, validation_error,
                        usage_count, last_used_at, created_at, updated_at, x_platform,
                        data_source_type, tenant_id, owner_profile_id
                    ) VALUES (
                        :id, :profile_id, :tool_type, :connection_type, :name, :description, :icon,
                        :api_key, :api_secret, :oauth_token, :oauth_refresh_token, :base_url,
                        :remote_cluster_url, :remote_connection_id, :config, :associated_roles,
                        :enabled, :is_active, :is_validated, :last_validated_at, :validation_error,
                        :usage_count, :last_used_at, :created_at, :updated_at, :x_platform,
                        :data_source_type, :tenant_id, :owner_profile_id
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
                        created_at = EXCLUDED.created_at,
                        updated_at = EXCLUDED.updated_at,
                        x_platform = EXCLUDED.x_platform,
                        data_source_type = EXCLUDED.data_source_type,
                        tenant_id = EXCLUDED.tenant_id,
                        owner_profile_id = EXCLUDED.owner_profile_id
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
                    "remote_cluster_url": connection.remote_cluster_url,
                    "remote_connection_id": connection.remote_connection_id,
                    "config": self.serialize_json(connection.config),
                    "associated_roles": self.serialize_json(connection.associated_roles),
                    "enabled": True,
                    "is_active": connection.is_active,
                    "is_validated": connection.is_validated,
                    "last_validated_at": connection.last_validated_at,
                    "validation_error": connection.validation_error,
                    "usage_count": connection.usage_count,
                    "last_used_at": connection.last_used_at,
                    "created_at": connection.created_at,
                    "updated_at": connection.updated_at,
                    "x_platform": self.serialize_json(connection.x_platform),
                    "data_source_type": connection.data_source_type,
                    "tenant_id": connection.tenant_id,
                    "owner_profile_id": connection.owner_profile_id,
                },
            )

        return connection

    def get_connection(
        self, connection_id: str, profile_id: str
    ) -> Optional[ToolConnection]:
        """Get a specific tool connection"""
        with self.get_connection() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT * FROM tool_connections
                    WHERE id = :id AND profile_id = :profile_id
                """
                ),
                {"id": connection_id, "profile_id": profile_id},
            ).fetchone()
            if not row:
                return None
            return self._row_to_connection(row)

    def get_connections_by_profile(
        self, profile_id: str, active_only: bool = True
    ) -> List[ToolConnection]:
        """Get all tool connections for a profile"""
        query = """
            SELECT * FROM tool_connections
            WHERE profile_id = :profile_id
        """
        params: Dict[str, Any] = {"profile_id": profile_id}

        if active_only:
            query += " AND is_active = true"

        query += " ORDER BY usage_count DESC, name ASC"

        with self.get_connection() as conn:
            rows = conn.execute(text(query), params).fetchall()
            return [self._row_to_connection(row) for row in rows]

    def get_connections_by_tool_type(
        self, profile_id: str, tool_type: str
    ) -> List[ToolConnection]:
        """Get all connections for a specific tool type"""
        with self.get_connection() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT * FROM tool_connections
                    WHERE profile_id = :profile_id
                      AND tool_type = :tool_type
                      AND is_active = true
                    ORDER BY usage_count DESC, name ASC
                """
                ),
                {"profile_id": profile_id, "tool_type": tool_type},
            ).fetchall()
            return [self._row_to_connection(row) for row in rows]

    def get_connections_by_role(
        self, profile_id: str, role_id: str
    ) -> List[ToolConnection]:
        """Get all connections associated with a specific AI role"""
        connections = self.get_connections_by_profile(profile_id, active_only=True)
        return [conn for conn in connections if role_id in conn.associated_roles]

    def record_connection_usage(self, connection_id: str, profile_id: str) -> None:
        """Record that a connection was used"""
        with self.transaction() as conn:
            conn.execute(
                text(
                    """
                    UPDATE tool_connections
                    SET usage_count = usage_count + 1,
                        last_used_at = :last_used_at
                    WHERE id = :id AND profile_id = :profile_id
                """
                ),
                {
                    "last_used_at": _utc_now(),
                    "id": connection_id,
                    "profile_id": profile_id,
                },
            )

    def update_validation_status(
        self,
        connection_id: str,
        profile_id: str,
        is_valid: bool,
        error_message: Optional[str] = None,
    ) -> None:
        """Update validation status of a connection"""
        with self.transaction() as conn:
            conn.execute(
                text(
                    """
                    UPDATE tool_connections
                    SET is_validated = :is_validated,
                        last_validated_at = :last_validated_at,
                        validation_error = :validation_error
                    WHERE id = :id AND profile_id = :profile_id
                """
                ),
                {
                    "is_validated": is_valid,
                    "last_validated_at": _utc_now(),
                    "validation_error": error_message,
                    "id": connection_id,
                    "profile_id": profile_id,
                },
            )

    def delete_connection(self, connection_id: str, profile_id: str) -> bool:
        """Delete a tool connection"""
        with self.transaction() as conn:
            result = conn.execute(
                text(
                    """
                    DELETE FROM tool_connections
                    WHERE id = :id AND profile_id = :profile_id
                """
                ),
                {"id": connection_id, "profile_id": profile_id},
            )
            return result.rowcount > 0

    def export_as_templates(self, profile_id: str) -> List[ToolConnectionTemplate]:
        """
        Export connections as templates (without sensitive data)

        Used for template export to external extensions.
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
        schema = {"connection_type": conn.connection_type, "fields": {}}

        if conn.connection_type == "local":
            if conn.api_key:
                schema["fields"]["api_key"] = {
                    "type": "string",
                    "required": True,
                    "sensitive": True,
                }
            if conn.api_secret:
                schema["fields"]["api_secret"] = {
                    "type": "string",
                    "required": True,
                    "sensitive": True,
                }
            if conn.oauth_token:
                schema["fields"]["oauth_token"] = {
                    "type": "string",
                    "required": True,
                    "sensitive": True,
                }
            if conn.base_url:
                schema["fields"]["base_url"] = {
                    "type": "string",
                    "required": True,
                    "example": conn.base_url,
                }

        return schema

    def _extract_required_permissions(self, conn: ToolConnection) -> List[str]:
        """Extract required permissions from connection config"""
        return conn.config.get("required_permissions", [])

    def _coerce_datetime(self, value: Optional[Any]) -> Optional[datetime]:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        return self.from_isoformat(value)

    def _row_to_connection(self, row) -> ToolConnection:
        """Convert database row to ToolConnection model"""
        return ToolConnection(
            id=row.id,
            profile_id=row.profile_id,
            tool_type=row.tool_type,
            connection_type=row.connection_type,
            name=row.name,
            description=row.description,
            icon=row.icon,
            api_key=row.api_key,
            api_secret=row.api_secret,
            oauth_token=row.oauth_token,
            oauth_refresh_token=row.oauth_refresh_token,
            base_url=row.base_url,
            remote_cluster_url=row.remote_cluster_url,
            remote_connection_id=row.remote_connection_id,
            config=self.deserialize_json(row.config, {}),
            associated_roles=self.deserialize_json(row.associated_roles, []),
            is_active=row.is_active if row.is_active is not None else False,
            is_validated=row.is_validated if row.is_validated is not None else False,
            last_validated_at=self._coerce_datetime(row.last_validated_at),
            validation_error=row.validation_error,
            usage_count=row.usage_count or 0,
            last_used_at=self._coerce_datetime(row.last_used_at),
            created_at=self._coerce_datetime(row.created_at) or _utc_now(),
            updated_at=self._coerce_datetime(row.updated_at) or _utc_now(),
            x_platform=self.deserialize_json(row.x_platform) if row.x_platform else None,
            data_source_type=getattr(row, "data_source_type", None),
            tenant_id=getattr(row, "tenant_id", None),
            owner_profile_id=getattr(row, "owner_profile_id", None),
        )
