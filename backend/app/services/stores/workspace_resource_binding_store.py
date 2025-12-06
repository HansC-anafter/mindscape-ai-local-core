"""
Workspace Resource Binding Store
Manages persistent storage for workspace resource bindings
"""

import sqlite3
import json
from datetime import datetime
from typing import List, Optional, Dict, Any
from pathlib import Path

from ...models.workspace_resource_binding import (
    WorkspaceResourceBinding,
    ResourceType,
    AccessMode
)


class WorkspaceResourceBindingStore:
    """
    Store for workspace resource bindings

    Manages workspace overlay layer for shared resources.
    """

    def __init__(self, db_path: str = "data/my_agent_console.db"):
        self.db_path = db_path
        self._ensure_tables()

    def _ensure_tables(self):
        """Create tables if they don't exist"""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Workspace resource bindings table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS workspace_resource_bindings (
                id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                resource_type TEXT NOT NULL,
                resource_id TEXT NOT NULL,
                access_mode TEXT NOT NULL DEFAULT 'read',
                overrides TEXT DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (workspace_id) REFERENCES workspaces(id)
            )
        """)

        # Composite index for common query patterns
        # Query: "Get all resources of a type for a workspace"
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_workspace_resource_bindings_workspace_type
            ON workspace_resource_bindings(workspace_id, resource_type)
        """)

        # Index for specific resource lookup
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_workspace_resource_bindings_workspace_resource
            ON workspace_resource_bindings(workspace_id, resource_type, resource_id)
        """)

        # Index for resource reverse lookup (which workspaces use this resource)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_workspace_resource_bindings_resource
            ON workspace_resource_bindings(resource_type, resource_id)
        """)

        conn.commit()
        conn.close()

    def save_binding(self, binding: WorkspaceResourceBinding) -> WorkspaceResourceBinding:
        """Save or update a workspace resource binding"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        binding.updated_at = datetime.utcnow()

        cursor.execute("""
            INSERT OR REPLACE INTO workspace_resource_bindings (
                id, workspace_id, resource_type, resource_id, access_mode,
                overrides, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            binding.id,
            binding.workspace_id,
            binding.resource_type.value,
            binding.resource_id,
            binding.access_mode.value,
            json.dumps(binding.overrides),
            binding.created_at.isoformat(),
            binding.updated_at.isoformat(),
        ))

        conn.commit()
        conn.close()

        return binding

    def get_binding(
        self,
        binding_id: str,
        workspace_id: Optional[str] = None
    ) -> Optional[WorkspaceResourceBinding]:
        """Get a specific binding by ID"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        if workspace_id:
            cursor.execute("""
                SELECT * FROM workspace_resource_bindings
                WHERE id = ? AND workspace_id = ?
            """, (binding_id, workspace_id))
        else:
            cursor.execute("""
                SELECT * FROM workspace_resource_bindings
                WHERE id = ?
            """, (binding_id,))

        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return self._row_to_binding(row)

    def get_binding_by_resource(
        self,
        workspace_id: str,
        resource_type: ResourceType,
        resource_id: str
    ) -> Optional[WorkspaceResourceBinding]:
        """Get binding for a specific resource in a workspace"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM workspace_resource_bindings
            WHERE workspace_id = ? AND resource_type = ? AND resource_id = ?
        """, (workspace_id, resource_type.value, resource_id))

        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return self._row_to_binding(row)

    def list_bindings_by_workspace(
        self,
        workspace_id: str,
        resource_type: Optional[ResourceType] = None
    ) -> List[WorkspaceResourceBinding]:
        """
        List all bindings for a workspace

        Optionally filter by resource_type.
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        if resource_type:
            cursor.execute("""
                SELECT * FROM workspace_resource_bindings
                WHERE workspace_id = ? AND resource_type = ?
                ORDER BY resource_type, resource_id
            """, (workspace_id, resource_type.value))
        else:
            cursor.execute("""
                SELECT * FROM workspace_resource_bindings
                WHERE workspace_id = ?
                ORDER BY resource_type, resource_id
            """, (workspace_id,))

        rows = cursor.fetchall()
        conn.close()

        return [self._row_to_binding(row) for row in rows]

    def list_bindings_by_resource(
        self,
        resource_type: ResourceType,
        resource_id: str
    ) -> List[WorkspaceResourceBinding]:
        """
        List all workspaces that use a specific resource

        Useful for finding which workspaces are affected when a shared resource changes.
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM workspace_resource_bindings
            WHERE resource_type = ? AND resource_id = ?
            ORDER BY workspace_id
        """, (resource_type.value, resource_id))

        rows = cursor.fetchall()
        conn.close()

        return [self._row_to_binding(row) for row in rows]

    def delete_binding(
        self,
        binding_id: str,
        workspace_id: Optional[str] = None
    ) -> bool:
        """Delete a binding"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        if workspace_id:
            cursor.execute("""
                DELETE FROM workspace_resource_bindings
                WHERE id = ? AND workspace_id = ?
            """, (binding_id, workspace_id))
        else:
            cursor.execute("""
                DELETE FROM workspace_resource_bindings
                WHERE id = ?
            """, (binding_id,))

        deleted = cursor.rowcount > 0
        conn.commit()
        conn.close()

        return deleted

    def delete_binding_by_resource(
        self,
        workspace_id: str,
        resource_type: ResourceType,
        resource_id: str
    ) -> bool:
        """Delete binding for a specific resource"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            DELETE FROM workspace_resource_bindings
            WHERE workspace_id = ? AND resource_type = ? AND resource_id = ?
        """, (workspace_id, resource_type.value, resource_id))

        deleted = cursor.rowcount > 0
        conn.commit()
        conn.close()

        return deleted

    def _row_to_binding(self, row: sqlite3.Row) -> WorkspaceResourceBinding:
        """Convert database row to WorkspaceResourceBinding model"""
        return WorkspaceResourceBinding(
            id=row["id"],
            workspace_id=row["workspace_id"],
            resource_type=ResourceType(row["resource_type"]),
            resource_id=row["resource_id"],
            access_mode=AccessMode(row["access_mode"]),
            overrides=json.loads(row["overrides"]) if row["overrides"] else {},
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

