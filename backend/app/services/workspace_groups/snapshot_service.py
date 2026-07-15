"""Immutable topology snapshots created once at run admission."""

import hashlib
import json
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import text

from backend.app.services.stores.postgres_base import PostgresStoreBase
from backend.app.services.workspace_groups.contracts import (
    ActiveWorkspaceGroupContext,
    WorkspaceGroupTopologySnapshot,
)


class WorkspaceGroupSnapshotService(PostgresStoreBase):
    def get_or_create(
        self,
        context: ActiveWorkspaceGroupContext,
        *,
        actor_user_id: str,
    ) -> WorkspaceGroupTopologySnapshot:
        payload = {
            "display_name": context.topology.display_name,
            "members": [
                member.model_dump(mode="json")
                for member in context.topology.members
            ],
            "dispatch_workspace_id": context.topology.dispatch_workspace_id,
            "cell_workspace_ids": context.topology.cell_workspace_ids,
        }
        canonical_payload = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        content_hash = hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()
        snapshot_id = f"wgs_{uuid4().hex}"
        with self.transaction() as conn:
            row = conn.execute(
                text(
                    """
                    WITH inserted AS (
                        INSERT INTO workspace_group_topology_snapshots
                            (id, group_id, group_revision, content_hash, payload,
                             created_by_user_id)
                        VALUES
                            (:id, :group_id, :group_revision, :content_hash,
                             CAST(:payload AS jsonb), :created_by_user_id)
                        ON CONFLICT
                            (group_id, group_revision, content_hash)
                        DO NOTHING
                        RETURNING *
                    )
                    SELECT * FROM inserted
                    UNION ALL
                    SELECT * FROM workspace_group_topology_snapshots
                    WHERE group_id = :group_id
                      AND group_revision = :group_revision
                      AND content_hash = :content_hash
                    LIMIT 1
                    """
                ),
                {
                    "id": snapshot_id,
                    "group_id": context.group_id,
                    "group_revision": context.revision,
                    "content_hash": content_hash,
                    "payload": canonical_payload,
                    "created_by_user_id": actor_user_id,
                },
            ).fetchone()
        if row is None:
            raise RuntimeError("workspace group snapshot admission failed")
        return self._row_to_snapshot(row)

    def get(self, snapshot_id: str) -> Optional[WorkspaceGroupTopologySnapshot]:
        with self.get_connection() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT * FROM workspace_group_topology_snapshots
                    WHERE id = :snapshot_id
                    """
                ),
                {"snapshot_id": snapshot_id},
            ).fetchone()
        return self._row_to_snapshot(row) if row else None

    def _row_to_snapshot(self, row: Any) -> WorkspaceGroupTopologySnapshot:
        payload = self.deserialize_json(row.payload, default={})
        return WorkspaceGroupTopologySnapshot.model_validate(
            {
                "id": row.id,
                "group_id": row.group_id,
                "display_name": payload.get("display_name", row.group_id),
                "group_revision": row.group_revision,
                "content_hash": row.content_hash,
                "members": payload.get("members", []),
                "dispatch_workspace_id": payload.get("dispatch_workspace_id"),
                "cell_workspace_ids": payload.get("cell_workspace_ids", []),
                "created_by_user_id": row.created_by_user_id,
                "created_at": row.created_at,
            }
        )
