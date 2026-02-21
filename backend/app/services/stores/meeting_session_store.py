"""
Meeting session store for governance session persistence.

PostgreSQL store for persisting MeetingSession lifecycle (start/end),
state snapshots, and links to decisions/traces/intents.
"""

import logging
import json as _json
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

from sqlalchemy import text

from app.services.stores.postgres_base import PostgresStoreBase
from app.models.meeting_session import MeetingSession

logger = logging.getLogger(__name__)


TABLE_DDL = """
CREATE TABLE IF NOT EXISTS meeting_sessions (
    id               TEXT PRIMARY KEY,
    workspace_id     TEXT NOT NULL,
    thread_id        TEXT,
    started_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at         TIMESTAMPTZ,
    state_before     JSONB DEFAULT '{}',
    state_after      JSONB DEFAULT '{}',
    decisions        JSONB DEFAULT '[]',
    traces           JSONB DEFAULT '[]',
    intents_patched  JSONB DEFAULT '[]',
    metadata         JSONB DEFAULT '{}'
);
"""

INDEX_DDL = [
    "CREATE INDEX IF NOT EXISTS idx_meeting_sessions_ws_thread ON meeting_sessions(workspace_id, thread_id)",
    "CREATE INDEX IF NOT EXISTS idx_meeting_sessions_active ON meeting_sessions(workspace_id, ended_at)",
]


class MeetingSessionStore(PostgresStoreBase):
    """Store for MeetingSession persistence (Postgres)."""

    def __init__(self, db_role: str = "core"):
        super().__init__(db_role=db_role)

    def ensure_table(self) -> None:
        """Create the meeting_sessions table if it does not exist."""
        with self.transaction() as conn:
            conn.execute(text(TABLE_DDL))
            for idx in INDEX_DDL:
                conn.execute(text(idx))
        logger.info("meeting_sessions table ensured")

    # ============== Write ==============

    def create(self, session: MeetingSession) -> MeetingSession:
        """Insert a new meeting session."""
        with self.transaction() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO meeting_sessions (
                        id, workspace_id, thread_id, started_at, ended_at,
                        state_before, state_after, decisions, traces,
                        intents_patched, metadata
                    ) VALUES (
                        :id, :workspace_id, :thread_id, :started_at, :ended_at,
                        :state_before, :state_after, :decisions, :traces,
                        :intents_patched, :metadata
                    )
                """
                ),
                {
                    "id": session.id,
                    "workspace_id": session.workspace_id,
                    "thread_id": session.thread_id,
                    "started_at": session.started_at,
                    "ended_at": session.ended_at,
                    "state_before": self.serialize_json(session.state_before),
                    "state_after": self.serialize_json(session.state_after),
                    "decisions": self.serialize_json(session.decisions),
                    "traces": self.serialize_json(session.traces),
                    "intents_patched": self.serialize_json(session.intents_patched),
                    "metadata": self.serialize_json(session.metadata),
                },
            )
        return session

    def update(self, session: MeetingSession) -> MeetingSession:
        """Update an existing meeting session."""
        with self.transaction() as conn:
            conn.execute(
                text(
                    """
                    UPDATE meeting_sessions SET
                        ended_at = :ended_at,
                        state_after = :state_after,
                        decisions = :decisions,
                        traces = :traces,
                        intents_patched = :intents_patched,
                        metadata = :metadata
                    WHERE id = :id
                """
                ),
                {
                    "id": session.id,
                    "ended_at": session.ended_at,
                    "state_after": self.serialize_json(session.state_after),
                    "decisions": self.serialize_json(session.decisions),
                    "traces": self.serialize_json(session.traces),
                    "intents_patched": self.serialize_json(session.intents_patched),
                    "metadata": self.serialize_json(session.metadata),
                },
            )
        return session

    def end_session(
        self,
        session_id: str,
        state_after: Optional[Dict[str, Any]] = None,
    ) -> Optional[MeetingSession]:
        """Mark a session as ended and optionally set state_after."""
        session = self.get_by_id(session_id)
        if not session:
            logger.warning(f"Cannot end session {session_id}: not found")
            return None
        session.end(state_after=state_after)
        return self.update(session)

    # ============== Read ==============

    def get_by_id(self, session_id: str) -> Optional[MeetingSession]:
        """Get a meeting session by ID."""
        with self.get_connection() as conn:
            row = conn.execute(
                text("SELECT * FROM meeting_sessions WHERE id = :id"),
                {"id": session_id},
            ).fetchone()
            if not row:
                return None
            return self._row_to_session(row)

    def get_active_session(
        self,
        workspace_id: str,
        thread_id: Optional[str] = None,
    ) -> Optional[MeetingSession]:
        """Get the currently active (un-ended) session for a workspace/thread.

        Uses the idx_meeting_sessions_active index (workspace_id, ended_at).
        """
        if thread_id:
            query = """
                SELECT * FROM meeting_sessions
                WHERE workspace_id = :workspace_id
                  AND thread_id = :thread_id
                  AND ended_at IS NULL
                ORDER BY started_at DESC LIMIT 1
            """
            params = {"workspace_id": workspace_id, "thread_id": thread_id}
        else:
            query = """
                SELECT * FROM meeting_sessions
                WHERE workspace_id = :workspace_id
                  AND ended_at IS NULL
                ORDER BY started_at DESC LIMIT 1
            """
            params = {"workspace_id": workspace_id}

        with self.get_connection() as conn:
            row = conn.execute(text(query), params).fetchone()
            if not row:
                return None
            return self._row_to_session(row)

    def list_by_workspace(
        self,
        workspace_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> List[MeetingSession]:
        """List meeting sessions for a workspace, newest first."""
        with self.get_connection() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT * FROM meeting_sessions
                    WHERE workspace_id = :workspace_id
                    ORDER BY started_at DESC
                    LIMIT :limit OFFSET :offset
                """
                ),
                {"workspace_id": workspace_id, "limit": limit, "offset": offset},
            ).fetchall()
            return [self._row_to_session(r) for r in rows]

    # ============== Internal ==============

    @staticmethod
    def _row_data(row) -> Dict[str, Any]:
        return row._mapping if hasattr(row, "_mapping") else row

    def _row_to_session(self, row) -> MeetingSession:
        """Convert a database row to a MeetingSession."""
        data = self._row_data(row)

        started_at = data["started_at"]
        if not isinstance(started_at, datetime):
            started_at = datetime.fromisoformat(str(started_at))

        ended_at = data.get("ended_at")
        if ended_at and not isinstance(ended_at, datetime):
            ended_at = datetime.fromisoformat(str(ended_at))

        return MeetingSession(
            id=data["id"],
            workspace_id=data["workspace_id"],
            thread_id=data.get("thread_id"),
            started_at=started_at,
            ended_at=ended_at,
            state_before=self.deserialize_json(data.get("state_before"), {}),
            state_after=self.deserialize_json(data.get("state_after"), {}),
            decisions=self.deserialize_json(data.get("decisions"), []),
            traces=self.deserialize_json(data.get("traces"), []),
            intents_patched=self.deserialize_json(data.get("intents_patched"), []),
            metadata=self.deserialize_json(data.get("metadata"), {}),
        )
