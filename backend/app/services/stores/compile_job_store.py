"""
Compile job store for handoff bundle compile lifecycle persistence.
"""

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from backend.app.models.compile_job import CompileJob, CompileJobStatus
from backend.app.services.stores.base import StoreNotFoundError
from backend.app.services.stores.postgres_base import PostgresStoreBase

logger = logging.getLogger(__name__)


TABLE_DDL = """
CREATE TABLE IF NOT EXISTS compile_jobs (
    id               TEXT PRIMARY KEY,
    workspace_id     TEXT NOT NULL,
    project_id       TEXT,
    thread_id        TEXT,
    profile_id       TEXT,
    session_id       TEXT,
    handoff_id       TEXT,
    source_device_id TEXT,
    status           TEXT NOT NULL DEFAULT 'accepted',
    result           JSONB DEFAULT '{}'::jsonb,
    error            TEXT,
    metadata         JSONB DEFAULT '{}'::jsonb,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at       TIMESTAMPTZ,
    completed_at     TIMESTAMPTZ
);
"""

INDEX_DDL = [
    "CREATE INDEX IF NOT EXISTS idx_compile_jobs_ws_created ON compile_jobs(workspace_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_compile_jobs_session ON compile_jobs(session_id)",
    "CREATE INDEX IF NOT EXISTS idx_compile_jobs_status ON compile_jobs(status, updated_at DESC)",
]


