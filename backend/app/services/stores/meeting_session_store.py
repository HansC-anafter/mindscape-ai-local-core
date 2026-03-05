"""
Meeting session store for governance session persistence.

PostgreSQL store for persisting MeetingSession lifecycle (start/end),
state snapshots, and links to decisions/traces/intents.
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

from sqlalchemy import text

from backend.app.services.stores.postgres_base import PostgresStoreBase
from backend.app.models.meeting_session import MeetingSession, MeetingStatus

logger = logging.getLogger(__name__)


TABLE_DDL = """
CREATE TABLE IF NOT EXISTS meeting_sessions (
    id               TEXT PRIMARY KEY,
    workspace_id     TEXT NOT NULL,
    project_id       TEXT,
    thread_id        TEXT,
    lens_id          TEXT,
    started_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at         TIMESTAMPTZ,
    status           TEXT NOT NULL DEFAULT 'planned',
    meeting_type     TEXT NOT NULL DEFAULT 'general',
    agenda           JSONB DEFAULT '[]',
    success_criteria JSONB DEFAULT '[]',
    round_count      INTEGER DEFAULT 0,
    max_rounds       INTEGER DEFAULT 5,
    action_items     JSONB DEFAULT '[]',
    minutes_md       TEXT DEFAULT '',
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
    "CREATE INDEX IF NOT EXISTS idx_meeting_sessions_ws_project ON meeting_sessions(workspace_id, project_id)",
    "CREATE INDEX IF NOT EXISTS idx_meeting_sessions_active ON meeting_sessions(workspace_id, ended_at)",
]


