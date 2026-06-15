"""
Meeting session store for governance session persistence.

PostgreSQL store for persisting MeetingSession lifecycle (start/end),
state snapshots, and links to decisions/traces/intents.
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

from sqlalchemy import text

from backend.app.models.meeting_decision import MeetingDecision
from backend.app.services.stores.meeting_session_projection import (
    is_active_session_fresh,
    row_to_meeting_decision,
    row_to_session,
    unresolved_decision_from_row,
)
from backend.app.services.stores.meeting_session_schema import (
    DECISIONS_INDEX_DDL,
    DECISIONS_TABLE_DDL,
    INDEX_DDL,
    MEETING_SESSION_ALTER_DDL,
    TABLE_DDL,
)
from backend.app.services.stores.postgres_base import PostgresStoreBase
from backend.app.models.meeting_session import MeetingSession, MeetingStatus

logger = logging.getLogger(__name__)

class MeetingSessionStore(PostgresStoreBase):
    """Store for MeetingSession persistence (Postgres)."""

    _table_ensured = False

    def __init__(self, db_role: str = "core"):
        super().__init__(db_role=db_role)
        if not MeetingSessionStore._table_ensured:
            self.ensure_table()
            MeetingSessionStore._table_ensured = True

    def ensure_table(self) -> None:
        """Create the meeting_sessions and meeting_decisions tables if they do not exist."""
        with self.transaction() as conn:
            conn.execute(text(TABLE_DDL))
            conn.execute(text(DECISIONS_TABLE_DDL))
            for alter in MEETING_SESSION_ALTER_DDL:
                conn.execute(text(alter))
            for idx in INDEX_DDL:
                conn.execute(text(idx))
            for idx in DECISIONS_INDEX_DDL:
                conn.execute(text(idx))
        logger.info("meeting_sessions + meeting_decisions tables ensured")

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
                        thread_id = :thread_id,
                        lens_id = :lens_id,
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
                    "thread_id": session.thread_id,
                    "lens_id": session.lens_id,
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

    def close_stale_active_sessions(
        self,
        workspace_id: str,
        *,
        project_id: Optional[str] = None,
        thread_id: Optional[str] = None,
        reason: str = "stale_replaced_by_compile",
        now: Optional[datetime] = None,
        limit: int = 100,
    ) -> int:
        """Abort active-but-stale sessions so new compile intake starts cleanly."""
        effective_now = now or datetime.now(timezone.utc)
        closed = 0
        sessions = self.list_by_workspace(
            workspace_id,
            project_id=project_id,
            limit=limit,
            offset=0,
        )
        for session in sessions:
            if not session.is_active:
                continue
            if project_id and session.project_id != project_id:
                continue
            if thread_id and session.thread_id != thread_id:
                continue
            if is_active_session_fresh(session, now=effective_now):
                continue
            session.abort(reason=reason)
            self.update(session)
            closed += 1
        if closed:
            logger.info(
                "Closed %d stale active meeting sessions in workspace %s",
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
            rows = conn.execute(
                text(query.replace("LIMIT 1", "LIMIT 10")),
                params,
            ).fetchall()
            if not rows:
                return None
            for row in rows:
                session = self._row_to_session(row)
                if is_active_session_fresh(session):
                    return session
            return None

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

    def _row_to_session(self, row) -> MeetingSession:
        """Convert a database row to a MeetingSession."""
        return row_to_session(row, deserialize_json=self.deserialize_json)

    # ============== Decisions CRUD ==============

    def save_decisions(self, decisions) -> int:
        """Bulk-insert MeetingDecision records. Returns count saved."""
        if not decisions:
            return 0
        with self.transaction() as conn:
            for d in decisions:
                conn.execute(
                    text(
                        """
                        INSERT INTO meeting_decisions (
                            id, session_id, workspace_id, category,
                            content, status, resolved_by_task_id,
                            source_action_item, created_at
                        ) VALUES (
                            :id, :session_id, :workspace_id, :category,
                            :content, :status, :resolved_by_task_id,
                            :source_action_item, :created_at
                        ) ON CONFLICT (id) DO NOTHING
                    """
                    ),
                    {
                        "id": d.id,
                        "session_id": d.session_id,
                        "workspace_id": d.workspace_id,
                        "category": d.category,
                        "content": d.content,
                        "status": d.status,
                        "resolved_by_task_id": d.resolved_by_task_id,
                        "source_action_item": self.serialize_json(d.source_action_item),
                        "created_at": d.created_at,
                    },
                )
        logger.info("Saved %d meeting decisions", len(decisions))
        return len(decisions)

    def get_unresolved_decisions(
        self, workspace_id: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get unresolved decisions for a workspace."""
        query = text(
            """
            SELECT id, session_id, workspace_id, category,
                   content, status, resolved_by_task_id, created_at
            FROM meeting_decisions
            WHERE workspace_id = :workspace_id
              AND status NOT IN ('resolved', 'cancelled')
            ORDER BY created_at DESC
            LIMIT :limit
        """
        )
        with self.get_connection() as conn:
            rows = conn.execute(
                query, {"workspace_id": workspace_id, "limit": limit}
            ).fetchall()
            return [unresolved_decision_from_row(r) for r in rows]

    def list_decisions_by_session(self, session_id: str) -> List[MeetingDecision]:
        """List structured meeting decisions for a session, oldest first."""
        query = text(
            """
            SELECT id, session_id, workspace_id, category, content, status,
                   resolved_by_task_id, source_action_item, created_at
            FROM meeting_decisions
            WHERE session_id = :session_id
            ORDER BY created_at ASC
            """
        )
        with self.get_connection() as conn:
            rows = conn.execute(query, {"session_id": session_id}).fetchall()
            return [self._row_to_meeting_decision(row) for row in rows]

    def _row_to_meeting_decision(self, row: Any) -> MeetingDecision:
        return row_to_meeting_decision(row, deserialize_json=self.deserialize_json)
