"""
Meeting session store for governance session persistence.

PostgreSQL store for persisting MeetingSession lifecycle (start/end),
state snapshots, and links to decisions/traces/intents.
"""

import logging
import os
import threading
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any

from sqlalchemy import text

from backend.app.models.meeting_decision import MeetingDecision
from backend.app.services.stores.postgres_base import PostgresStoreBase
from backend.app.models.meeting_session import MeetingSession, MeetingStatus

logger = logging.getLogger(__name__)

_DEFAULT_ACTIVE_SESSION_WINDOW_MINUTES = 24 * 60


def _active_session_window_minutes() -> int:
    raw = str(
        os.getenv(
            "MINDSCAPE_ACTIVE_MEETING_WINDOW_MINUTES",
            _DEFAULT_ACTIVE_SESSION_WINDOW_MINUTES,
        )
    ).strip()
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return _DEFAULT_ACTIVE_SESSION_WINDOW_MINUTES
    return value if value > 0 else _DEFAULT_ACTIVE_SESSION_WINDOW_MINUTES


def _coerce_datetime(raw: Any) -> Optional[datetime]:
    if raw in (None, ""):
        return None
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    if isinstance(raw, str):
        normalized = raw.strip()
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def _session_last_activity_at(session: MeetingSession) -> Optional[datetime]:
    metadata = getattr(session, "metadata", None) or {}
    candidates = [
        _coerce_datetime(getattr(session, "started_at", None)),
        _coerce_datetime(metadata.get("last_round_updated_at")),
        _coerce_datetime(metadata.get("pipeline_stage_updated_at")),
    ]
    valid = [candidate for candidate in candidates if candidate]
    if not valid:
        return None
    return max(valid)


def is_active_session_fresh(
    session: MeetingSession,
    *,
    now: Optional[datetime] = None,
    window: Optional[timedelta] = None,
) -> bool:
    if not session or not session.is_active:
        return False
    effective_now = now or datetime.now(timezone.utc)
    effective_window = window or timedelta(minutes=_active_session_window_minutes())
    last_activity_at = _session_last_activity_at(session)
    if last_activity_at is None:
        return False
    return last_activity_at >= (effective_now - effective_window)


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

ALTER_DDL_BY_COLUMN = [
    ("project_id", "ALTER TABLE meeting_sessions ADD COLUMN IF NOT EXISTS project_id TEXT"),
    ("lens_id", "ALTER TABLE meeting_sessions ADD COLUMN IF NOT EXISTS lens_id TEXT"),
    (
        "status",
        "ALTER TABLE meeting_sessions ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'planned'",
    ),
    (
        "meeting_type",
        "ALTER TABLE meeting_sessions ADD COLUMN IF NOT EXISTS meeting_type TEXT NOT NULL DEFAULT 'general'",
    ),
    (
        "agenda",
        "ALTER TABLE meeting_sessions ADD COLUMN IF NOT EXISTS agenda JSONB DEFAULT '[]'::jsonb",
    ),
    (
        "success_criteria",
        "ALTER TABLE meeting_sessions ADD COLUMN IF NOT EXISTS success_criteria JSONB DEFAULT '[]'::jsonb",
    ),
    (
        "round_count",
        "ALTER TABLE meeting_sessions ADD COLUMN IF NOT EXISTS round_count INTEGER DEFAULT 0",
    ),
    (
        "max_rounds",
        "ALTER TABLE meeting_sessions ADD COLUMN IF NOT EXISTS max_rounds INTEGER DEFAULT 5",
    ),
    (
        "action_items",
        "ALTER TABLE meeting_sessions ADD COLUMN IF NOT EXISTS action_items JSONB DEFAULT '[]'::jsonb",
    ),
    (
        "minutes_md",
        "ALTER TABLE meeting_sessions ADD COLUMN IF NOT EXISTS minutes_md TEXT DEFAULT ''",
    ),
]


class MeetingSessionStore(PostgresStoreBase):
    """Store for MeetingSession persistence (Postgres)."""

    _table_ensured = False
    _ensure_lock = threading.Lock()

    def __init__(self, db_role: str = "core"):
        super().__init__(db_role=db_role)
        self.ensure_table()

    def _existing_columns(self, conn) -> set[str]:
        rows = conn.execute(
            text(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'meeting_sessions'
                """
            )
        ).fetchall()
        columns: set[str] = set()
        for row in rows:
            if hasattr(row, "column_name"):
                columns.add(str(row.column_name))
                continue
            if isinstance(row, dict):
                column_name = row.get("column_name")
                if column_name is not None:
                    columns.add(str(column_name))
                    continue
            columns.add(str(row[0]))
        return columns

    def ensure_table(self) -> None:
        """Create the meeting_sessions and meeting_decisions tables if they do not exist."""
        if MeetingSessionStore._table_ensured:
            return
        with MeetingSessionStore._ensure_lock:
            if MeetingSessionStore._table_ensured:
                return
            with self.transaction() as conn:
                conn.execute(text(TABLE_DDL))
                conn.execute(text(DECISIONS_TABLE_DDL))
                existing_columns = self._existing_columns(conn)
                for column_name, alter in ALTER_DDL_BY_COLUMN:
                    if column_name not in existing_columns:
                        conn.execute(text(alter))
                for idx in INDEX_DDL:
                    conn.execute(text(idx))
                for idx in DECISIONS_INDEX_DDL:
                    conn.execute(text(idx))
            MeetingSessionStore._table_ensured = True
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
        Only considers sessions with actionable statuses (planned/active/closing)
        and recent activity within the active-session freshness window.
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
                ORDER BY started_at DESC
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
                ORDER BY started_at DESC
            """
            params = {"workspace_id": workspace_id, "project_id": project_id}
        elif thread_id:
            query = f"""
                SELECT * FROM meeting_sessions
                WHERE workspace_id = :workspace_id
                  AND thread_id = :thread_id
                  AND ended_at IS NULL
                  {status_clause}
                ORDER BY started_at DESC
            """
            params = {"workspace_id": workspace_id, "thread_id": thread_id}
        else:
            query = f"""
                SELECT * FROM meeting_sessions
                WHERE workspace_id = :workspace_id
                  AND ended_at IS NULL
                  {status_clause}
                ORDER BY started_at DESC
            """
            params = {"workspace_id": workspace_id}

        with self.get_connection() as conn:
            rows = conn.execute(text(query), params).fetchall()
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

    def update_decision(self, decision: MeetingDecision) -> MeetingDecision:
        """Persist updates to a structured meeting decision."""
        with self.transaction() as conn:
            conn.execute(
                text(
                    """
                    UPDATE meeting_decisions
                    SET category = :category,
                        content = :content,
                        status = :status,
                        resolved_by_task_id = :resolved_by_task_id,
                        source_action_item = :source_action_item
                    WHERE id = :id
                    """
                ),
                {
                    "id": decision.id,
                    "category": decision.category,
                    "content": decision.content,
                    "status": decision.status,
                    "resolved_by_task_id": decision.resolved_by_task_id,
                    "source_action_item": self.serialize_json(
                        decision.source_action_item
                    ),
                },
            )
        return decision

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
