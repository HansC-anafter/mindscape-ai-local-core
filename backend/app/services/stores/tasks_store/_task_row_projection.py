"""Row projection helpers for TasksStore CRUD."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from app.models.workspace import Task
from backend.app.services.runner_topology import normalize_queue_partition

from ._crud_helpers import (
    _resolve_hydrated_queue_shard,
    _utc_now,
    coerce_task_status_enum,
)


class TasksStoreRowProjectionMixin:
    """Convert persisted task rows into Task models."""

    def _coerce_datetime(self, value: Optional[Any]) -> Optional[datetime]:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        return self.from_isoformat(value)

    def _row_to_task(self, row) -> Task:
        """Convert database row to Task model"""
        execution_context = None
        try:
            raw_ctx = getattr(row, "execution_context", None)
            if raw_ctx:
                execution_context = self.deserialize_json(raw_ctx)
        except Exception:
            execution_context = None

        storyline_tags = []
        try:
            raw_tags = getattr(row, "storyline_tags", None)
            if raw_tags:
                storyline_tags = self.deserialize_json(raw_tags, [])
        except Exception:
            storyline_tags = []

        project_id = getattr(row, "project_id", None)
        blocked_payload = None
        try:
            raw_blocked_payload = getattr(row, "blocked_payload", None)
            if raw_blocked_payload is not None:
                blocked_payload = self.deserialize_json(raw_blocked_payload, None)
        except Exception:
            blocked_payload = None

        return Task(
            id=row.id,
            workspace_id=row.workspace_id,
            message_id=row.message_id,
            execution_id=row.execution_id,
            parent_execution_id=getattr(row, "parent_execution_id", None),
            project_id=project_id,
            pack_id=row.pack_id,
            task_type=row.task_type,
            status=coerce_task_status_enum(row.status),
            params=self.deserialize_json(row.params, {}),
            result=self.deserialize_json(row.result),
            execution_context=execution_context,
            meeting_session_id=getattr(row, "meeting_session_id", None),
            storyline_tags=storyline_tags,
            created_at=self._coerce_datetime(row.created_at),
            next_eligible_at=self._coerce_datetime(
                getattr(row, "next_eligible_at", None)
            )
            or self._coerce_datetime(row.created_at)
            or _utc_now(),
            blocked_reason=getattr(row, "blocked_reason", None),
            blocked_payload=blocked_payload,
            queue_shard=(
                normalize_queue_partition(
                    getattr(row, "queue_shard", None),
                    fallback=None,
                )
                or _resolve_hydrated_queue_shard(row.pack_id, execution_context)
            ),
            concurrency_key=getattr(row, "concurrency_key", None),
            frontier_state=getattr(row, "frontier_state", "cold") or "cold",
            frontier_enqueued_at=self._coerce_datetime(
                getattr(row, "frontier_enqueued_at", None)
            ),
            runner_id=getattr(row, "runner_id", None),
            heartbeat_at=self._coerce_datetime(getattr(row, "heartbeat_at", None)),
            started_at=self._coerce_datetime(row.started_at),
            completed_at=self._coerce_datetime(row.completed_at),
            error=row.error,
        )
