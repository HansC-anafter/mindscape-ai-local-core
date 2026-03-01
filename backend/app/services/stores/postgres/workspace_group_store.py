"""WorkspaceGroup store — Postgres persistence for workspace groups."""

import logging
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import text

from ..postgres_base import PostgresStoreBase
from app.models.workspace_group import WorkspaceGroup

logger = logging.getLogger(__name__)


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


_ENSURE_TABLE_SQL = text(
    """
    CREATE TABLE IF NOT EXISTS workspace_groups (
        id VARCHAR(64) PRIMARY KEY,
        display_name VARCHAR(255) NOT NULL,
        owner_user_id VARCHAR(64) NOT NULL,
        description TEXT,
        role_map JSONB NOT NULL DEFAULT '{}',
        metadata JSONB DEFAULT '{}',
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_wg_owner ON workspace_groups(owner_user_id);
"""
)


class PostgresWorkspaceGroupStore(PostgresStoreBase):
    """Postgres CRUD for workspace groups."""

    def ensure_table(self) -> None:
        """Create the workspace_groups table if it does not exist."""
        with self.transaction() as conn:
            conn.execute(_ENSURE_TABLE_SQL)
            logger.info("[WorkspaceGroupStore] Table ensured")

    # ── CRUD ──

    def create(self, group: WorkspaceGroup) -> WorkspaceGroup:
        """Insert a new workspace group."""
        with self.transaction() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO workspace_groups
                        (id, display_name, owner_user_id, description,
                         role_map, metadata, created_at, updated_at)
                    VALUES
                        (:id, :display_name, :owner_user_id, :description,
                         :role_map, :metadata, :created_at, :updated_at)
                """
                ),
                {
                    "id": group.id,
                    "display_name": group.display_name,
                    "owner_user_id": group.owner_user_id,
                    "description": group.description,
                    "role_map": self.serialize_json(group.role_map),
                    "metadata": self.serialize_json(group.metadata or {}),
                    "created_at": group.created_at,
                    "updated_at": group.updated_at,
                },
            )
            logger.info(f"[WorkspaceGroupStore] Created group {group.id}")
            return group

    def get(self, group_id: str) -> Optional[WorkspaceGroup]:
        """Fetch a workspace group by ID."""
        with self.get_connection() as conn:
            row = conn.execute(
                text("SELECT * FROM workspace_groups WHERE id = :id"),
                {"id": group_id},
            ).fetchone()
            if not row:
                return None
            return self._row_to_group(row)

    def list_by_owner(
        self, owner_user_id: str, limit: int = 50
    ) -> List[WorkspaceGroup]:
        """List groups owned by a user."""
        with self.get_connection() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT * FROM workspace_groups
                    WHERE owner_user_id = :owner_user_id
                    ORDER BY updated_at DESC
                    LIMIT :limit
                """
                ),
                {"owner_user_id": owner_user_id, "limit": limit},
            ).fetchall()
            return [self._row_to_group(r) for r in rows]

    def get_by_workspace_id(self, workspace_id: str) -> Optional[WorkspaceGroup]:
        """Find the group containing a given workspace (via JSONB key lookup)."""
        with self.get_connection() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT * FROM workspace_groups
                    WHERE role_map ? :ws_id
                    LIMIT 1
                """
                ),
                {"ws_id": workspace_id},
            ).fetchone()
            if not row:
                return None
            return self._row_to_group(row)

    def update(self, group: WorkspaceGroup) -> WorkspaceGroup:
        """Update an existing workspace group."""
        group.updated_at = _utc_now()
        with self.transaction() as conn:
            conn.execute(
                text(
                    """
                    UPDATE workspace_groups SET
                        display_name = :display_name,
                        description = :description,
                        role_map = :role_map,
                        metadata = :metadata,
                        updated_at = :updated_at
                    WHERE id = :id
                """
                ),
                {
                    "display_name": group.display_name,
                    "description": group.description,
                    "role_map": self.serialize_json(group.role_map),
                    "metadata": self.serialize_json(group.metadata or {}),
                    "updated_at": group.updated_at,
                    "id": group.id,
                },
            )
            logger.info(f"[WorkspaceGroupStore] Updated group {group.id}")
            return group

    def delete(self, group_id: str) -> bool:
        """Delete a workspace group."""
        with self.transaction() as conn:
            result = conn.execute(
                text("DELETE FROM workspace_groups WHERE id = :id"),
                {"id": group_id},
            )
            return result.rowcount > 0

    # ── Helpers ──

    def _row_to_group(self, row) -> WorkspaceGroup:
        """Convert a database row to a WorkspaceGroup."""
        return WorkspaceGroup(
            id=row.id,
            display_name=row.display_name,
            owner_user_id=row.owner_user_id,
            description=row.description,
            role_map=self.deserialize_json(row.role_map, default={}),
            metadata=self.deserialize_json(row.metadata, default={}),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
