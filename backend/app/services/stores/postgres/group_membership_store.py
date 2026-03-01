"""Workspace group memberships store — CRUD for multi-group membership."""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from app.services.stores.postgres_base import PostgresStoreBase

logger = logging.getLogger(__name__)


class GroupMembershipStore(PostgresStoreBase):
    """Store for workspace_group_memberships join table."""

    def add_membership(
        self,
        workspace_id: str,
        group_id: str,
        role: str = "cell",
    ) -> Dict[str, Any]:
        """Add a workspace to a group."""
        query = text(
            """
            INSERT INTO workspace_group_memberships
                (workspace_id, group_id, role)
            VALUES (:workspace_id, :group_id, :role)
            ON CONFLICT (workspace_id, group_id) DO UPDATE
                SET role = :role
            RETURNING workspace_id, group_id, role, joined_at
        """
        )
        with self.get_connection() as conn:
            row = conn.execute(
                query,
                {
                    "workspace_id": workspace_id,
                    "group_id": group_id,
                    "role": role,
                },
            ).fetchone()
            conn.commit()
            return {
                "workspace_id": row.workspace_id,
                "group_id": row.group_id,
                "role": row.role,
                "joined_at": row.joined_at.isoformat() if row.joined_at else None,
            }

    def remove_membership(self, workspace_id: str, group_id: str) -> bool:
        """Remove a workspace from a group. Returns True if removed."""
        query = text(
            """
            DELETE FROM workspace_group_memberships
            WHERE workspace_id = :workspace_id AND group_id = :group_id
        """
        )
        with self.get_connection() as conn:
            result = conn.execute(
                query,
                {
                    "workspace_id": workspace_id,
                    "group_id": group_id,
                },
            )
            conn.commit()
            return result.rowcount > 0

    def list_groups_for_workspace(self, workspace_id: str) -> List[Dict[str, Any]]:
        """List all groups a workspace belongs to."""
        query = text(
            """
            SELECT wgm.group_id, wgm.role, wgm.joined_at,
                   wg.display_name, wg.owner_user_id
            FROM workspace_group_memberships wgm
            JOIN workspace_groups wg ON wg.id = wgm.group_id
            WHERE wgm.workspace_id = :workspace_id
            ORDER BY wgm.joined_at ASC
        """
        )
        with self.get_connection() as conn:
            rows = conn.execute(query, {"workspace_id": workspace_id}).fetchall()
            return [
                {
                    "group_id": row.group_id,
                    "role": row.role,
                    "joined_at": row.joined_at.isoformat() if row.joined_at else None,
                    "display_name": row.display_name,
                    "owner_user_id": row.owner_user_id,
                }
                for row in rows
            ]

    def list_workspaces_in_group(self, group_id: str) -> List[Dict[str, Any]]:
        """List all workspaces belonging to a group."""
        query = text(
            """
            SELECT wgm.workspace_id, wgm.role, wgm.joined_at,
                   w.title, w.visibility
            FROM workspace_group_memberships wgm
            JOIN workspaces w ON w.id = wgm.workspace_id
            WHERE wgm.group_id = :group_id
            ORDER BY wgm.joined_at ASC
        """
        )
        with self.get_connection() as conn:
            rows = conn.execute(query, {"group_id": group_id}).fetchall()
            return [
                {
                    "workspace_id": row.workspace_id,
                    "role": row.role,
                    "joined_at": row.joined_at.isoformat() if row.joined_at else None,
                    "title": row.title,
                    "visibility": row.visibility,
                }
                for row in rows
            ]
