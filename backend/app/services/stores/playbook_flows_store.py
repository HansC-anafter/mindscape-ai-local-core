"""
Playbook Flows Store

Manages PlaybookFlow persistence and retrieval.
"""

import uuid
from datetime import datetime
from typing import Optional, List
import logging

from backend.app.models.playbook_flow import PlaybookFlow, FlowNode, FlowEdge
from backend.app.services.stores.base import StoreBase

logger = logging.getLogger(__name__)


class PlaybookFlowsStore(StoreBase):
    """Store for managing PlaybookFlow entries"""

    def create_flow(self, flow: PlaybookFlow) -> PlaybookFlow:
        """Create a new PlaybookFlow"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO playbook_flows (
                    id, name, description, flow_definition, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                flow.id,
                flow.name,
                flow.description,
                self.serialize_json(flow.flow_definition),
                self.to_isoformat(flow.created_at),
                self.to_isoformat(flow.updated_at)
            ))
            conn.commit()
            return flow

    def get_flow(self, flow_id: str) -> Optional[PlaybookFlow]:
        """Get PlaybookFlow by ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM playbook_flows WHERE id = ?', (flow_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_flow(row)

    def get_flow_by_name(self, name: str) -> Optional[PlaybookFlow]:
        """Get PlaybookFlow by name"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM playbook_flows WHERE name = ?', (name,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_flow(row)

    def list_flows(self, limit: int = 100, offset: int = 0) -> List[PlaybookFlow]:
        """List PlaybookFlows with pagination"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM playbook_flows
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
            ''', (limit, offset))
            rows = cursor.fetchall()
            return [self._row_to_flow(row) for row in rows]

    def update_flow(self, flow: PlaybookFlow) -> PlaybookFlow:
        """Update an existing PlaybookFlow"""
        flow.updated_at = datetime.utcnow()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE playbook_flows
                SET name = ?, description = ?, flow_definition = ?, updated_at = ?
                WHERE id = ?
            ''', (
                flow.name,
                flow.description,
                self.serialize_json(flow.flow_definition),
                self.to_isoformat(flow.updated_at),
                flow.id
            ))
            conn.commit()
            return flow

    def delete_flow(self, flow_id: str) -> bool:
        """Delete a PlaybookFlow"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM playbook_flows WHERE id = ?', (flow_id,))
            conn.commit()
            return cursor.rowcount > 0

    def _row_to_flow(self, row) -> PlaybookFlow:
        """Convert database row to PlaybookFlow model"""
        flow_definition = self.deserialize_json(row['flow_definition']) or {}
        return PlaybookFlow(
            id=row['id'],
            name=row['name'],
            description=row.get('description'),
            flow_definition=flow_definition,
            created_at=self.from_isoformat(row['created_at']),
            updated_at=self.from_isoformat(row['updated_at'])
        )

