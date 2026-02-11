"""
Workspace Resource Binding Store
Manages persistent storage for workspace resource bindings
"""

from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)
from typing import List, Optional, Dict, Any

from sqlalchemy import text

from app.models.workspace_resource_binding import (
    WorkspaceResourceBinding,
    ResourceType,
    AccessMode,
)
from app.services.stores.postgres_base import PostgresStoreBase


class WorkspaceResourceBindingStore(PostgresStoreBase):
    """
    Store for workspace resource bindings

    Manages workspace overlay layer for shared resources.
    """

    def __init__(self, db_path: Optional[str] = None, db_role: str = "core"):
        super().__init__(db_role=db_role)
        self.db_path = db_path

    def save_binding(self, binding: WorkspaceResourceBinding) -> WorkspaceResourceBinding:
        """Save or update a workspace resource binding"""
        binding.updated_at = _utc_now()

        with self.transaction() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO workspace_resource_bindings (
                        id, workspace_id, resource_type, resource_id, access_mode,
                        overrides, created_at, updated_at
                    ) VALUES (
                        :id, :workspace_id, :resource_type, :resource_id, :access_mode,
                        :overrides, :created_at, :updated_at
                    )
                    ON CONFLICT (id) DO UPDATE SET
                        workspace_id = EXCLUDED.workspace_id,
                        resource_type = EXCLUDED.resource_type,
                        resource_id = EXCLUDED.resource_id,
                        access_mode = EXCLUDED.access_mode,
                        overrides = EXCLUDED.overrides,
                        created_at = EXCLUDED.created_at,
                        updated_at = EXCLUDED.updated_at
                """
                ),
                {
                    "id": binding.id,
                    "workspace_id": binding.workspace_id,
                    "resource_type": binding.resource_type.value,
                    "resource_id": binding.resource_id,
                    "access_mode": binding.access_mode.value,
                    "overrides": self.serialize_json(binding.overrides or {}),
                    "created_at": binding.created_at,
                    "updated_at": binding.updated_at,
                },
            )

        return binding

    def get_binding(
        self, binding_id: str, workspace_id: Optional[str] = None
    ) -> Optional[WorkspaceResourceBinding]:
        """Get a specific binding by ID"""
        query_parts = ["SELECT * FROM workspace_resource_bindings WHERE id = :id"]
        params: Dict[str, Any] = {"id": binding_id}
        if workspace_id:
            query_parts.append("AND workspace_id = :workspace_id")
            params["workspace_id"] = workspace_id

        with self.get_connection() as conn:
            row = conn.execute(text(" ".join(query_parts)), params).fetchone()
            if not row:
                return None
            return self._row_to_binding(row)

    def get_binding_by_resource(
        self,
        workspace_id: str,
        resource_type: ResourceType,
        resource_id: str,
    ) -> Optional[WorkspaceResourceBinding]:
        """Get binding for a specific resource in a workspace"""
        with self.get_connection() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT * FROM workspace_resource_bindings
                    WHERE workspace_id = :workspace_id
                      AND resource_type = :resource_type
                      AND resource_id = :resource_id
                """
                ),
                {
                    "workspace_id": workspace_id,
                    "resource_type": resource_type.value,
                    "resource_id": resource_id,
                },
            ).fetchone()
            if not row:
                return None
            return self._row_to_binding(row)

    def list_bindings_by_workspace(
        self, workspace_id: str, resource_type: Optional[ResourceType] = None
    ) -> List[WorkspaceResourceBinding]:
        """
        List all bindings for a workspace

        Optionally filter by resource_type.
        """
        query_parts = [
            "SELECT * FROM workspace_resource_bindings WHERE workspace_id = :workspace_id"
        ]
        params: Dict[str, Any] = {"workspace_id": workspace_id}

        if resource_type:
            query_parts.append("AND resource_type = :resource_type")
            params["resource_type"] = resource_type.value

        query_parts.append("ORDER BY resource_type, resource_id")

        with self.get_connection() as conn:
            rows = conn.execute(text(" ".join(query_parts)), params).fetchall()
            return [self._row_to_binding(row) for row in rows]

    def list_bindings_by_resource(
        self, resource_type: ResourceType, resource_id: str
    ) -> List[WorkspaceResourceBinding]:
        """
        List all workspaces that use a specific resource

        Useful for finding which workspaces are affected when a shared resource changes.
        """
        with self.get_connection() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT * FROM workspace_resource_bindings
                    WHERE resource_type = :resource_type
                      AND resource_id = :resource_id
                    ORDER BY workspace_id
                """
                ),
                {
                    "resource_type": resource_type.value,
                    "resource_id": resource_id,
                },
            ).fetchall()
            return [self._row_to_binding(row) for row in rows]

    def delete_binding(
        self, binding_id: str, workspace_id: Optional[str] = None
    ) -> bool:
        """Delete a binding"""
        query_parts = ["DELETE FROM workspace_resource_bindings WHERE id = :id"]
        params: Dict[str, Any] = {"id": binding_id}

        if workspace_id:
            query_parts.append("AND workspace_id = :workspace_id")
            params["workspace_id"] = workspace_id

        with self.transaction() as conn:
            result = conn.execute(text(" ".join(query_parts)), params)
            return result.rowcount > 0

    def delete_binding_by_resource(
        self, workspace_id: str, resource_type: ResourceType, resource_id: str
    ) -> bool:
        """Delete binding for a specific resource"""
        with self.transaction() as conn:
            result = conn.execute(
                text(
                    """
                    DELETE FROM workspace_resource_bindings
                    WHERE workspace_id = :workspace_id
                      AND resource_type = :resource_type
                      AND resource_id = :resource_id
                """
                ),
                {
                    "workspace_id": workspace_id,
                    "resource_type": resource_type.value,
                    "resource_id": resource_id,
                },
            )
            return result.rowcount > 0

    def _coerce_datetime(self, value: Optional[Any]) -> Optional[datetime]:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        return self.from_isoformat(value)

    def _row_to_binding(self, row) -> WorkspaceResourceBinding:
        """Convert database row to WorkspaceResourceBinding model"""
        return WorkspaceResourceBinding(
            id=row.id,
            workspace_id=row.workspace_id,
            resource_type=ResourceType(row.resource_type),
            resource_id=row.resource_id,
            access_mode=AccessMode(row.access_mode),
            overrides=self.deserialize_json(row.overrides, {}),
            created_at=self._coerce_datetime(row.created_at),
            updated_at=self._coerce_datetime(row.updated_at),
        )
