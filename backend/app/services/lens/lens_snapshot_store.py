"""
Lens Snapshot Store for persistence.

Stores lens snapshots with hash-based deduplication.
"""
import uuid
from typing import Optional
from datetime import datetime, timezone

from app.services.stores.base import StoreBase
from app.models.lens_snapshot import LensSnapshot
from app.models.lens_kernel import LensNode
import json


class LensSnapshotStore(StoreBase):
    """Store for managing lens snapshots"""

    def save_if_not_exists(self, snapshot: LensSnapshot) -> LensSnapshot:
        """
        Save snapshot if hash doesn't exist

        Args:
            snapshot: LensSnapshot to save

        Returns:
            Saved or existing snapshot
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute('''
                SELECT * FROM lens_snapshots WHERE effective_lens_hash = ?
            ''', (snapshot.effective_lens_hash,))
            existing = cursor.fetchone()

            if existing:
                return self._row_to_snapshot(existing)

            snapshot_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc)

            cursor.execute('''
                INSERT INTO lens_snapshots (
                    id, effective_lens_hash, profile_id, workspace_id, session_id,
                    nodes_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                snapshot_id,
                snapshot.effective_lens_hash,
                snapshot.profile_id,
                snapshot.workspace_id,
                snapshot.session_id,
                json.dumps([n.dict() for n in snapshot.nodes], default=str),
                self.to_isoformat(now)
            ))
            conn.commit()

            return self.get_by_hash(snapshot.effective_lens_hash)

    def get_by_hash(self, lens_hash: str) -> Optional[LensSnapshot]:
        """Get snapshot by hash"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM lens_snapshots WHERE effective_lens_hash = ?
            ''', (lens_hash,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_snapshot(row)

    def get_by_id(self, snapshot_id: str) -> Optional[LensSnapshot]:
        """Get snapshot by ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM lens_snapshots WHERE id = ?
            ''', (snapshot_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_snapshot(row)

    def _row_to_snapshot(self, row) -> LensSnapshot:
        """Convert database row to LensSnapshot"""
        from app.models.lens_kernel import LensNode

        nodes_data = json.loads(row['nodes_json'])
        nodes = [LensNode(**node_data) for node_data in nodes_data]

        return LensSnapshot(
            id=row['id'],
            effective_lens_hash=row['effective_lens_hash'],
            profile_id=row['profile_id'],
            workspace_id=row['workspace_id'],
            session_id=row['session_id'],
            nodes=nodes,
            created_at=self.from_isoformat(row['created_at'])
        )

