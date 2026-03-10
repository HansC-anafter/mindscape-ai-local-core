"""
MetaMeetingSessionStore — Persistence for MetaMeetingSession.

ADR-001 v2 Phase 3.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from backend.app.models.personal_governance.meta_meeting_session import (
    MetaMeetingSession,
    MetaMeetingStatus,
)
from backend.app.services.stores.postgres_base import PostgresStoreBase

logger = logging.getLogger(__name__)


class MetaMeetingSessionStore(PostgresStoreBase):
    """CRUD operations for meta_meeting_sessions."""

    TABLE = "meta_meeting_sessions"

    def create(self, session: MetaMeetingSession) -> MetaMeetingSession:
        """Insert a new meta meeting session."""
        with self.transaction() as conn:
            conn.execute(
                text(
                    f"""
                    INSERT INTO {self.TABLE}
                    (id, owner_profile_id, status, meta_scope_id,
                     scope_snapshot, digest_ids, digest_count,
                     agenda, success_criteria, max_rounds,
                     created_at, metadata)
                    VALUES (:id, :owner, :status, :scope_id,
                            :snapshot, :digests, :dcount,
                            :agenda, :criteria, :max_rounds,
                            :created, :meta)
                """
                ),
                {
                    "id": session.id,
                    "owner": session.owner_profile_id,
                    "status": session.status.value,
                    "scope_id": session.meta_scope_id,
                    "snapshot": self.serialize_json(session.scope_snapshot),
                    "digests": self.serialize_json(session.digest_ids),
                    "dcount": session.digest_count,
                    "agenda": self.serialize_json(session.agenda),
                    "criteria": self.serialize_json(session.success_criteria),
                    "max_rounds": session.max_rounds,
                    "created": session.created_at,
                    "meta": self.serialize_json(session.metadata),
                },
            )
        return session

    def get(self, session_id: str) -> Optional[MetaMeetingSession]:
        """Retrieve a meta meeting session by ID."""
        conn = self.get_connection()
        try:
            row = (
                conn.execute(
                    text(f"SELECT * FROM {self.TABLE} WHERE id = :id"),
                    {"id": session_id},
                )
                .mappings()
                .first()
            )
            if not row:
                return None
            return self._row_to_model(dict(row))
        finally:
            conn.close()

    def update(self, session: MetaMeetingSession) -> None:
        """Full update of a meta meeting session."""
        with self.transaction() as conn:
            conn.execute(
                text(
                    f"""
                    UPDATE {self.TABLE} SET
                        status = :status,
                        scope_snapshot = :snapshot,
                        digest_ids = :digests,
                        digest_count = :dcount,
                        agenda = :agenda,
                        minutes_md = :minutes,
                        action_items = :actions,
                        decisions = :decisions,
                        round_count = :rounds,
                        writeback_receipts = :receipts,
                        writeback_summary = :wb_summary,
                        prepared_at = :prepared,
                        started_at = :started,
                        closed_at = :closed,
                        archived_at = :archived,
                        metadata = :meta
                    WHERE id = :id
                """
                ),
                {
                    "id": session.id,
                    "status": session.status.value,
                    "snapshot": self.serialize_json(session.scope_snapshot),
                    "digests": self.serialize_json(session.digest_ids),
                    "dcount": session.digest_count,
                    "agenda": self.serialize_json(session.agenda),
                    "minutes": session.minutes_md,
                    "actions": self.serialize_json(session.action_items),
                    "decisions": self.serialize_json(session.decisions),
                    "rounds": session.round_count,
                    "receipts": self.serialize_json(session.writeback_receipts),
                    "wb_summary": self.serialize_json(session.writeback_summary),
                    "prepared": session.prepared_at,
                    "started": session.started_at,
                    "closed": session.closed_at,
                    "archived": session.archived_at,
                    "meta": self.serialize_json(session.metadata),
                },
            )

    def list_by_owner(
        self, owner_profile_id: str, status: Optional[str] = None, limit: int = 20
    ) -> List[MetaMeetingSession]:
        """List meta meeting sessions for an owner."""
        conn = self.get_connection()
        try:
            sql = f"SELECT * FROM {self.TABLE} WHERE owner_profile_id = :owner"
            params: Dict[str, Any] = {"owner": owner_profile_id}
            if status:
                sql += " AND status = :status"
                params["status"] = status
            sql += " ORDER BY created_at DESC LIMIT :limit"
            params["limit"] = limit
            rows = conn.execute(text(sql), params).mappings().all()
            return [self._row_to_model(dict(r)) for r in rows]
        finally:
            conn.close()

    def _row_to_model(self, row: Dict[str, Any]) -> MetaMeetingSession:
        """Convert DB row to MetaMeetingSession."""
        return MetaMeetingSession(
            id=row["id"],
            owner_profile_id=row["owner_profile_id"],
            status=MetaMeetingStatus(row["status"]),
            meta_scope_id=row.get("meta_scope_id"),
            scope_snapshot=self.deserialize_json(row.get("scope_snapshot", "{}")),
            digest_ids=self.deserialize_json(row.get("digest_ids", "[]")),
            digest_count=row.get("digest_count", 0),
            agenda=self.deserialize_json(row.get("agenda", "[]")),
            success_criteria=self.deserialize_json(row.get("success_criteria", "[]")),
            minutes_md=row.get("minutes_md", ""),
            action_items=self.deserialize_json(row.get("action_items", "[]")),
            decisions=self.deserialize_json(row.get("decisions", "[]")),
            round_count=row.get("round_count", 0),
            max_rounds=row.get("max_rounds", 5),
            writeback_receipts=self.deserialize_json(
                row.get("writeback_receipts", "[]")
            ),
            writeback_summary=self.deserialize_json(row.get("writeback_summary", "{}")),
            created_at=row.get("created_at", datetime.utcnow()),
            prepared_at=row.get("prepared_at"),
            started_at=row.get("started_at"),
            closed_at=row.get("closed_at"),
            archived_at=row.get("archived_at"),
            metadata=self.deserialize_json(row.get("metadata", "{}")),
        )
