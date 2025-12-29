"""
Lens Receipt Store for persistence.

Stores lens receipts for execution observability.
"""
import uuid
from typing import Optional, List
from datetime import datetime, timezone

from app.services.stores.base import StoreBase
from app.models.lens_receipt import LensReceipt, TriggeredNode
import json


class LensReceiptStore(StoreBase):
    """Store for managing lens receipts"""

    def save(self, receipt: LensReceipt) -> LensReceipt:
        """Save receipt"""
        receipt_id = receipt.id or str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute('''
                INSERT OR REPLACE INTO lens_receipts (
                    id, execution_id, workspace_id, effective_lens_hash,
                    triggered_nodes_json, base_output, lens_output, diff_summary, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                receipt_id,
                receipt.execution_id,
                receipt.workspace_id,
                receipt.effective_lens_hash,
                json.dumps([n.dict() for n in receipt.triggered_nodes], default=str) if receipt.triggered_nodes else None,
                receipt.base_output,
                receipt.lens_output,
                receipt.diff_summary,
                self.to_isoformat(now)
            ))
            conn.commit()

            return self.get_by_execution_id(receipt.execution_id)

    def get_by_execution_id(self, execution_id: str) -> Optional[LensReceipt]:
        """Get receipt by execution ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM lens_receipts WHERE execution_id = ?
            ''', (execution_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_receipt(row)

    def get_by_workspace_id(self, workspace_id: str, limit: int = 100) -> List[LensReceipt]:
        """Get receipts by workspace ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM lens_receipts
                WHERE workspace_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            ''', (workspace_id, limit))
            rows = cursor.fetchall()
            return [self._row_to_receipt(row) for row in rows]

    def _row_to_receipt(self, row) -> LensReceipt:
        """Convert database row to LensReceipt"""
        triggered_nodes = []
        if row['triggered_nodes_json']:
            nodes_data = json.loads(row['triggered_nodes_json'])
            triggered_nodes = [TriggeredNode(**node_data) for node_data in nodes_data]

        return LensReceipt(
            id=row['id'],
            execution_id=row['execution_id'],
            workspace_id=row['workspace_id'],
            effective_lens_hash=row['effective_lens_hash'],
            triggered_nodes=triggered_nodes,
            base_output=row['base_output'],
            lens_output=row['lens_output'],
            diff_summary=row['diff_summary'],
            created_at=self.from_isoformat(row['created_at'])
        )

