"""PostgreSQL store for memory_writeback_runs."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from sqlalchemy import text

from backend.app.models.memory_contract import (
    MemoryWritebackRun,
    MemoryWritebackRunStatus,
)
from backend.app.services.stores.postgres_base import PostgresStoreBase


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MemoryWritebackRunStore(PostgresStoreBase):
    """CRUD helpers and state transitions for memory_writeback_runs."""

    def create(self, run: MemoryWritebackRun) -> MemoryWritebackRun:
        with self.transaction() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO memory_writeback_runs (
                        id, run_type, source_scope, source_id, status,
                        idempotency_key, update_mode_summary, started_at,
                        completed_at, summary, error_detail, last_stage,
                        metadata, created_at, updated_at
                    ) VALUES (
                        :id, :run_type, :source_scope, :source_id, :status,
                        :idempotency_key, :update_mode_summary, :started_at,
                        :completed_at, :summary, :error_detail, :last_stage,
                        :metadata, :created_at, :updated_at
                    )
                    """
                ),
                {
                    "id": run.id,
                    "run_type": run.run_type,
                    "source_scope": run.source_scope,
                    "source_id": run.source_id,
                    "status": run.status,
                    "idempotency_key": run.idempotency_key,
                    "update_mode_summary": self.serialize_json(run.update_mode_summary),
                    "started_at": run.started_at,
                    "completed_at": run.completed_at,
                    "summary": self.serialize_json(run.summary),
                    "error_detail": run.error_detail,
                    "last_stage": run.last_stage,
                    "metadata": self.serialize_json(run.metadata),
                    "created_at": run.created_at,
                    "updated_at": run.updated_at,
                },
            )
        return run

    def get(self, run_id: str) -> Optional[MemoryWritebackRun]:
        with self.get_connection() as conn:
            row = conn.execute(
                text("SELECT * FROM memory_writeback_runs WHERE id = :id"),
                {"id": run_id},
            ).fetchone()
        if not row:
            return None
        return self._row_to_run(row)

    def get_by_idempotency_key(self, idempotency_key: str) -> Optional[MemoryWritebackRun]:
        with self.get_connection() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT * FROM memory_writeback_runs
                    WHERE idempotency_key = :idempotency_key
                    LIMIT 1
                    """
                ),
                {"idempotency_key": idempotency_key},
            ).fetchone()
        if not row:
            return None
        return self._row_to_run(row)

    def get_or_create(
        self,
        *,
        run_type: str,
        source_scope: str,
        source_id: str,
        idempotency_key: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Tuple[MemoryWritebackRun, bool]:
        existing = self.get_by_idempotency_key(idempotency_key)
        if existing:
            return existing, False
        run = MemoryWritebackRun.new(
            run_type=run_type,
            source_scope=source_scope,
            source_id=source_id,
            idempotency_key=idempotency_key,
            metadata=metadata,
        )
        self.create(run)
        return run, True

    def mark_stage(
        self,
        run_id: str,
        *,
        last_stage: str,
        summary_update: Optional[Dict[str, Any]] = None,
    ) -> Optional[MemoryWritebackRun]:
        run = self.get(run_id)
        if not run:
            return None
        merged_summary = dict(run.summary or {})
        if summary_update:
            merged_summary.update(summary_update)
        now = _utc_now()
        with self.transaction() as conn:
            conn.execute(
                text(
                    """
                    UPDATE memory_writeback_runs
                    SET last_stage = :last_stage,
                        summary = :summary,
                        updated_at = :updated_at
                    WHERE id = :id
                    """
                ),
                {
                    "id": run_id,
                    "last_stage": last_stage,
                    "summary": self.serialize_json(merged_summary),
                    "updated_at": now,
                },
            )
        return self.get(run_id)

    def mark_completed(
        self,
        run_id: str,
        *,
        summary: Optional[Dict[str, Any]] = None,
        update_mode_summary: Optional[Dict[str, Any]] = None,
        last_stage: str = "completed",
    ) -> Optional[MemoryWritebackRun]:
        run = self.get(run_id)
        if not run:
            return None
        merged_summary = dict(run.summary or {})
        if summary:
            merged_summary.update(summary)
        merged_update_modes = dict(run.update_mode_summary or {})
        if update_mode_summary:
            merged_update_modes.update(update_mode_summary)
        now = _utc_now()
        with self.transaction() as conn:
            conn.execute(
                text(
                    """
                    UPDATE memory_writeback_runs
                    SET status = :status,
                        completed_at = :completed_at,
                        summary = :summary,
                        update_mode_summary = :update_mode_summary,
                        last_stage = :last_stage,
                        updated_at = :updated_at
                    WHERE id = :id
                    """
                ),
                {
                    "id": run_id,
                    "status": MemoryWritebackRunStatus.COMPLETED.value,
                    "completed_at": now,
                    "summary": self.serialize_json(merged_summary),
                    "update_mode_summary": self.serialize_json(merged_update_modes),
                    "last_stage": last_stage,
                    "updated_at": now,
                },
            )
        return self.get(run_id)

    def mark_failed(
        self,
        run_id: str,
        *,
        error_detail: str,
        summary: Optional[Dict[str, Any]] = None,
        last_stage: str = "failed",
    ) -> Optional[MemoryWritebackRun]:
        run = self.get(run_id)
        if not run:
            return None
        merged_summary = dict(run.summary or {})
        if summary:
            merged_summary.update(summary)
        now = _utc_now()
        with self.transaction() as conn:
            conn.execute(
                text(
                    """
                    UPDATE memory_writeback_runs
                    SET status = :status,
                        completed_at = :completed_at,
                        summary = :summary,
                        error_detail = :error_detail,
                        last_stage = :last_stage,
                        updated_at = :updated_at
                    WHERE id = :id
                    """
                ),
                {
                    "id": run_id,
                    "status": MemoryWritebackRunStatus.FAILED.value,
                    "completed_at": now,
                    "summary": self.serialize_json(merged_summary),
                    "error_detail": error_detail,
                    "last_stage": last_stage,
                    "updated_at": now,
                },
            )
        return self.get(run_id)

    def _row_to_run(self, row: Any) -> MemoryWritebackRun:
        data: Dict[str, Any] = row._mapping if hasattr(row, "_mapping") else row
        return MemoryWritebackRun(
            id=data["id"],
            run_type=data["run_type"],
            source_scope=data["source_scope"],
            source_id=data["source_id"],
            status=data["status"],
            idempotency_key=data["idempotency_key"],
            update_mode_summary=self.deserialize_json(
                data.get("update_mode_summary"), default={}
            ),
            started_at=data["started_at"],
            completed_at=data.get("completed_at"),
            summary=self.deserialize_json(data.get("summary"), default={}),
            error_detail=data.get("error_detail"),
            last_stage=data.get("last_stage", "created"),
            metadata=self.deserialize_json(data.get("metadata"), default={}),
            created_at=data["created_at"],
            updated_at=data["updated_at"],
        )