class CompileJobStore(PostgresStoreBase):
    """Postgres persistence for handoff compile jobs."""

    _table_ensured = False

    def __init__(self, db_role: str = "core"):
        super().__init__(db_role=db_role)
        if not CompileJobStore._table_ensured:
            self.ensure_table()
            CompileJobStore._table_ensured = True

    def ensure_table(self) -> None:
        alter_ddls = [
            "ALTER TABLE compile_jobs ADD COLUMN IF NOT EXISTS project_id TEXT",
            "ALTER TABLE compile_jobs ADD COLUMN IF NOT EXISTS thread_id TEXT",
            "ALTER TABLE compile_jobs ADD COLUMN IF NOT EXISTS profile_id TEXT",
            "ALTER TABLE compile_jobs ADD COLUMN IF NOT EXISTS session_id TEXT",
            "ALTER TABLE compile_jobs ADD COLUMN IF NOT EXISTS handoff_id TEXT",
            "ALTER TABLE compile_jobs ADD COLUMN IF NOT EXISTS source_device_id TEXT",
            "ALTER TABLE compile_jobs ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'accepted'",
            "ALTER TABLE compile_jobs ADD COLUMN IF NOT EXISTS result JSONB DEFAULT '{}'::jsonb",
            "ALTER TABLE compile_jobs ADD COLUMN IF NOT EXISTS error TEXT",
            "ALTER TABLE compile_jobs ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'::jsonb",
            "ALTER TABLE compile_jobs ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now()",
            "ALTER TABLE compile_jobs ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now()",
            "ALTER TABLE compile_jobs ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ",
            "ALTER TABLE compile_jobs ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ",
        ]
        with self.transaction() as conn:
            conn.execute(text(TABLE_DDL))
            for alter in alter_ddls:
                conn.execute(text(alter))
            for idx in INDEX_DDL:
                conn.execute(text(idx))
        logger.info("compile_jobs table ensured")

    def create(self, job: CompileJob) -> CompileJob:
        with self.transaction() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO compile_jobs (
                        id, workspace_id, project_id, thread_id, profile_id,
                        session_id, handoff_id, source_device_id, status,
                        result, error, metadata, created_at, updated_at,
                        started_at, completed_at
                    ) VALUES (
                        :id, :workspace_id, :project_id, :thread_id, :profile_id,
                        :session_id, :handoff_id, :source_device_id, :status,
                        :result, :error, :metadata, :created_at, :updated_at,
                        :started_at, :completed_at
                    )
                    """
                ),
                self._job_params(job),
            )
        return job

    def get_by_id(self, job_id: str) -> Optional[CompileJob]:
        with self.get_connection() as conn:
            row = conn.execute(
                text("SELECT * FROM compile_jobs WHERE id = :id"),
                {"id": job_id},
            ).fetchone()
            if not row:
                return None
            return self._row_to_job(row)

    def list_by_workspace(
        self,
        workspace_id: str,
        *,
        limit: int = 50,
    ) -> List[CompileJob]:
        with self.get_connection() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT * FROM compile_jobs
                    WHERE workspace_id = :workspace_id
                    ORDER BY created_at DESC
                    LIMIT :limit
                    """
                ),
                {"workspace_id": workspace_id, "limit": limit},
            ).fetchall()
            return [self._row_to_job(row) for row in rows]

    def update(
        self,
        job_id: str,
        *,
        session_id: Optional[str] = None,
        status: Optional[str] = None,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        started_at: Any = None,
        completed_at: Any = None,
    ) -> CompileJob:
        existing = self.get_by_id(job_id)
        if not existing:
            raise StoreNotFoundError(f"Compile job not found: {job_id}")

        updates = []
        params: Dict[str, Any] = {"id": job_id}

        if session_id is not None:
            updates.append("session_id = :session_id")
            params["session_id"] = session_id
        if status is not None:
            updates.append("status = :status")
            params["status"] = status
        if result is not None:
            updates.append("result = :result")
            params["result"] = self.serialize_json(result)
        if error is not None:
            updates.append("error = :error")
            params["error"] = error
        if metadata is not None:
            updates.append("metadata = :metadata")
            params["metadata"] = self.serialize_json(metadata)
        if started_at is not None:
            updates.append("started_at = :started_at")
            params["started_at"] = started_at
        if completed_at is not None:
            updates.append("completed_at = :completed_at")
            params["completed_at"] = completed_at

        if not updates:
            return existing

        updates.append("updated_at = now()")

        with self.transaction() as conn:
            conn.execute(
                text(f"UPDATE compile_jobs SET {', '.join(updates)} WHERE id = :id"),
                params,
            )
        return self.get_by_id(job_id)

    def mark_running(
        self,
        job_id: str,
        *,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> CompileJob:
        job = self.get_by_id(job_id)
        if not job:
            raise StoreNotFoundError(f"Compile job not found: {job_id}")
        job.mark_running(session_id=session_id, metadata=metadata)
        return self.update(
            job_id,
            session_id=job.session_id,
            status=job.status.value,
            metadata=job.metadata,
            started_at=job.started_at,
        )

    def mark_succeeded(
        self,
        job_id: str,
        *,
        session_id: Optional[str] = None,
        result: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> CompileJob:
        job = self.get_by_id(job_id)
        if not job:
            raise StoreNotFoundError(f"Compile job not found: {job_id}")
        job.mark_succeeded(session_id=session_id, result=result, metadata=metadata)
        return self.update(
            job_id,
            session_id=job.session_id,
            status=job.status.value,
            result=job.result,
            error=job.error,
            metadata=job.metadata,
            completed_at=job.completed_at,
        )

    def mark_failed(
        self,
        job_id: str,
        error: str,
        *,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> CompileJob:
        job = self.get_by_id(job_id)
        if not job:
            raise StoreNotFoundError(f"Compile job not found: {job_id}")
        job.mark_failed(error, session_id=session_id, metadata=metadata)
        return self.update(
            job_id,
            session_id=job.session_id,
            status=job.status.value,
            error=job.error,
            metadata=job.metadata,
            completed_at=job.completed_at,
        )

    def _job_params(self, job: CompileJob) -> Dict[str, Any]:
        return {
            "id": job.id,
            "workspace_id": job.workspace_id,
            "project_id": job.project_id,
            "thread_id": job.thread_id,
            "profile_id": job.profile_id,
            "session_id": job.session_id,
            "handoff_id": job.handoff_id,
            "source_device_id": job.source_device_id,
            "status": job.status.value if hasattr(job.status, "value") else str(job.status),
            "result": self.serialize_json(job.result),
            "error": job.error,
            "metadata": self.serialize_json(job.metadata),
            "created_at": job.created_at,
            "updated_at": job.updated_at,
            "started_at": job.started_at,
            "completed_at": job.completed_at,
        }

    def _row_to_job(self, row: Any) -> CompileJob:
        status = row.status or CompileJobStatus.ACCEPTED.value
        try:
            parsed_status = CompileJobStatus(status)
        except ValueError:
            parsed_status = CompileJobStatus.ACCEPTED
        return CompileJob(
            id=row.id,
            workspace_id=row.workspace_id,
            project_id=row.project_id,
            thread_id=row.thread_id,
            profile_id=row.profile_id,
            session_id=row.session_id,
            handoff_id=row.handoff_id,
            source_device_id=row.source_device_id,
            status=parsed_status,
            result=self.deserialize_json(row.result, default={}),
            error=row.error,
            metadata=self.deserialize_json(row.metadata, default={}),
            created_at=row.created_at,
            updated_at=row.updated_at,
            started_at=row.started_at,
            completed_at=row.completed_at,
        )
