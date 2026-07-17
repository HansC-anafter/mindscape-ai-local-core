"""Compact task control projection for execution progress reads."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import text


_PROGRESS_TASK_SQL = """
SELECT
    id,
    workspace_id,
    execution_id,
    status,
    queue_shard,
    blocked_reason,
    jsonb_strip_nulls(jsonb_build_object(
        'reason', blocked_payload -> 'reason',
        'defer_until', blocked_payload -> 'defer_until',
        'visibility', blocked_payload -> 'visibility',
        'producer_kind', blocked_payload -> 'producer_kind',
        'queue_shard', blocked_payload -> 'queue_shard'
    )) AS blocked_payload,
    frontier_state,
    next_eligible_at,
    created_at,
    runner_id,
    heartbeat_at,
    jsonb_strip_nulls(jsonb_build_object(
        'heartbeat_at', execution_context -> 'heartbeat_at',
        'runner_id', execution_context -> 'runner_id',
        'execution_backend_hint', execution_context -> 'execution_backend_hint',
        'dependency_hold', execution_context -> 'dependency_hold',
        'admission_policy', execution_context -> 'admission_policy',
        'admission', execution_context -> 'admission'
    )) AS execution_context
FROM tasks
WHERE execution_id = :execution_id OR id = :execution_id
ORDER BY (execution_id = :execution_id) DESC, created_at DESC
LIMIT 1
"""


@dataclass(frozen=True)
class ProgressTaskControl:
    """Only fields needed to render queue/admission/progress state."""

    id: str
    workspace_id: str
    execution_id: Optional[str]
    status: str
    queue_shard: Optional[str]
    blocked_reason: Optional[str]
    blocked_payload: dict[str, Any]
    frontier_state: Optional[str]
    next_eligible_at: Optional[datetime]
    created_at: Optional[datetime]
    runner_id: Optional[str]
    heartbeat_at: Optional[datetime]
    execution_context: dict[str, Any]


class TasksStoreProgressSnapshotMixin:
    """Read one execution without materializing task JSON payload columns."""

    def get_progress_task_control(
        self,
        execution_id: str,
    ) -> Optional[ProgressTaskControl]:
        with self.get_connection() as conn:
            row = (
                conn.execute(
                    text(_PROGRESS_TASK_SQL),
                    {"execution_id": execution_id},
                )
                .mappings()
                .first()
            )
        if row is None:
            return None
        return ProgressTaskControl(
            id=str(row["id"]),
            workspace_id=str(row["workspace_id"]),
            execution_id=(
                str(row["execution_id"]) if row.get("execution_id") else None
            ),
            status=str(row.get("status") or ""),
            queue_shard=row.get("queue_shard"),
            blocked_reason=row.get("blocked_reason"),
            blocked_payload=dict(row.get("blocked_payload") or {}),
            frontier_state=row.get("frontier_state"),
            next_eligible_at=row.get("next_eligible_at"),
            created_at=row.get("created_at"),
            runner_id=row.get("runner_id"),
            heartbeat_at=row.get("heartbeat_at"),
            execution_context=dict(row.get("execution_context") or {}),
        )
