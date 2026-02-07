"""
Lens Receipt Store for persistence.

Stores lens receipts for execution observability.
"""
import uuid
import json
from typing import Optional, List
from datetime import datetime, timezone

from sqlalchemy import text

from app.services.stores.postgres_base import PostgresStoreBase
from app.models.lens_receipt import LensReceipt, TriggeredNode


class LensReceiptStore(PostgresStoreBase):
    """Store for managing lens receipts (Postgres)."""

    def __init__(self, db_path: Optional[str] = None, db_role: str = "core"):
        super().__init__(db_role=db_role)
        self.db_path = db_path

    def save(self, receipt: LensReceipt) -> LensReceipt:
        """Save receipt"""
        receipt_id = receipt.id or str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        with self.transaction() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO lens_receipts (
                        id, execution_id, workspace_id, effective_lens_hash,
                        triggered_nodes_json, base_output, lens_output, diff_summary, created_at
                    ) VALUES (
                        :id, :execution_id, :workspace_id, :effective_lens_hash,
                        :triggered_nodes_json, :base_output, :lens_output, :diff_summary, :created_at
                    )
                    ON CONFLICT (id) DO UPDATE SET
                        execution_id = EXCLUDED.execution_id,
                        workspace_id = EXCLUDED.workspace_id,
                        effective_lens_hash = EXCLUDED.effective_lens_hash,
                        triggered_nodes_json = EXCLUDED.triggered_nodes_json,
                        base_output = EXCLUDED.base_output,
                        lens_output = EXCLUDED.lens_output,
                        diff_summary = EXCLUDED.diff_summary,
                        created_at = EXCLUDED.created_at
                """
                ),
                {
                    "id": receipt_id,
                    "execution_id": receipt.execution_id,
                    "workspace_id": receipt.workspace_id,
                    "effective_lens_hash": receipt.effective_lens_hash,
                    "triggered_nodes_json": (
                        json.dumps([n.dict() for n in receipt.triggered_nodes], default=str)
                        if receipt.triggered_nodes
                        else None
                    ),
                    "base_output": receipt.base_output,
                    "lens_output": receipt.lens_output,
                    "diff_summary": receipt.diff_summary,
                    "created_at": now,
                },
            )

        return self.get_by_execution_id(receipt.execution_id)

    def get_by_execution_id(self, execution_id: str) -> Optional[LensReceipt]:
        """Get receipt by execution ID"""
        with self.get_connection() as conn:
            row = conn.execute(
                text("SELECT * FROM lens_receipts WHERE execution_id = :execution_id"),
                {"execution_id": execution_id},
            ).fetchone()
            if not row:
                return None
            return self._row_to_receipt(row)

    def get_by_workspace_id(self, workspace_id: str, limit: int = 100) -> List[LensReceipt]:
        """Get receipts by workspace ID"""
        with self.get_connection() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT * FROM lens_receipts
                    WHERE workspace_id = :workspace_id
                    ORDER BY created_at DESC
                    LIMIT :limit
                """
                ),
                {"workspace_id": workspace_id, "limit": limit},
            ).fetchall()
            return [self._row_to_receipt(row) for row in rows]

    def _row_to_receipt(self, row) -> LensReceipt:
        """Convert database row to LensReceipt"""
        data = row._mapping if hasattr(row, "_mapping") else row

        triggered_nodes = []
        if data["triggered_nodes_json"]:
            nodes_data = json.loads(data["triggered_nodes_json"])
            triggered_nodes = [TriggeredNode(**node_data) for node_data in nodes_data]

        return LensReceipt(
            id=data["id"],
            execution_id=data["execution_id"],
            workspace_id=data["workspace_id"],
            effective_lens_hash=data["effective_lens_hash"],
            triggered_nodes=triggered_nodes,
            base_output=data["base_output"],
            lens_output=data["lens_output"],
            diff_summary=data["diff_summary"],
            created_at=data["created_at"],
        )
