"""
Playbook Flows Store

Manages PlaybookFlow persistence and retrieval.
"""

import logging
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)
from typing import Optional, List

from sqlalchemy import text

from app.models.playbook_flow import PlaybookFlow
from app.services.stores.postgres_base import PostgresStoreBase

logger = logging.getLogger(__name__)


class PlaybookFlowsStore(PostgresStoreBase):
    """Postgres-backed store for managing PlaybookFlow entries."""

    def __init__(self, db_path: Optional[str] = None, db_role: str = "core"):
        super().__init__(db_role=db_role)
        self.db_path = db_path

    def create_flow(self, flow: PlaybookFlow) -> PlaybookFlow:
        """Create a new PlaybookFlow"""
        with self.transaction() as conn:
            query = text(
                """
                INSERT INTO playbook_flows (
                    id, name, description, flow_definition, created_at, updated_at
                ) VALUES (
                    :id, :name, :description, :flow_definition, :created_at, :updated_at
                )
            """
            )
            conn.execute(
                query,
                {
                    "id": flow.id,
                    "name": flow.name,
                    "description": flow.description,
                    "flow_definition": self.serialize_json(flow.flow_definition),
                    "created_at": flow.created_at,
                    "updated_at": flow.updated_at,
                },
            )
            return flow

    def get_flow(self, flow_id: str) -> Optional[PlaybookFlow]:
        """Get PlaybookFlow by ID"""
        with self.get_connection() as conn:
            row = conn.execute(
                text("SELECT * FROM playbook_flows WHERE id = :flow_id"),
                {"flow_id": flow_id},
            ).fetchone()
            if not row:
                return None
            return self._row_to_flow(row)

    def get_flow_by_name(self, name: str) -> Optional[PlaybookFlow]:
        """Get PlaybookFlow by name"""
        with self.get_connection() as conn:
            row = conn.execute(
                text("SELECT * FROM playbook_flows WHERE name = :name"),
                {"name": name},
            ).fetchone()
            if not row:
                return None
            return self._row_to_flow(row)

    def list_flows(self, limit: int = 100, offset: int = 0) -> List[PlaybookFlow]:
        """List PlaybookFlows with pagination"""
        with self.get_connection() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT * FROM playbook_flows
                    ORDER BY created_at DESC
                    LIMIT :limit
                    OFFSET :offset
                """
                ),
                {"limit": limit, "offset": offset},
            ).fetchall()
            return [self._row_to_flow(row) for row in rows]

    def update_flow(self, flow: PlaybookFlow) -> PlaybookFlow:
        """Update an existing PlaybookFlow"""
        flow.updated_at = _utc_now()
        with self.transaction() as conn:
            conn.execute(
                text(
                    """
                    UPDATE playbook_flows
                    SET name = :name,
                        description = :description,
                        flow_definition = :flow_definition,
                        updated_at = :updated_at
                    WHERE id = :id
                """
                ),
                {
                    "id": flow.id,
                    "name": flow.name,
                    "description": flow.description,
                    "flow_definition": self.serialize_json(flow.flow_definition),
                    "updated_at": flow.updated_at,
                },
            )
            return flow

    def delete_flow(self, flow_id: str) -> bool:
        """Delete a PlaybookFlow"""
        with self.transaction() as conn:
            result = conn.execute(
                text("DELETE FROM playbook_flows WHERE id = :flow_id"),
                {"flow_id": flow_id},
            )
            return result.rowcount > 0

    def _coerce_datetime(self, value: Optional[datetime]) -> Optional[datetime]:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        return self.from_isoformat(value)

    def _row_to_flow(self, row) -> PlaybookFlow:
        """Convert database row to PlaybookFlow model"""
        flow_definition = self.deserialize_json(row.flow_definition) if row.flow_definition else {}
        description = row.description if row.description else None

        return PlaybookFlow(
            id=row.id,
            name=row.name,
            description=description,
            flow_definition=flow_definition,
            created_at=self._coerce_datetime(row.created_at),
            updated_at=self._coerce_datetime(row.updated_at),
        )
