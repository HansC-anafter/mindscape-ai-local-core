"""
Compile job store for handoff bundle compile lifecycle persistence.
"""

import asyncio
import logging
import threading
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
    "CREATE INDEX IF NOT EXISTS idx_compile_jobs_ws_project_created ON compile_jobs(workspace_id, project_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_compile_jobs_status ON compile_jobs(status, updated_at DESC)",
]

ALTER_DDL_BY_COLUMN = [
    ("project_id", "ALTER TABLE compile_jobs ADD COLUMN IF NOT EXISTS project_id TEXT"),
    ("thread_id", "ALTER TABLE compile_jobs ADD COLUMN IF NOT EXISTS thread_id TEXT"),
    ("profile_id", "ALTER TABLE compile_jobs ADD COLUMN IF NOT EXISTS profile_id TEXT"),
    ("session_id", "ALTER TABLE compile_jobs ADD COLUMN IF NOT EXISTS session_id TEXT"),
    ("handoff_id", "ALTER TABLE compile_jobs ADD COLUMN IF NOT EXISTS handoff_id TEXT"),
    (
        "source_device_id",
        "ALTER TABLE compile_jobs ADD COLUMN IF NOT EXISTS source_device_id TEXT",
    ),
    (
        "status",
        "ALTER TABLE compile_jobs ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'accepted'",
    ),
    (
        "result",
        "ALTER TABLE compile_jobs ADD COLUMN IF NOT EXISTS result JSONB DEFAULT '{}'::jsonb",
    ),
    ("error", "ALTER TABLE compile_jobs ADD COLUMN IF NOT EXISTS error TEXT"),
    (
        "metadata",
        "ALTER TABLE compile_jobs ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'::jsonb",
    ),
    (
        "created_at",
        "ALTER TABLE compile_jobs ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now()",
    ),
    (
        "updated_at",
        "ALTER TABLE compile_jobs ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now()",
    ),
    ("started_at", "ALTER TABLE compile_jobs ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ"),
    (
        "completed_at",
        "ALTER TABLE compile_jobs ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ",
    ),
]


