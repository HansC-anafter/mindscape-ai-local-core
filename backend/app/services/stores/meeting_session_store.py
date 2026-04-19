"""
Meeting session store for governance session persistence.

PostgreSQL store for persisting MeetingSession lifecycle (start/end),
state snapshots, and links to decisions/traces/intents.
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from backend.app.models.meeting_decision import MeetingDecision
from backend.app.services.stores.postgres_base import PostgresStoreBase
from backend.app.models.meeting_session import MeetingSession, MeetingStatus

logger = logging.getLogger(__name__)

DEFAULT_ACTIVE_SESSION_FRESHNESS = timedelta(minutes=30)
DEFAULT_PLANNED_SESSION_FRESHNESS = timedelta(minutes=15)
SESSION_ACTIVITY_METADATA_KEYS = (
    "last_round_updated_at",
    "pipeline_stage_updated_at",
    "dispatch_updated_at",
    "updated_at",
)


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

DECISIONS_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS meeting_decisions (
    id                  TEXT PRIMARY KEY,
    session_id          TEXT NOT NULL,
    workspace_id        TEXT NOT NULL,
    category            VARCHAR(32) NOT NULL DEFAULT 'action',
    content             TEXT NOT NULL,
    status              VARCHAR(32) DEFAULT 'pending',
    resolved_by_task_id TEXT,
    source_action_item  JSONB DEFAULT '{}',
    created_at          TIMESTAMPTZ DEFAULT NOW()
);
"""

DECISIONS_INDEX_DDL = [
    "CREATE INDEX IF NOT EXISTS idx_decisions_session ON meeting_decisions(session_id)",
    "CREATE INDEX IF NOT EXISTS idx_decisions_ws_status ON meeting_decisions(workspace_id, status)",
]

INDEX_DDL = [
    "CREATE INDEX IF NOT EXISTS idx_meeting_sessions_ws_thread ON meeting_sessions(workspace_id, thread_id)",
    "CREATE INDEX IF NOT EXISTS idx_meeting_sessions_ws_project ON meeting_sessions(workspace_id, project_id)",
    "CREATE INDEX IF NOT EXISTS idx_meeting_sessions_active ON meeting_sessions(workspace_id, ended_at)",
]


def _coerce_activity_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value))
        except Exception:
            return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def is_active_session_fresh(
    session: MeetingSession,
    *,
    now: Optional[datetime] = None,
    active_ttl: timedelta = DEFAULT_ACTIVE_SESSION_FRESHNESS,
    planned_ttl: timedelta = DEFAULT_PLANNED_SESSION_FRESHNESS,
) -> bool:
    if session is None or session.ended_at is not None:
        return False

    effective_now = now or datetime.now(timezone.utc)
    if effective_now.tzinfo is None:
        effective_now = effective_now.replace(tzinfo=timezone.utc)
    else:
        effective_now = effective_now.astimezone(timezone.utc)

    metadata = session.metadata or {}
    activity_points: List[datetime] = []

    started_at = _coerce_activity_datetime(session.started_at)
    if started_at is not None:
        activity_points.append(started_at)

    for key in SESSION_ACTIVITY_METADATA_KEYS:
        activity_dt = _coerce_activity_datetime(metadata.get(key))
        if activity_dt is not None:
            activity_points.append(activity_dt)

    if not activity_points:
        return False

    last_activity = max(activity_points)
    ttl = (
        planned_ttl
        if session.status == MeetingStatus.PLANNED
        else active_ttl
    )
    return last_activity >= (effective_now - ttl)


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
            conn.execute(text(DECISIONS_TABLE_DDL))
            for alter in alter_ddls:
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
            return [
                {
                    "id": r[0],
                    "session_id": r[1],
                    "workspace_id": r[2],
                    "category": r[3],
                    "content": r[4],
                    "status": r[5],
                    "resolved_by_task_id": r[6],
                    "created_at": r[7].isoformat() if r[7] else None,
                }
                for r in rows
            ]

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
        data = row._mapping if hasattr(row, "_mapping") else row
        created_at = data["created_at"]
        if created_at and not isinstance(created_at, datetime):
            created_at = datetime.fromisoformat(str(created_at))
        return MeetingDecision(
            id=data["id"],
            session_id=data["session_id"],
            workspace_id=data["workspace_id"],
            category=data["category"],
            content=data["content"],
            status=data.get("status") or "pending",
            resolved_by_task_id=data.get("resolved_by_task_id"),
            source_action_item=self.deserialize_json(
                data.get("source_action_item"),
                default={},
            ),
            created_at=created_at,
        )
