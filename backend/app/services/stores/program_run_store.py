"""
Postgres persistence for ProgramRun ledgers.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from sqlalchemy import text

from backend.app.models.program_run import ProgramRun, ProgramRunStatus
from backend.app.services.stores.postgres_base import PostgresStoreBase

logger = logging.getLogger(__name__)


TABLE_DDL = """
CREATE TABLE IF NOT EXISTS program_runs (
    id                 TEXT PRIMARY KEY,
    workspace_id       TEXT NOT NULL,
    meeting_session_id TEXT NOT NULL UNIQUE,
    project_id         TEXT,
    thread_id          TEXT,
    status             TEXT NOT NULL DEFAULT 'open',
    source             TEXT NOT NULL DEFAULT 'action_intent_bootstrap',
    scale              TEXT,
    program_spec       JSONB DEFAULT '{}'::jsonb,
    cursor_state       JSONB DEFAULT '{}'::jsonb,
    target_outputs     JSONB DEFAULT '[]'::jsonb,
    metadata           JSONB DEFAULT '{}'::jsonb,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    recorded_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

INDEX_DDL = [
    "CREATE INDEX IF NOT EXISTS idx_program_runs_ws_created ON program_runs(workspace_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_program_runs_project_created ON program_runs(workspace_id, project_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_program_runs_thread_created ON program_runs(workspace_id, thread_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_program_runs_status ON program_runs(status, updated_at DESC)",
]


class ProgramRunStore(PostgresStoreBase):
    """Persistent store for durable ProgramRun ledgers."""

    _table_ensured = False

    def __init__(self, db_role: str = "core"):
        super().__init__(db_role=db_role)
        if not ProgramRunStore._table_ensured:
            self.ensure_table()
            ProgramRunStore._table_ensured = True

    def ensure_table(self) -> None:
        alter_ddls = [
            "ALTER TABLE program_runs ADD COLUMN IF NOT EXISTS project_id TEXT",
            "ALTER TABLE program_runs ADD COLUMN IF NOT EXISTS thread_id TEXT",
            "ALTER TABLE program_runs ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'open'",
            "ALTER TABLE program_runs ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'action_intent_bootstrap'",
            "ALTER TABLE program_runs ADD COLUMN IF NOT EXISTS scale TEXT",
            "ALTER TABLE program_runs ADD COLUMN IF NOT EXISTS program_spec JSONB DEFAULT '{}'::jsonb",
            "ALTER TABLE program_runs ADD COLUMN IF NOT EXISTS cursor_state JSONB DEFAULT '{}'::jsonb",
            "ALTER TABLE program_runs ADD COLUMN IF NOT EXISTS target_outputs JSONB DEFAULT '[]'::jsonb",
            "ALTER TABLE program_runs ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'::jsonb",
            "ALTER TABLE program_runs ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now()",
            "ALTER TABLE program_runs ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now()",
            "ALTER TABLE program_runs ADD COLUMN IF NOT EXISTS recorded_at TIMESTAMPTZ NOT NULL DEFAULT now()",
        ]
        with self.transaction() as conn:
            conn.execute(text(TABLE_DDL))
            for alter in alter_ddls:
                conn.execute(text(alter))
            for idx in INDEX_DDL:
                conn.execute(text(idx))
        logger.info("program_runs table ensured")

    def create(self, program_run: ProgramRun) -> ProgramRun:
        with self.transaction() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO program_runs (
                        id, workspace_id, meeting_session_id, project_id, thread_id,
                        status, source, scale, program_spec, cursor_state,
                        target_outputs, metadata, created_at, updated_at, recorded_at
                    ) VALUES (
                        :id, :workspace_id, :meeting_session_id, :project_id, :thread_id,
                        :status, :source, :scale, :program_spec, :cursor_state,
                        :target_outputs, :metadata, :created_at, :updated_at, :recorded_at
                    )
                    """
                ),
                self._program_run_params(program_run),
            )
        return program_run

    def upsert_for_session(self, program_run: ProgramRun) -> ProgramRun:
        existing = self.get_by_session_id(program_run.meeting_session_id)
        created_at = existing.created_at if existing else program_run.created_at
        program_run.created_at = created_at
        program_run.updated_at = program_run.recorded_at
        with self.transaction() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO program_runs (
                        id, workspace_id, meeting_session_id, project_id, thread_id,
                        status, source, scale, program_spec, cursor_state,
                        target_outputs, metadata, created_at, updated_at, recorded_at
                    ) VALUES (
                        :id, :workspace_id, :meeting_session_id, :project_id, :thread_id,
                        :status, :source, :scale, :program_spec, :cursor_state,
                        :target_outputs, :metadata, :created_at, :updated_at, :recorded_at
                    )
                    ON CONFLICT (meeting_session_id) DO UPDATE SET
                        workspace_id = EXCLUDED.workspace_id,
                        project_id = EXCLUDED.project_id,
                        thread_id = EXCLUDED.thread_id,
                        status = EXCLUDED.status,
                        source = EXCLUDED.source,
                        scale = EXCLUDED.scale,
                        program_spec = EXCLUDED.program_spec,
                        cursor_state = EXCLUDED.cursor_state,
                        target_outputs = EXCLUDED.target_outputs,
                        metadata = EXCLUDED.metadata,
                        updated_at = EXCLUDED.updated_at,
                        recorded_at = EXCLUDED.recorded_at
                    """
                ),
                self._program_run_params(program_run),
            )
        return self.get_by_session_id(program_run.meeting_session_id) or program_run

    def get_by_id(self, program_run_id: str) -> Optional[ProgramRun]:
        with self.get_connection() as conn:
            row = conn.execute(
                text("SELECT * FROM program_runs WHERE id = :id"),
                {"id": program_run_id},
            ).fetchone()
        if not row:
            return None
        return self._row_to_program_run(row)

    def get_by_session_id(self, meeting_session_id: str) -> Optional[ProgramRun]:
        with self.get_connection() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT * FROM program_runs
                    WHERE meeting_session_id = :meeting_session_id
                    """
                ),
                {"meeting_session_id": meeting_session_id},
            ).fetchone()
        if not row:
            return None
        return self._row_to_program_run(row)

    def list_by_workspace(
        self,
        workspace_id: str,
        *,
        project_id: Optional[str] = None,
        meeting_session_id: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> List[ProgramRun]:
        query = """
            SELECT * FROM program_runs
            WHERE workspace_id = :workspace_id
        """
        params = {
            "workspace_id": workspace_id,
            "limit": limit,
            "offset": offset,
        }
        if project_id:
            query += " AND project_id = :project_id"
            params["project_id"] = project_id
        if meeting_session_id:
            query += " AND meeting_session_id = :meeting_session_id"
            params["meeting_session_id"] = meeting_session_id
        query += " ORDER BY created_at DESC LIMIT :limit OFFSET :offset"

        with self.get_connection() as conn:
            rows = conn.execute(text(query), params).fetchall()
        return [self._row_to_program_run(row) for row in rows]

    def _program_run_params(self, program_run: ProgramRun) -> dict:
        return {
            "id": program_run.id,
            "workspace_id": program_run.workspace_id,
            "meeting_session_id": program_run.meeting_session_id,
            "project_id": program_run.project_id,
            "thread_id": program_run.thread_id,
            "status": (
                program_run.status.value
                if hasattr(program_run.status, "value")
                else str(program_run.status)
            ),
            "source": program_run.source,
            "scale": program_run.scale,
            "program_spec": self.serialize_json(program_run.program_spec),
            "cursor_state": self.serialize_json(program_run.cursor_state),
            "target_outputs": self.serialize_json(program_run.target_outputs),
            "metadata": self.serialize_json(program_run.metadata),
            "created_at": program_run.created_at,
            "updated_at": program_run.updated_at,
            "recorded_at": program_run.recorded_at,
        }

    def _row_to_program_run(self, row) -> ProgramRun:
        status = row.status
        try:
            status = ProgramRunStatus(str(row.status))
        except ValueError:
            logger.warning("Unknown program run status %s; preserving raw value", row.status)
        return ProgramRun(
            id=row.id,
            workspace_id=row.workspace_id,
            meeting_session_id=row.meeting_session_id,
            project_id=row.project_id,
            thread_id=row.thread_id,
            status=status,
            source=row.source or "action_intent_bootstrap",
            scale=row.scale,
            program_spec=self.deserialize_json(row.program_spec, default={}),
            cursor_state=self.deserialize_json(row.cursor_state, default={}),
            target_outputs=self.deserialize_json(row.target_outputs, default=[]),
            metadata=self.deserialize_json(row.metadata, default={}),
            created_at=row.created_at,
            updated_at=row.updated_at,
            recorded_at=row.recorded_at,
        )
