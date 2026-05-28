"""PostgreSQL store for durable capability install jobs."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from sqlalchemy import text

from backend.app.services.stores.postgres_base import PostgresStoreBase

logger = logging.getLogger(__name__)

TABLE_DDL = """
CREATE TABLE IF NOT EXISTS capability_install_jobs (
    install_id            TEXT PRIMARY KEY,
    source_kind           TEXT NOT NULL,
    state                 TEXT NOT NULL DEFAULT 'queued',
    source_payload        JSONB NOT NULL DEFAULT '{}'::jsonb,
    result_payload        JSONB NOT NULL DEFAULT '{}'::jsonb,
    error                 TEXT,
    retry_after_seconds   INTEGER,
    not_before            TIMESTAMPTZ,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at            TIMESTAMPTZ,
    finished_at           TIMESTAMPTZ
);
"""

INDEX_DDL = [
    "CREATE INDEX IF NOT EXISTS idx_capability_install_jobs_state ON capability_install_jobs(state)",
    "CREATE INDEX IF NOT EXISTS idx_capability_install_jobs_not_before ON capability_install_jobs(not_before)",
    "CREATE INDEX IF NOT EXISTS idx_capability_install_jobs_created_at ON capability_install_jobs(created_at)",
]


class CapabilityInstallJobStore(PostgresStoreBase):
    """Durable store for capability install orchestration state."""

    _table_ensured = False

    def __init__(self, db_role: str = "core"):
        super().__init__(db_role=db_role)
        if not CapabilityInstallJobStore._table_ensured:
            self.ensure_table()
            CapabilityInstallJobStore._table_ensured = True

    def ensure_table(self) -> None:
        with self.transaction() as conn:
            conn.execute(text(TABLE_DDL))
            for ddl in INDEX_DDL:
                conn.execute(text(ddl))
        logger.info("capability_install_jobs table ensured")

    def create_job(
        self,
        *,
        install_id: str,
        source_kind: str,
        source_payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        with self.transaction() as conn:
            row = (
                conn.execute(
                    text(
                        """
                        INSERT INTO capability_install_jobs (
                            install_id,
                            source_kind,
                            state,
                            source_payload
                        ) VALUES (
                            :install_id,
                            :source_kind,
                            'queued',
                            CAST(:source_payload AS JSONB)
                        )
                        RETURNING *
                        """
                    ),
                    {
                        "install_id": install_id,
                        "source_kind": source_kind,
                        "source_payload": self.serialize_json(source_payload),
                    },
                )
                .mappings()
                .one()
            )
        return self._row_to_dict(row)

    def get_job(self, install_id: str) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            row = (
                conn.execute(
                    text(
                        "SELECT * FROM capability_install_jobs WHERE install_id = :install_id"
                    ),
                    {"install_id": install_id},
                )
                .mappings()
                .first()
            )
        return self._row_to_dict(row) if row else None

    def claim_next_job(self) -> Optional[Dict[str, Any]]:
        with self.transaction() as conn:
            running = conn.execute(
                text(
                    """
                    SELECT install_id
                    FROM capability_install_jobs
                    WHERE state = 'running'
                    LIMIT 1
                    """
                )
            ).first()
            if running is not None:
                return None

            row = (
                conn.execute(
                    text(
                        """
                        WITH candidate AS (
                            SELECT install_id
                            FROM capability_install_jobs
                            WHERE
                                state = 'queued'
                                OR (
                                    state = 'waiting_db'
                                    AND (not_before IS NULL OR not_before <= now())
                                )
                            ORDER BY created_at ASC
                            FOR UPDATE SKIP LOCKED
                            LIMIT 1
                        )
                        UPDATE capability_install_jobs AS jobs
                        SET state = 'running',
                            error = NULL,
                            retry_after_seconds = NULL,
                            not_before = NULL,
                            started_at = COALESCE(started_at, now()),
                            updated_at = now()
                        FROM candidate
                        WHERE jobs.install_id = candidate.install_id
                        RETURNING jobs.*
                        """
                    )
                )
                .mappings()
                .first()
            )
        return self._row_to_dict(row) if row else None

    def mark_waiting_db(
        self,
        install_id: str,
        *,
        reason: str,
        retry_after_seconds: int,
    ) -> Optional[Dict[str, Any]]:
        with self.transaction() as conn:
            row = (
                conn.execute(
                    text(
                        """
                        UPDATE capability_install_jobs
                        SET state = 'waiting_db',
                            error = :reason,
                            retry_after_seconds = :retry_after_seconds,
                            not_before = now() + (:retry_after_seconds || ' seconds')::interval,
                            updated_at = now()
                        WHERE install_id = :install_id
                        RETURNING *
                        """
                    ),
                    {
                        "install_id": install_id,
                        "reason": reason,
                        "retry_after_seconds": retry_after_seconds,
                    },
                )
                .mappings()
                .first()
            )
        return self._row_to_dict(row) if row else None

    def mark_succeeded(
        self,
        install_id: str,
        *,
        result_payload: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        return self._mark_terminal(
            install_id,
            state="succeeded",
            result_payload=result_payload,
            error=None,
        )

    def mark_pending_execution_activation(
        self,
        install_id: str,
        *,
        result_payload: Dict[str, Any],
        error: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        return self._mark_terminal(
            install_id,
            state="pending_execution_activation",
            result_payload=result_payload,
            error=error,
        )

    def mark_failed(
        self,
        install_id: str,
        *,
        error: str,
        result_payload: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        return self._mark_terminal(
            install_id,
            state="failed",
            result_payload=result_payload or {},
            error=error,
        )

    def requeue_running_jobs_for_shutdown(self) -> int:
        with self.transaction() as conn:
            result = conn.execute(
                text(
                    """
                    UPDATE capability_install_jobs
                    SET state = 'queued',
                        error = 'requeued_after_shutdown',
                        updated_at = now()
                    WHERE state = 'running'
                    """
                )
            )
        return int(result.rowcount or 0)

    def _mark_terminal(
        self,
        install_id: str,
        *,
        state: str,
        result_payload: Dict[str, Any],
        error: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        with self.transaction() as conn:
            row = (
                conn.execute(
                    text(
                        """
                        UPDATE capability_install_jobs
                        SET state = :state,
                            result_payload = CAST(:result_payload AS JSONB),
                            error = :error,
                            retry_after_seconds = NULL,
                            not_before = NULL,
                            finished_at = COALESCE(finished_at, now()),
                            updated_at = now()
                        WHERE install_id = :install_id
                        RETURNING *
                        """
                    ),
                    {
                        "install_id": install_id,
                        "state": state,
                        "result_payload": self.serialize_json(result_payload),
                        "error": error,
                    },
                )
                .mappings()
                .first()
            )
        return self._row_to_dict(row) if row else None

    def _row_to_dict(self, row: Any) -> Dict[str, Any]:
        item = dict(row)
        item["source_payload"] = self.deserialize_json(item.get("source_payload"), {})
        item["result_payload"] = self.deserialize_json(item.get("result_payload"), {})
        for key in ("created_at", "updated_at", "started_at", "finished_at", "not_before"):
            value = item.get(key)
            if hasattr(value, "isoformat"):
                item[key] = value.isoformat()
        return item
