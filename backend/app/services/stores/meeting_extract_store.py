"""
MeetingExtract store for L2 Bridge structured meeting outputs.

PostgreSQL store for persisting MeetingExtract and MeetingExtractItem,
providing typed X_t inputs for L3 Progress and Violation scoring.
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

from sqlalchemy import text

from backend.app.services.stores.postgres_base import PostgresStoreBase
from backend.app.models.meeting_extract import (
    MeetingExtract,
    MeetingExtractItem,
    ExtractType,
)

logger = logging.getLogger(__name__)


TABLE_DDL = """
CREATE TABLE IF NOT EXISTS meeting_extracts (
    id                 TEXT PRIMARY KEY,
    meeting_session_id TEXT NOT NULL,
    state_snapshot     JSONB DEFAULT '{}',
    goal_set_id        TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata           JSONB DEFAULT '{}'
);
"""

ITEMS_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS meeting_extract_items (
    id                 TEXT PRIMARY KEY,
    meeting_session_id TEXT NOT NULL,
    extract_id         TEXT NOT NULL REFERENCES meeting_extracts(id) ON DELETE CASCADE,
    extract_type       TEXT NOT NULL,
    content            TEXT NOT NULL,
    source_event_ids   JSONB DEFAULT '[]',
    evidence_refs      JSONB DEFAULT '[]',
    goal_clause_ids    JSONB DEFAULT '[]',
    confidence         FLOAT DEFAULT 0.0,
    agent_id           TEXT,
    round_number       INTEGER,
    embedding          JSONB,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata           JSONB DEFAULT '{}'
);
"""

INDEX_DDL = [
    "CREATE INDEX IF NOT EXISTS idx_meeting_extracts_session ON meeting_extracts(meeting_session_id)",
    "CREATE INDEX IF NOT EXISTS idx_meeting_extract_items_extract ON meeting_extract_items(extract_id)",
]