class MeetingSessionStore(PostgresStoreBase):
    """Store for MeetingSession persistence (Postgres)."""

    _table_ensured = False

    def __init__(self, db_role: str = "core"):
        super().__init__(db_role=db_role)
        if not MeetingSessionStore._table_ensured:
            self.ensure_table()
            MeetingSessionStore._table_ensured = True

    def ensure_table(self) -> None:
        """Create the meeting_sessions table if it does not exist."""
        alter_ddls = [
            "ALTER TABLE meeting_sessions ADD COLUMN IF NOT EXISTS project_id TEXT",
            "ALTER TABLE meeting_sessions ADD COLUMN IF NOT EXISTS lens_id TEXT",
            "ALTER TABLE meeting_sessions ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'planned'",
            "ALTER TABLE meeting_sessions ADD COLUMN IF NOT EXISTS meeting_type TEXT NOT NULL DEFAULT 'general'",
            "ALTER TABLE meeting_sessions ADD COLUMN IF NOT EXISTS agenda JSONB DEFAULT '[]'::jsonb",
            "ALTER TABLE meeting_sessions ADD COLUMN IF NOT EXISTS success_criteria JSONB DEFAULT '[]'::jsonb",
            "ALTER TABLE meeting_sessions ADD COLUMN IF NOT EXISTS round_count INTEGER DEFAULT 0",
            "ALTER TABLE meeting_sessions ADD COLUMN IF NOT EXISTS max_rounds INTEGER DEFAULT 5",
            "ALTER TABLE meeting_sessions ADD COLUMN IF NOT EXISTS action_items JSONB DEFAULT '[]'::jsonb",
            "ALTER TABLE meeting_sessions ADD COLUMN IF NOT EXISTS minutes_md TEXT DEFAULT ''",
        ]
        with self.transaction() as conn:
            conn.execute(text(TABLE_DDL))
            for alter in alter_ddls:
                conn.execute(text(alter))
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
                        id, workspace_id, project_id, thread_id, lens_id,
                        started_at, ended_at,
                        status, meeting_type, agenda, success_criteria,
                        round_count, max_rounds, action_items, minutes_md,
                        state_before, state_after, decisions, traces,
                        intents_patched, metadata
                    ) VALUES (
                        :id, :workspace_id, :project_id, :thread_id, :lens_id,
                        :started_at, :ended_at,
                        :status, :meeting_type, :agenda, :success_criteria,
                        :round_count, :max_rounds, :action_items, :minutes_md,
                        :state_before, :state_after, :decisions, :traces,
                        :intents_patched, :metadata
                    )
                """
                ),
                {
                    "id": session.id,
                    "workspace_id": session.workspace_id,
                    "project_id": session.project_id,
                    "thread_id": session.thread_id,
                    "lens_id": session.lens_id,
                    "started_at": session.started_at,
                    "ended_at": session.ended_at,
                    "status": (
                        session.status.value
                        if hasattr(session.status, "value")
                        else str(session.status)
                    ),
                    "meeting_type": session.meeting_type,
                    "agenda": self.serialize_json(session.agenda),
                    "success_criteria": self.serialize_json(session.success_criteria),
                    "round_count": session.round_count,
                    "max_rounds": session.max_rounds,
                    "action_items": self.serialize_json(session.action_items),
                    "minutes_md": session.minutes_md,
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
                        project_id = :project_id,
                        ended_at = :ended_at,
                        status = :status,
                        meeting_type = :meeting_type,
                        agenda = :agenda,
                        success_criteria = :success_criteria,
                        round_count = :round_count,
                        max_rounds = :max_rounds,
                        action_items = :action_items,
                        minutes_md = :minutes_md,
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
                    "project_id": session.project_id,
                    "ended_at": session.ended_at,
                    "status": (
                        session.status.value
                        if hasattr(session.status, "value")
                        else str(session.status)
                    ),
                    "meeting_type": session.meeting_type,
                    "agenda": self.serialize_json(session.agenda),
                    "success_criteria": self.serialize_json(session.success_criteria),
                    "round_count": session.round_count,
                    "max_rounds": session.max_rounds,
                    "action_items": self.serialize_json(session.action_items),
                    "minutes_md": session.minutes_md,
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
        session.close(state_after=state_after)
        return self.update(session)

    def close_orphaned_sessions(
        self,
        workspace_id: str,
        max_age_hours: int = 24,
    ) -> int:
        """Close sessions that have been active longer than max_age_hours.

        Returns the number of sessions closed.
        """
        query = text(
            """
            UPDATE meeting_sessions
            SET ended_at = now(),
                status = 'aborted',
                metadata = jsonb_set(
                    COALESCE(metadata, '{}'::jsonb),
                    '{abort_reason}',
                    '"orphan_cleanup"'::jsonb
                )
            WHERE workspace_id = :workspace_id
              AND ended_at IS NULL
              AND started_at < now() - make_interval(hours => :max_age_hours)
        """
        )
        with self.transaction() as conn:
            result = conn.execute(
                query,
                {"workspace_id": workspace_id, "max_age_hours": max_age_hours},
            )
            closed = result.rowcount
            if closed:
                logger.info(
                    "Closed %d orphaned meeting sessions in workspace %s",
                    closed,
                    workspace_id,
                )
            return closed

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
        project_id: Optional[str] = None,
        thread_id: Optional[str] = None,
    ) -> Optional[MeetingSession]:
        """Get the currently active (un-ended) session for a workspace/thread.

        Uses the idx_meeting_sessions_active index (workspace_id, ended_at).
        Only considers sessions with actionable statuses (planned/active/closing).
        """
        # Common status filter to exclude failed/aborted/closed sessions
        status_clause = "AND status IN ('planned', 'active', 'closing')"

        if project_id and thread_id:
            query = f"""
                SELECT * FROM meeting_sessions
                WHERE workspace_id = :workspace_id
                  AND project_id = :project_id
                  AND thread_id = :thread_id
                  AND ended_at IS NULL
                  {status_clause}
                ORDER BY started_at DESC LIMIT 1
            """
            params = {
                "workspace_id": workspace_id,
                "project_id": project_id,
                "thread_id": thread_id,
            }
        elif project_id:
            query = f"""
                SELECT * FROM meeting_sessions
                WHERE workspace_id = :workspace_id
                  AND project_id = :project_id
                  AND ended_at IS NULL
                  {status_clause}
                ORDER BY started_at DESC LIMIT 1
            """
            params = {"workspace_id": workspace_id, "project_id": project_id}
        elif thread_id:
            query = f"""
                SELECT * FROM meeting_sessions
                WHERE workspace_id = :workspace_id
                  AND thread_id = :thread_id
                  AND ended_at IS NULL
                  {status_clause}
                ORDER BY started_at DESC LIMIT 1
            """
            params = {"workspace_id": workspace_id, "thread_id": thread_id}
        else:
            query = f"""
                SELECT * FROM meeting_sessions
                WHERE workspace_id = :workspace_id
                  AND ended_at IS NULL
                  {status_clause}
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
        project_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[MeetingSession]:
        """List meeting sessions for a workspace, newest first."""
        base_query = """
            SELECT * FROM meeting_sessions
            WHERE workspace_id = :workspace_id
        """
        params: Dict[str, Any] = {
            "workspace_id": workspace_id,
            "limit": limit,
            "offset": offset,
        }
        if project_id:
            base_query += " AND project_id = :project_id"
            params["project_id"] = project_id
        base_query += " ORDER BY started_at DESC LIMIT :limit OFFSET :offset"
        with self.get_connection() as conn:
            rows = conn.execute(
                text(base_query),
                params,
            ).fetchall()
            return [self._row_to_session(r) for r in rows]

    # ============== Internal ==============

    @staticmethod
    def _row_data(row) -> Dict[str, Any]:
        return row._mapping if hasattr(row, "_mapping") else row

    def _row_to_session(self, row) -> MeetingSession:
        """Convert a database row to a MeetingSession."""
        data = self._row_data(row)
        status_raw = data.get("status", MeetingStatus.PLANNED.value)
        try:
            status = MeetingStatus(status_raw)
        except Exception:
            status = MeetingStatus.PLANNED

        started_at = data["started_at"]
        if not isinstance(started_at, datetime):
            started_at = datetime.fromisoformat(str(started_at))

        ended_at = data.get("ended_at")
        if ended_at and not isinstance(ended_at, datetime):
            ended_at = datetime.fromisoformat(str(ended_at))

        return MeetingSession(
            id=data["id"],
            workspace_id=data["workspace_id"],
            project_id=data.get("project_id"),
            thread_id=data.get("thread_id"),
            lens_id=data.get("lens_id"),
            started_at=started_at,
            ended_at=ended_at,
            status=status,
            meeting_type=data.get("meeting_type", "general"),
            agenda=self.deserialize_json(data.get("agenda"), []),
            success_criteria=self.deserialize_json(data.get("success_criteria"), []),
            round_count=data.get("round_count", 0) or 0,
            max_rounds=data.get("max_rounds", 5) or 5,
            action_items=self.deserialize_json(data.get("action_items"), []),
            minutes_md=data.get("minutes_md", "") or "",
            state_before=self.deserialize_json(data.get("state_before"), {}),
            state_after=self.deserialize_json(data.get("state_after"), {}),
            decisions=self.deserialize_json(data.get("decisions"), []),
            traces=self.deserialize_json(data.get("traces"), []),
            intents_patched=self.deserialize_json(data.get("intents_patched"), []),
            metadata=self.deserialize_json(data.get("metadata"), {}),
        )
