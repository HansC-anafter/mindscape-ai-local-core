"""Run and worker attempt control-plane storage."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import text

from app.services.stores.postgres_base import PostgresStoreBase


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RunAttemptsStore(PostgresStoreBase):
    """Persist run control records and idempotent worker attempts."""

    def upsert_run(
        self,
        *,
        run_id: str,
        execution_id: str,
        workspace_id: str,
        task_id: Optional[str],
        pack_id: Optional[str],
        status: str,
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
        conn=None,
    ) -> str:
        params = {
            "run_id": run_id,
            "execution_id": execution_id,
            "workspace_id": workspace_id,
            "task_id": task_id,
            "pack_id": pack_id,
            "status": status,
            "started_at": started_at,
            "completed_at": completed_at,
            "updated_at": _utc_now(),
        }
        query = text(
            """
            INSERT INTO runs (
                run_id,
                execution_id,
                workspace_id,
                task_id,
                pack_id,
                status,
                started_at,
                completed_at,
                updated_at
            )
            VALUES (
                :run_id,
                :execution_id,
                :workspace_id,
                :task_id,
                :pack_id,
                :status,
                :started_at,
                :completed_at,
                :updated_at
            )
            ON CONFLICT (run_id)
            DO UPDATE SET
                execution_id = EXCLUDED.execution_id,
                workspace_id = EXCLUDED.workspace_id,
                task_id = EXCLUDED.task_id,
                pack_id = EXCLUDED.pack_id,
                status = EXCLUDED.status,
                started_at = COALESCE(runs.started_at, EXCLUDED.started_at),
                completed_at = EXCLUDED.completed_at,
                updated_at = EXCLUDED.updated_at
            """
        )
        active_conn = conn
        if active_conn is not None:
            active_conn.execute(query, params)
            return run_id
        with self.transaction() as owned_conn:
            owned_conn.execute(query, params)
        return run_id

    def create_attempt(
        self,
        *,
        run_id: str,
        task_id: str,
        runner_id: Optional[str],
        status: str,
        started_at: Optional[datetime] = None,
        attempt_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        conn=None,
    ) -> str:
        resolved_attempt_id = attempt_id or f"attempt_{uuid4().hex}"
        resolved_idempotency_key = idempotency_key or resolved_attempt_id
        params = {
            "attempt_id": resolved_attempt_id,
            "run_id": run_id,
            "task_id": task_id,
            "runner_id": runner_id,
            "status": status,
            "started_at": started_at or _utc_now(),
            "idempotency_key": resolved_idempotency_key,
            "updated_at": _utc_now(),
        }
        query = text(
            """
            INSERT INTO run_attempts (
                attempt_id,
                run_id,
                task_id,
                runner_id,
                attempt_no,
                status,
                started_at,
                idempotency_key,
                updated_at
            )
            VALUES (
                :attempt_id,
                :run_id,
                :task_id,
                :runner_id,
                COALESCE(
                    (
                        SELECT MAX(existing_attempt.attempt_no) + 1
                        FROM run_attempts existing_attempt
                        WHERE existing_attempt.run_id = :run_id
                    ),
                    1
                ),
                :status,
                :started_at,
                :idempotency_key,
                :updated_at
            )
            ON CONFLICT (idempotency_key) DO NOTHING
            RETURNING attempt_id
            """
        )
        active_conn = conn
        if active_conn is not None:
            row = active_conn.execute(query, params).fetchone()
            if row:
                return row[0]
            return self._attempt_id_for_idempotency_key(
                resolved_idempotency_key,
                conn=active_conn,
            )
        with self.transaction() as owned_conn:
            row = owned_conn.execute(query, params).fetchone()
            if row:
                return row[0]
            return self._attempt_id_for_idempotency_key(
                resolved_idempotency_key,
                conn=owned_conn,
            )

    def complete_latest_attempt_for_task(
        self,
        *,
        task_id: str,
        status: str,
        completed_at: Optional[datetime] = None,
        error_summary: Optional[str] = None,
        conn=None,
    ) -> Optional[str]:
        finished_at = completed_at or _utc_now()
        params = {
            "task_id": task_id,
            "status": status,
            "completed_at": finished_at,
            "error_summary": error_summary,
            "updated_at": _utc_now(),
        }
        query = text(
            """
            WITH latest_attempt AS (
                SELECT attempt_id, started_at
                FROM run_attempts
                WHERE task_id = :task_id
                ORDER BY started_at DESC NULLS LAST, created_at DESC
                LIMIT 1
            )
            UPDATE run_attempts
            SET status = :status,
                completed_at = :completed_at,
                duration_ms = CASE
                    WHEN latest_attempt.started_at IS NULL THEN duration_ms
                    ELSE GREATEST(
                        0,
                        FLOOR(
                            EXTRACT(
                                EPOCH FROM (:completed_at - latest_attempt.started_at)
                            ) * 1000
                        )::BIGINT
                    )
                END,
                error_summary = :error_summary,
                updated_at = :updated_at
            FROM latest_attempt
            WHERE run_attempts.attempt_id = latest_attempt.attempt_id
            RETURNING run_attempts.attempt_id
            """
        )
        active_conn = conn
        if active_conn is not None:
            row = active_conn.execute(query, params).fetchone()
            return row[0] if row else None
        with self.transaction() as owned_conn:
            row = owned_conn.execute(query, params).fetchone()
            return row[0] if row else None

    def _attempt_id_for_idempotency_key(self, idempotency_key: str, *, conn) -> str:
        row = conn.execute(
            text(
                """
                SELECT attempt_id
                FROM run_attempts
                WHERE idempotency_key = :idempotency_key
                """
            ),
            {"idempotency_key": idempotency_key},
        ).fetchone()
        if row:
            return row[0]
        raise RuntimeError("Run attempt idempotency lookup failed")