class MeetingExtractStore(PostgresStoreBase):
    """Store for MeetingExtract + items persistence (Postgres)."""

    _table_ensured = False

    def __init__(self, db_role: str = "core"):
        super().__init__(db_role=db_role)
        if not MeetingExtractStore._table_ensured:
            self.ensure_table()
            MeetingExtractStore._table_ensured = True

    def ensure_table(self) -> None:
        """Create tables if they do not exist."""
        with self.transaction() as conn:
            conn.execute(text(TABLE_DDL))
            conn.execute(text(ITEMS_TABLE_DDL))
            for idx in INDEX_DDL:
                conn.execute(text(idx))
        logger.info("meeting_extracts + meeting_extract_items tables ensured")

    # ============== Write ==============

    def create(self, extract: MeetingExtract) -> MeetingExtract:
        """Insert a MeetingExtract and its items."""
        with self.transaction() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO meeting_extracts (id, meeting_session_id,
                        state_snapshot, goal_set_id, created_at, metadata)
                    VALUES (:id, :meeting_session_id,
                        :state_snapshot, :goal_set_id, :created_at, :metadata)
                """
                ),
                {
                    "id": extract.id,
                    "meeting_session_id": extract.meeting_session_id,
                    "state_snapshot": self.serialize_json(extract.state_snapshot),
                    "goal_set_id": extract.goal_set_id,
                    "created_at": extract.created_at,
                    "metadata": self.serialize_json(extract.metadata),
                },
            )
            for item in extract.items:
                conn.execute(
                    text(
                        """
                        INSERT INTO meeting_extract_items (id, meeting_session_id,
                            extract_id, extract_type, content,
                            source_event_ids, evidence_refs,
                            goal_clause_ids, confidence,
                            agent_id, round_number, embedding,
                            created_at, metadata)
                        VALUES (:id, :meeting_session_id,
                            :extract_id, :extract_type, :content,
                            :source_event_ids, :evidence_refs,
                            :goal_clause_ids, :confidence,
                            :agent_id, :round_number, :embedding,
                            :created_at, :metadata)
                    """
                    ),
                    {
                        "id": item.id,
                        "meeting_session_id": item.meeting_session_id,
                        "extract_id": extract.id,
                        "extract_type": (
                            item.extract_type.value
                            if hasattr(item.extract_type, "value")
                            else str(item.extract_type)
                        ),
                        "content": item.content,
                        "source_event_ids": self.serialize_json(item.source_event_ids),
                        "evidence_refs": self.serialize_json(item.evidence_refs),
                        "goal_clause_ids": self.serialize_json(item.goal_clause_ids),
                        "confidence": item.confidence,
                        "agent_id": item.agent_id,
                        "round_number": item.round_number,
                        "embedding": self.serialize_json(item.embedding),
                        "created_at": item.created_at,
                        "metadata": self.serialize_json(item.metadata),
                    },
                )
        return extract

    # ============== Read ==============

    def get_by_id(self, extract_id: str) -> Optional[MeetingExtract]:
        """Get a MeetingExtract by ID with all items."""
        with self.get_connection() as conn:
            row = conn.execute(
                text("SELECT * FROM meeting_extracts WHERE id = :id"),
                {"id": extract_id},
            ).fetchone()
            if not row:
                return None
            return self._row_to_extract(conn, row)

    def get_by_session(self, meeting_session_id: str) -> Optional[MeetingExtract]:
        """Get the latest MeetingExtract for a session."""
        with self.get_connection() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT * FROM meeting_extracts
                    WHERE meeting_session_id = :sid
                    ORDER BY created_at DESC LIMIT 1
                """
                ),
                {"sid": meeting_session_id},
            ).fetchone()
            if not row:
                return None
            return self._row_to_extract(conn, row)

    # ============== Internal ==============

    def _row_to_extract(self, conn, row) -> MeetingExtract:
        """Convert a row + items to MeetingExtract."""
        data = row._mapping if hasattr(row, "_mapping") else row
        item_rows = conn.execute(
            text("SELECT * FROM meeting_extract_items WHERE extract_id = :eid"),
            {"eid": data["id"]},
        ).fetchall()

        items = []
        for ir in item_rows:
            id_ = ir._mapping if hasattr(ir, "_mapping") else ir
            et_raw = id_.get("extract_type", "decision")
            try:
                et = ExtractType(et_raw)
            except Exception:
                et = ExtractType.DECISION
            item_created = id_.get("created_at")
            if item_created and not isinstance(item_created, datetime):
                item_created = datetime.fromisoformat(str(item_created))
            items.append(
                MeetingExtractItem(
                    id=id_["id"],
                    meeting_session_id=id_["meeting_session_id"],
                    extract_type=et,
                    content=id_["content"],
                    embedding=self.deserialize_json(id_.get("embedding"), None),
                    source_event_ids=self.deserialize_json(
                        id_.get("source_event_ids"), []
                    ),
                    evidence_refs=self.deserialize_json(id_.get("evidence_refs"), []),
                    goal_clause_ids=self.deserialize_json(
                        id_.get("goal_clause_ids"), []
                    ),
                    confidence=id_.get("confidence", 0.0),
                    agent_id=id_.get("agent_id"),
                    round_number=id_.get("round_number"),
                    metadata=self.deserialize_json(id_.get("metadata"), {}),
                    created_at=item_created or datetime.now(),
                )
            )

        created_at = data["created_at"]
        if not isinstance(created_at, datetime):
            created_at = datetime.fromisoformat(str(created_at))

        return MeetingExtract(
            id=data["id"],
            meeting_session_id=data["meeting_session_id"],
            items=items,
            state_snapshot=self.deserialize_json(data.get("state_snapshot"), {}),
            goal_set_id=data.get("goal_set_id"),
            metadata=self.deserialize_json(data.get("metadata"), {}),
            created_at=created_at,
        )