class CompileJobStore(PostgresStoreBase):
    """Postgres persistence for handoff compile jobs."""

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
                WHERE table_name = 'compile_jobs'
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
        if CompileJobStore._table_ensured:
            return
        with CompileJobStore._ensure_lock:
            if CompileJobStore._table_ensured:
                return
            with self.transaction() as conn:
                conn.execute(text(TABLE_DDL))
                existing_columns = self._existing_columns(conn)
                for column_name, alter in ALTER_DDL_BY_COLUMN:
                    if column_name not in existing_columns:
                        conn.execute(text(alter))
                for idx in INDEX_DDL:
                    conn.execute(text(idx))
            CompileJobStore._table_ensured = True
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
        self._emit_stream_event(job)
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

    def list_incomplete(self, *, limit: int = 200) -> List[CompileJob]:
        with self.get_connection() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT * FROM compile_jobs
                    WHERE status IN ('accepted', 'running')
                    ORDER BY created_at DESC
                    LIMIT :limit
                    """
                ),
                {"limit": limit},
            ).fetchall()
            return [self._row_to_job(row) for row in rows]

    def list_accepted(self, *, limit: int = 200) -> List[CompileJob]:
        with self.get_connection() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT * FROM compile_jobs
                    WHERE status = 'accepted'
                    ORDER BY created_at ASC
                    LIMIT :limit
                    """
                ),
                {"limit": limit},
            ).fetchall()
            return [self._row_to_job(row) for row in rows]

    def try_claim_for_resume(
        self,
        job_id: str,
        *,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[CompileJob]:
        existing = self.get_by_id(job_id)
        if not existing:
            raise StoreNotFoundError(f"Compile job not found: {job_id}")

        merged_metadata = dict(existing.metadata or {})
        if metadata:
            merged_metadata.update(metadata)

        with self.transaction() as conn:
            result = conn.execute(
                text(
                    """
                    UPDATE compile_jobs
                    SET status = 'running',
                        session_id = COALESCE(:session_id, session_id),
                        metadata = :metadata,
                        started_at = COALESCE(started_at, now()),
                        updated_at = now()
                    WHERE id = :id
                      AND status = 'accepted'
                    RETURNING id
                    """
                ),
                {
                    "id": job_id,
                    "session_id": session_id,
                    "metadata": self.serialize_json(merged_metadata),
                },
            ).fetchone()

        if not result:
            return None
        updated_job = self.get_by_id(job_id)
        if updated_job:
            self._emit_stream_event(updated_job)
        return updated_job

    def requeue_for_resume(
        self,
        job_id: str,
        *,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[CompileJob]:
        existing = self.get_by_id(job_id)
        if not existing:
            raise StoreNotFoundError(f"Compile job not found: {job_id}")

        merged_metadata = dict(existing.metadata or {})
        if metadata:
            merged_metadata.update(metadata)

        with self.transaction() as conn:
            result = conn.execute(
                text(
                    """
                    UPDATE compile_jobs
                    SET status = 'accepted',
                        session_id = COALESCE(:session_id, session_id),
                        error = NULL,
                        completed_at = NULL,
                        started_at = NULL,
                        metadata = :metadata,
                        updated_at = now()
                    WHERE id = :id
                      AND status = 'running'
                    RETURNING id
                    """
                ),
                {
                    "id": job_id,
                    "session_id": session_id,
                    "metadata": self.serialize_json(merged_metadata),
                },
            ).fetchone()

        if not result:
            return None
        updated_job = self.get_by_id(job_id)
        if updated_job:
            self._emit_stream_event(updated_job)
        return updated_job

    def get_latest_for_project(
        self,
        workspace_id: str,
        project_id: str,
    ) -> Optional[CompileJob]:
        with self.get_connection() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT * FROM compile_jobs
                    WHERE workspace_id = :workspace_id
                      AND project_id = :project_id
                    ORDER BY created_at DESC
                    LIMIT 1
                    """
                ),
                {
                    "workspace_id": workspace_id,
                    "project_id": project_id,
                },
            ).fetchone()
            if not row:
                return None
            return self._row_to_job(row)

    def get_latest_for_session(self, session_id: str) -> Optional[CompileJob]:
        with self.get_connection() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT * FROM compile_jobs
                    WHERE session_id = :session_id
                    ORDER BY created_at DESC
                    LIMIT 1
                    """
                ),
                {"session_id": session_id},
            ).fetchone()
            if not row:
                return None
            return self._row_to_job(row)

    def update(
        self,
        job_id: str,
        *,
        session_id: Optional[str] = None,
        status: Optional[str] = None,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        clear_error: bool = False,
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
        if error is not None or clear_error:
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
        updated_job = self.update(
            job_id,
            session_id=job.session_id,
            status=job.status.value,
            metadata=job.metadata,
            started_at=job.started_at,
        )
        self._emit_stream_event(updated_job)
        return updated_job

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
        updated_job = self.update(
            job_id,
            session_id=job.session_id,
            status=job.status.value,
            result=job.result,
            error=job.error,
            clear_error=True,
            metadata=job.metadata,
            completed_at=job.completed_at,
        )
        self._emit_stream_event(updated_job)
        return updated_job

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
        updated_job = self.update(
            job_id,
            session_id=job.session_id,
            status=job.status.value,
            error=job.error,
            metadata=job.metadata,
            completed_at=job.completed_at,
        )
        self._emit_stream_event(updated_job)
        return updated_job

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

    @staticmethod
    def build_stream_event(job: CompileJob) -> Dict[str, Any]:
        status = job.status.value if hasattr(job.status, "value") else str(job.status)
        event_timestamp = job.updated_at or job.created_at
        event_ts_ms = (
            int(event_timestamp.timestamp() * 1000)
            if event_timestamp is not None
            else 0
        )
        return {
            "id": f"compile-job:{job.id}:{status}:{event_ts_ms}",
            "type": "compile_job_updated",
            "timestamp": event_timestamp.isoformat() if event_timestamp else None,
            "actor": "system",
            "workspace_id": job.workspace_id,
            "project_id": job.project_id,
            "profile_id": job.profile_id or "",
            "thread_id": job.thread_id or job.session_id or job.id,
            "payload": {
                "compile_job_id": job.id,
                "session_id": job.session_id,
                "status": status,
                "error": job.error,
                "result": job.result,
                "metadata": job.public_metadata(),
                "created_at": (
                    job.created_at.isoformat() if job.created_at else None
                ),
                "updated_at": (
                    job.updated_at.isoformat() if job.updated_at else None
                ),
                "started_at": (
                    job.started_at.isoformat() if job.started_at else None
                ),
                "completed_at": (
                    job.completed_at.isoformat() if job.completed_at else None
                ),
                "terminal": status in ("succeeded", "failed"),
            },
            "metadata": {
                "compile_job_id": job.id,
                "compile_job_status": status,
                "session_id": job.session_id,
            },
        }

    def _emit_stream_event(self, job: Optional[CompileJob]) -> None:
        if job is None:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return

        event = self.build_stream_event(job)
        thread_id = (
            event.get("thread_id")
            or job.thread_id
            or job.session_id
            or job.id
        )

        async def _publish() -> None:
            try:
                from backend.app.services.cache.async_redis import publish_meeting_chunk

                await publish_meeting_chunk(job.workspace_id, event, str(thread_id))
            except Exception as exc:
                logger.debug(
                    "Failed to publish compile job stream event for %s: %s",
                    job.id,
                    exc,
                )

        try:
            loop.create_task(_publish())
        except Exception:
            logger.debug("Failed to schedule compile job stream event for %s", job.id)
