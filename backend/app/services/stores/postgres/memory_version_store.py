"""PostgreSQL store for memory_versions."""

from typing import Any, Dict, List

from sqlalchemy import text

from backend.app.models.memory_contract import MemoryVersion
from backend.app.services.stores.postgres_base import PostgresStoreBase


class MemoryVersionStore(PostgresStoreBase):
    """CRUD helpers for memory_versions."""

    def create(self, version: MemoryVersion) -> MemoryVersion:
        with self.transaction() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO memory_versions (
                        id, memory_item_id, version_no, update_mode,
                        claim_snapshot, summary_snapshot, metadata_snapshot,
                        created_at, created_from_run_id
                    ) VALUES (
                        :id, :memory_item_id, :version_no, :update_mode,
                        :claim_snapshot, :summary_snapshot, :metadata_snapshot,
                        :created_at, :created_from_run_id
                    )
                    """
                ),
                {
                    "id": version.id,
                    "memory_item_id": version.memory_item_id,
                    "version_no": version.version_no,
                    "update_mode": version.update_mode,
                    "claim_snapshot": version.claim_snapshot,
                    "summary_snapshot": version.summary_snapshot,
                    "metadata_snapshot": self.serialize_json(version.metadata_snapshot),
                    "created_at": version.created_at,
                    "created_from_run_id": version.created_from_run_id,
                },
            )
        return version

    def list_by_memory_item(self, memory_item_id: str) -> List[MemoryVersion]:
        with self.get_connection() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT * FROM memory_versions
                    WHERE memory_item_id = :memory_item_id
                    ORDER BY version_no ASC
                    """
                ),
                {"memory_item_id": memory_item_id},
            ).fetchall()
        return [self._row_to_version(row) for row in rows]

    def get_next_version_no(self, memory_item_id: str) -> int:
        with self.get_connection() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT COALESCE(MAX(version_no), 0) AS max_version_no
                    FROM memory_versions
                    WHERE memory_item_id = :memory_item_id
                    """
                ),
                {"memory_item_id": memory_item_id},
            ).fetchone()
        max_version_no = (
            row.max_version_no
            if hasattr(row, "max_version_no")
            else row[0] if row else 0
        )
        return int(max_version_no or 0) + 1

    def _row_to_version(self, row: Any) -> MemoryVersion:
        data: Dict[str, Any] = row._mapping if hasattr(row, "_mapping") else row
        return MemoryVersion(
            id=data["id"],
            memory_item_id=data["memory_item_id"],
            version_no=data["version_no"],
            update_mode=data["update_mode"],
            claim_snapshot=data["claim_snapshot"],
            summary_snapshot=data.get("summary_snapshot"),
            metadata_snapshot=self.deserialize_json(
                data.get("metadata_snapshot"), default={}
            ),
            created_at=data["created_at"],
            created_from_run_id=data.get("created_from_run_id"),
        )
