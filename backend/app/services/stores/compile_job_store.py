"""
Postgres store for compile job lifecycle state.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import text

from backend.app.models.compile_job import CompileJob, CompileJobStatus
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
    "CREATE INDEX IF NOT EXISTS idx_compile_jobs_workspace_id ON compile_jobs(workspace_id)",
    "CREATE INDEX IF NOT EXISTS idx_compile_jobs_session_id ON compile_jobs(session_id)",
    "CREATE INDEX IF NOT EXISTS idx_compile_jobs_project_id ON compile_jobs(project_id)",
    "CREATE INDEX IF NOT EXISTS idx_compile_jobs_status ON compile_jobs(status)",
    "CREATE INDEX IF NOT EXISTS idx_compile_jobs_created_at ON compile_jobs(created_at DESC)",
]


class CompileJobStore(PostgresStoreBase):
    _table_ensured = False

    def __init__(self, db_role: str = "core"):
        super().__init__(db_role=db_role)
        if not CompileJobStore._table_ensured:
            self.ensure_table()
            CompileJobStore._table_ensured = True

    def ensure_table(self) -> None:
        with self.transaction() as conn:
            conn.execute(text(TABLE_DDL))
            for idx in INDEX_DDL:
                conn.execute(text(idx))
        CompileJobStore._table_ensured = True
        logger.info("compile_jobs table ensured")

    def get_by_id(self, job_id: str) -> Optional[CompileJob]:
        with self.get_connection() as conn:
            row = (
                conn.execute(
                    text("SELECT * FROM compile_jobs WHERE id = :id"),
                    {"id": job_id},
                )
                .mappings()
                .first()
            )
        return self._row_to_job(row) if row else None

    def get_latest_for_session(self, session_id: str) -> Optional[CompileJob]:
        with self.get_connection() as conn:
            row = (
                conn.execute(
                    text(
                        """
                        SELECT *
                        FROM compile_jobs
                        WHERE session_id = :session_id
                        ORDER BY created_at DESC
                        LIMIT 1
                        """
                    ),
                    {"session_id": session_id},
                )
                .mappings()
                .first()
            )
        return self._row_to_job(row) if row else None

    def list_incomplete(self, limit: int = 500) -> list[CompileJob]:
        with self.get_connection() as conn:
            rows = (
                conn.execute(
                    text(
                        """
                        SELECT *
                        FROM compile_jobs
                        WHERE status IN ('accepted', 'running')
                        ORDER BY created_at DESC
                        LIMIT :limit
                        """
                    ),
                    {"limit": limit},
                )
                .mappings()
                .all()
            )
        return [self._row_to_job(row) for row in rows]

    def create(self, job: CompileJob) -> CompileJob:
        workspace_id = job.workspace_id or (job.metadata or {}).get("workspace_id")
        if not workspace_id:
            raise ValueError("CompileJob.workspace_id is required")
        with self.transaction() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO compile_jobs (
                        id,
                        workspace_id,
                        project_id,
                        thread_id,
                        profile_id,
                        session_id,
                        handoff_id,
                        source_device_id,
                        status,
                        result,
                        error,
                        metadata,
                        created_at,
                        updated_at,
                        started_at,
                        completed_at
                    ) VALUES (
                        :id,
                        :workspace_id,
                        :project_id,
                        :thread_id,
                        :profile_id,
                        :session_id,
                        :handoff_id,
                        :source_device_id,
                        :status,
                        CAST(:result AS JSONB),
                        :error,
                        CAST(:metadata AS JSONB),
                        :created_at,
                        :updated_at,
                        :started_at,
                        :completed_at
                    )
                    """
                ),
                {
                    "id": job.id,
                    "workspace_id": workspace_id,
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
                },
            )
        return job

    def mark_succeeded(
        self,
        job_id: str,
        *,
        session_id: Optional[str] = None,
        result: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[CompileJob]:
        existing = self.get_by_id(job_id)
        if existing is None:
            return None
        merged_metadata = dict(existing.metadata or {})
        if isinstance(metadata, dict):
            merged_metadata.update(metadata)
        effective_session_id = session_id or existing.session_id
        effective_result = result if isinstance(result, dict) else dict(existing.result or {})
        with self.transaction() as conn:
            conn.execute(
                text(
                    """
                    UPDATE compile_jobs
                    SET status = :status,
                        session_id = :session_id,
                        result = CAST(:result AS JSONB),
                        error = NULL,
                        metadata = CAST(:metadata AS JSONB),
                        updated_at = now(),
                        completed_at = COALESCE(completed_at, now())
                    WHERE id = :id
                    """
                ),
                {
                    "id": job_id,
                    "status": CompileJobStatus.SUCCEEDED.value,
                    "session_id": effective_session_id,
                    "result": self.serialize_json(effective_result),
                    "metadata": self.serialize_json(merged_metadata),
                },
            )
        return self.get_by_id(job_id)

    def mark_failed(
        self,
        job_id: str,
        error: str,
        *,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[CompileJob]:
        existing = self.get_by_id(job_id)
        if existing is None:
            return None
        merged_metadata = dict(existing.metadata or {})
        if isinstance(metadata, dict):
            merged_metadata.update(metadata)
        effective_session_id = session_id or existing.session_id
        with self.transaction() as conn:
            conn.execute(
                text(
                    """
                    UPDATE compile_jobs
                    SET status = :status,
                        session_id = :session_id,
                        error = :error,
                        metadata = CAST(:metadata AS JSONB),
                        updated_at = now(),
                        completed_at = COALESCE(completed_at, now())
                    WHERE id = :id
                    """
                ),
                {
                    "id": job_id,
                    "status": CompileJobStatus.FAILED.value,
                    "session_id": effective_session_id,
                    "error": error,
                    "metadata": self.serialize_json(merged_metadata),
                },
            )
        return self.get_by_id(job_id)

    def mark_incomplete_for_session(
        self,
        session_id: str,
        error: str,
        *,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        merged_metadata = metadata or {}
        with self.transaction() as conn:
            result = conn.execute(
                text(
                    """
                    UPDATE compile_jobs
                    SET status = :status,
                        error = :error,
                        metadata = COALESCE(metadata, '{}'::jsonb) || CAST(:metadata AS JSONB),
                        updated_at = now(),
                        completed_at = COALESCE(completed_at, now())
                    WHERE session_id = :session_id
                      AND status IN ('accepted', 'running')
                    """
                ),
                {
                    "session_id": session_id,
                    "status": CompileJobStatus.FAILED.value,
                    "error": error,
                    "metadata": self.serialize_json(merged_metadata),
                },
            )
        return result.rowcount or 0

    def _row_to_job(self, row: Any) -> CompileJob:
        data = dict(row)
        status_raw = data.get("status") or CompileJobStatus.ACCEPTED.value
        try:
            status = CompileJobStatus(status_raw)
        except Exception:
            status = CompileJobStatus.ACCEPTED
        return CompileJob(
            id=data["id"],
            workspace_id=data.get("workspace_id"),
            project_id=data.get("project_id"),
            thread_id=data.get("thread_id"),
            profile_id=data.get("profile_id"),
            session_id=data.get("session_id"),
            handoff_id=data.get("handoff_id"),
            source_device_id=data.get("source_device_id"),
            status=status,
            result=self.deserialize_json(data.get("result"), {}),
            error=data.get("error"),
            metadata=self.deserialize_json(data.get("metadata"), {}),
            created_at=self._coerce_datetime(data.get("created_at")),
            updated_at=self._coerce_datetime(data.get("updated_at")),
            started_at=self._coerce_datetime(data.get("started_at")),
            completed_at=self._coerce_datetime(data.get("completed_at")),
        )

    @staticmethod
    def _coerce_datetime(value: Any) -> Optional[datetime]:
        if value is None or isinstance(value, datetime):
            return value
        try:
            return datetime.fromisoformat(str(value))
        except Exception:
            return None
