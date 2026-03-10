"""
MetaScopeStore — CRUD for meta_scopes table (mindscape_core DB).

Part of ADR-001 v2 Phase 0 Foundation. L4 dynamic governance range selector.
"""

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from backend.app.models.personal_governance.meta_scope import MetaScope
from backend.app.services.stores.postgres_base import PostgresStoreBase

logger = logging.getLogger(__name__)


class MetaScopeStore(PostgresStoreBase):
    """PostgreSQL store for meta scopes (L4)."""

    def create(self, scope: MetaScope) -> MetaScope:
        """Persist a new meta scope."""
        query = text(
            """
            INSERT INTO meta_scopes (
                id, owner_profile_id, scope_kind, included_workspaces,
                included_projects, included_inboxes, time_window, goal_horizon,
                purpose, scope_snapshot_at, scope_resolution_strategy,
                resolved_digest_ids, resolved_workspace_states, created_at, metadata
            ) VALUES (
                :id, :owner_profile_id, :scope_kind, :included_workspaces,
                :included_projects, :included_inboxes, :time_window, :goal_horizon,
                :purpose, :scope_snapshot_at, :scope_resolution_strategy,
                :resolved_digest_ids, :resolved_workspace_states, :created_at, :metadata
            )
        """
        )
        params = {
            "id": scope.id,
            "owner_profile_id": scope.owner_profile_id,
            "scope_kind": scope.scope_kind,
            "included_workspaces": self.serialize_json(scope.included_workspaces),
            "included_projects": self.serialize_json(scope.included_projects),
            "included_inboxes": self.serialize_json(scope.included_inboxes),
            "time_window": scope.time_window,
            "goal_horizon": scope.goal_horizon,
            "purpose": scope.purpose,
            "scope_snapshot_at": scope.scope_snapshot_at,
            "scope_resolution_strategy": scope.scope_resolution_strategy,
            "resolved_digest_ids": self.serialize_json(scope.resolved_digest_ids),
            "resolved_workspace_states": self.serialize_json(
                scope.resolved_workspace_states
            ),
            "created_at": scope.created_at,
            "metadata": self.serialize_json(scope.metadata),
        }
        with self.transaction() as conn:
            conn.execute(query, params)
        return scope

    def get(self, scope_id: str) -> Optional[MetaScope]:
        """Get a single scope by ID."""
        query = text("SELECT * FROM meta_scopes WHERE id = :id")
        with self.get_connection() as conn:
            row = conn.execute(query, {"id": scope_id}).fetchone()
            if not row:
                return None
            return self._row_to_scope(row)

    def list_by_owner(self, owner_profile_id: str, limit: int = 20) -> List[MetaScope]:
        """List scopes for an owner, most recent first."""
        query = text(
            "SELECT * FROM meta_scopes WHERE owner_profile_id = :owner "
            "ORDER BY created_at DESC LIMIT :limit"
        )
        with self.get_connection() as conn:
            rows = conn.execute(
                query, {"owner": owner_profile_id, "limit": limit}
            ).fetchall()
            return [self._row_to_scope(r) for r in rows]

    def update_snapshot(self, scope: MetaScope) -> bool:
        """Update snapshot fields after scope freeze."""
        query = text(
            """
            UPDATE meta_scopes SET
                scope_snapshot_at = :snapshot_at,
                resolved_digest_ids = :digest_ids,
                resolved_workspace_states = :ws_states
            WHERE id = :id
        """
        )
        with self.transaction() as conn:
            result = conn.execute(
                query,
                {
                    "id": scope.id,
                    "snapshot_at": scope.scope_snapshot_at,
                    "digest_ids": self.serialize_json(scope.resolved_digest_ids),
                    "ws_states": self.serialize_json(scope.resolved_workspace_states),
                },
            )
            return result.rowcount > 0

    def _row_to_scope(self, row) -> MetaScope:
        return MetaScope(
            id=row.id,
            owner_profile_id=row.owner_profile_id,
            scope_kind=row.scope_kind,
            included_workspaces=self.deserialize_json(
                row.included_workspaces, default=[]
            ),
            included_projects=self.deserialize_json(row.included_projects, default=[]),
            included_inboxes=self.deserialize_json(row.included_inboxes, default=[]),
            time_window=row.time_window,
            goal_horizon=row.goal_horizon,
            purpose=row.purpose,
            scope_snapshot_at=row.scope_snapshot_at,
            scope_resolution_strategy=row.scope_resolution_strategy,
            resolved_digest_ids=self.deserialize_json(
                row.resolved_digest_ids, default=[]
            ),
            resolved_workspace_states=self.deserialize_json(
                row.resolved_workspace_states, default={}
            ),
            created_at=row.created_at,
            metadata=self.deserialize_json(row.metadata, default={}),
        )
