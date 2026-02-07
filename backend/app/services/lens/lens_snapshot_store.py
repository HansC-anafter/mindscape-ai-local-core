"""
Lens Snapshot Store for persistence.

Stores lens snapshots with hash-based deduplication.
"""
import uuid
import json
from typing import Optional
from datetime import datetime, timezone

from sqlalchemy import text

from app.services.stores.postgres_base import PostgresStoreBase
from app.models.lens_snapshot import LensSnapshot
from app.models.lens_kernel import LensNode


class LensSnapshotStore(PostgresStoreBase):
    """Store for managing lens snapshots (Postgres)."""

    def __init__(self, db_path: Optional[str] = None, db_role: str = "core"):
        super().__init__(db_role=db_role)
        self.db_path = db_path

    def save_if_not_exists(self, snapshot: LensSnapshot) -> LensSnapshot:
        """
        Save snapshot if hash doesn't exist

        Args:
            snapshot: LensSnapshot to save

        Returns:
            Saved or existing snapshot
        """
        snapshot_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        with self.transaction() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO lens_snapshots (
                        id, effective_lens_hash, profile_id, workspace_id, session_id,
                        nodes_json, created_at
                    ) VALUES (
                        :id, :effective_lens_hash, :profile_id, :workspace_id, :session_id,
                        :nodes_json, :created_at
                    )
                    ON CONFLICT (effective_lens_hash) DO NOTHING
                """
                ),
                {
                    "id": snapshot_id,
                    "effective_lens_hash": snapshot.effective_lens_hash,
                    "profile_id": snapshot.profile_id,
                    "workspace_id": snapshot.workspace_id,
                    "session_id": snapshot.session_id,
                    "nodes_json": json.dumps([n.dict() for n in snapshot.nodes], default=str),
                    "created_at": now,
                },
            )

        return self.get_by_hash(snapshot.effective_lens_hash)

    def get_by_hash(self, lens_hash: str) -> Optional[LensSnapshot]:
        """Get snapshot by hash"""
        with self.get_connection() as conn:
            row = conn.execute(
                text("SELECT * FROM lens_snapshots WHERE effective_lens_hash = :hash"),
                {"hash": lens_hash},
            ).fetchone()
            if not row:
                return None
            return self._row_to_snapshot(row)

    def get_by_id(self, snapshot_id: str) -> Optional[LensSnapshot]:
        """Get snapshot by ID"""
        with self.get_connection() as conn:
            row = conn.execute(
                text("SELECT * FROM lens_snapshots WHERE id = :id"),
                {"id": snapshot_id},
            ).fetchone()
            if not row:
                return None
            return self._row_to_snapshot(row)

    def _row_to_snapshot(self, row) -> LensSnapshot:
        """Convert database row to LensSnapshot"""
        data = row._mapping if hasattr(row, "_mapping") else row

        nodes_data = json.loads(data["nodes_json"])
        nodes = [LensNode(**node_data) for node_data in nodes_data]

        return LensSnapshot(
            id=data["id"],
            effective_lens_hash=data["effective_lens_hash"],
            profile_id=data["profile_id"],
            workspace_id=data["workspace_id"],
            session_id=data["session_id"],
            nodes=nodes,
            created_at=data["created_at"],
        )
