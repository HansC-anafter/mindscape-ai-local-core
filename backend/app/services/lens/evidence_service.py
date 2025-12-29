"""
Evidence Service for Mind-Lens observability.

Provides evidence of node triggers and lens drift analysis.
"""
import logging
from typing import List, Optional
from datetime import datetime, timezone, timedelta

from backend.app.services.lens.lens_receipt_store import LensReceiptStore
from backend.app.services.stores.graph_store import GraphStore
from backend.app.models.evidence import Evidence, DriftReport
from backend.app.models.lens_receipt import LensReceipt, TriggeredNode
import os

logger = logging.getLogger(__name__)


class EvidenceService:
    """Service for managing evidence and drift"""

    def __init__(
        self,
        receipt_store: Optional[LensReceiptStore] = None,
        graph_store: Optional[GraphStore] = None
    ):
        if receipt_store:
            self.receipt_store = receipt_store
        else:
            if os.path.exists('/.dockerenv') or os.environ.get('PYTHONPATH') == '/app':
                db_path = '/app/data/mindscape.db'
            else:
                base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
                data_dir = os.path.join(base_dir, "data")
                os.makedirs(data_dir, exist_ok=True)
                db_path = os.path.join(data_dir, "mindscape.db")
            self.receipt_store = LensReceiptStore(db_path)

        if graph_store:
            self.graph_store = graph_store
        else:
            if os.path.exists('/.dockerenv') or os.environ.get('PYTHONPATH') == '/app':
                db_path = '/app/data/mindscape.db'
            else:
                base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
                data_dir = os.path.join(base_dir, "data")
                os.makedirs(data_dir, exist_ok=True)
                db_path = os.path.join(data_dir, "mindscape.db")
            self.graph_store = GraphStore(db_path)

    def get_node_evidence(
        self,
        node_id: str,
        limit: int = 3,
        workspace_id: Optional[str] = None
    ) -> List[Evidence]:
        """
        Get recent trigger evidence for a node

        Args:
            node_id: Node ID
            limit: Maximum number of evidence to return
            workspace_id: Optional workspace filter

        Returns:
            List of Evidence
        """
        node = self.graph_store.get_node(node_id)
        if not node:
            return []

        all_receipts = []
        if workspace_id:
            receipts = self.receipt_store.get_by_workspace_id(workspace_id, limit=1000)
        else:
            receipts = []
            for ws_id in self._get_all_workspace_ids():
                ws_receipts = self.receipt_store.get_by_workspace_id(ws_id, limit=100)
                receipts.extend(ws_receipts)

        evidence_list = []
        for receipt in receipts:
            for triggered_node in receipt.triggered_nodes:
                if triggered_node.node_id == node_id:
                    evidence_list.append(Evidence(
                        node_id=node_id,
                        node_label=triggered_node.node_label,
                        snapshot_id=receipt.effective_lens_hash,
                        execution_id=receipt.execution_id,
                        workspace_id=receipt.workspace_id,
                        output_snippet=receipt.lens_output[:200] if receipt.lens_output else "",
                        triggered_at=receipt.created_at
                    ))

        evidence_list.sort(key=lambda e: e.triggered_at, reverse=True)
        return evidence_list[:limit]

    def compute_drift(
        self,
        profile_id: str,
        days: int = 30
    ) -> DriftReport:
        """
        Compute lens drift over time

        Args:
            profile_id: Profile ID
            days: Number of days to analyze

        Returns:
            DriftReport
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

        all_receipts = []
        for ws_id in self._get_all_workspace_ids():
            receipts = self.receipt_store.get_by_workspace_id(ws_id, limit=1000)
            all_receipts.extend([
                r for r in receipts
                if r.created_at >= cutoff_date
            ])

        node_usage = {}
        for receipt in all_receipts:
            for triggered_node in receipt.triggered_nodes:
                node_id = triggered_node.node_id
                if node_id not in node_usage:
                    node_usage[node_id] = {
                        "node_id": node_id,
                        "node_label": triggered_node.node_label,
                        "trigger_count": 0,
                        "last_triggered": receipt.created_at
                    }
                node_usage[node_id]["trigger_count"] += 1
                if receipt.created_at > node_usage[node_id]["last_triggered"]:
                    node_usage[node_id]["last_triggered"] = receipt.created_at

        node_drift = sorted(
            node_usage.values(),
            key=lambda x: x["trigger_count"],
            reverse=True
        )

        return DriftReport(
            profile_id=profile_id,
            days=days,
            total_executions=len(all_receipts),
            node_drift=node_drift,
            created_at=datetime.now(timezone.utc)
        )

    def _get_all_workspace_ids(self) -> List[str]:
        """Get all workspace IDs from receipts"""
        with self.receipt_store.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT DISTINCT workspace_id FROM lens_receipts')
            return [row['workspace_id'] for row in cursor.fetchall()]

