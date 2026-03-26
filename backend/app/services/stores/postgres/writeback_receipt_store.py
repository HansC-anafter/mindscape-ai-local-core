"""PostgreSQL read helpers for writeback receipts."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from sqlalchemy import text

from backend.app.models.personal_governance.writeback_receipt import WritebackReceipt
from backend.app.services.stores.postgres_base import PostgresStoreBase


class WritebackReceiptStore(PostgresStoreBase):
    """Read access for persisted writeback receipts."""

    def list_by_canonical_memory_item(
        self,
        source_memory_item_id: str,
        *,
        limit: int = 50,
    ) -> List[WritebackReceipt]:
        with self.get_connection() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT *
                    FROM writeback_receipts
                    WHERE metadata::jsonb -> 'canonical_projection' ->> 'source_memory_item_id' = :source_memory_item_id
                    ORDER BY created_at ASC
                    LIMIT :limit
                    """
                ),
                {
                    "source_memory_item_id": source_memory_item_id,
                    "limit": limit,
                },
            ).fetchall()
        return [self._row_to_receipt(row) for row in rows]

    def _row_to_receipt(self, row: Any) -> WritebackReceipt:
        data: Dict[str, Any] = row._mapping if hasattr(row, "_mapping") else row
        created_at = data["created_at"]
        if created_at and not isinstance(created_at, datetime):
            created_at = datetime.fromisoformat(str(created_at))
        return WritebackReceipt(
            id=data["id"],
            meta_session_id=data["meta_session_id"],
            source_decision_id=data["source_decision_id"],
            target_table=data["target_table"],
            target_id=data["target_id"],
            writeback_type=data["writeback_type"],
            status=data["status"],
            error_detail=data.get("error_detail"),
            created_at=created_at,
            metadata=self.deserialize_json(data.get("metadata"), default={}),
        )
