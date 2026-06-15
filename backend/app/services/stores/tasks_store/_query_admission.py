
"""Admission-deferred read-only query methods for TasksStore."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from app.models.workspace import Task, TaskStatus
from backend.app.services.runner_topology import (
    build_queue_partition_filter_clause,
    queue_partition_aliases,
)
from backend.app.services.task_admission_service import ADMISSION_DEFERRED_REASON

from ._query_common import _ADMISSION_DEFERRED_RELEASE_CANDIDATE_SELECT


class TasksStoreAdmissionQueryMixin:
    """Admission release query methods for due blocked tasks."""

    def list_due_admission_deferred_tasks(
        self,
        *,
        queue_shard: Optional[str] = None,
        limit: int = 200,
    ) -> List[Task]:
        query_parts = [
            """
            SELECT *
            FROM tasks
            WHERE task_type IN (:task_type_pb, :task_type_tool)
              AND status = :status
              AND blocked_reason = :blocked_reason
              AND next_eligible_at <= :now
            """
        ]
        params: Dict[str, Any] = {
            "task_type_pb": "playbook_execution",
            "task_type_tool": "tool_execution",
            "status": TaskStatus.PENDING.value,
            "blocked_reason": ADMISSION_DEFERRED_REASON,
            "now": datetime.now(timezone.utc),
            "limit": limit,
        }

        if queue_shard:
            queue_clause, queue_params = build_queue_partition_filter_clause(
                "queue_shard",
                queue_shard,
                param_prefix="queue_partition",
            )
            query_parts.append(f"AND {queue_clause}")
            params.update(queue_params)

        query_parts.append(
            """
            ORDER BY
                CASE
                    WHEN COALESCE(blocked_payload->>'visibility', '') = 'visible' THEN 0
                    ELSE 1
                END ASC,
                next_eligible_at ASC,
                created_at ASC,
                id ASC
            """
        )
        query_parts.append("LIMIT :limit")

        with self.get_connection() as conn:
            rows = conn.execute(text(" ".join(query_parts)), params).fetchall()
            return [self._row_to_task(row) for row in rows]

    def list_due_admission_deferred_release_candidates(
        self,
        *,
        queue_shard: Optional[str] = None,
        limit: int = 200,
    ) -> List[Task]:
        """List due admission-deferred tasks with only fields needed for release evaluation."""
        base_params: Dict[str, Any] = {
            "task_type_pb": "playbook_execution",
            "task_type_tool": "tool_execution",
            "status": TaskStatus.PENDING.value,
            "blocked_reason": ADMISSION_DEFERRED_REASON,
            "now": datetime.now(timezone.utc),
            "limit": limit,
        }

        def build_query(queue_clause: Optional[str] = None) -> str:
            query_parts = [
                _ADMISSION_DEFERRED_RELEASE_CANDIDATE_SELECT,
                """
                WHERE task_type IN (:task_type_pb, :task_type_tool)
                  AND status = :status
                  AND blocked_reason = :blocked_reason
                  AND next_eligible_at <= :now
                """,
            ]
            if queue_clause:
                query_parts.append(f"AND {queue_clause}")
            query_parts.append(
                """
                ORDER BY
                    CASE
                        WHEN COALESCE(blocked_payload->>'visibility', '') = 'visible' THEN 0
                        ELSE 1
                    END ASC,
                    next_eligible_at ASC,
                    created_at ASC,
                    id ASC
                """
            )
            query_parts.append("LIMIT :limit")
            return " ".join(query_parts)

        def sort_key(task: Task) -> tuple[int, datetime, datetime, str]:
            blocked_payload = task.blocked_payload or {}
            visibility = (
                blocked_payload.get("visibility")
                if isinstance(blocked_payload, dict)
                else None
            )
            next_eligible_at = task.next_eligible_at or datetime.max.replace(
                tzinfo=timezone.utc
            )
            created_at = task.created_at or datetime.max.replace(tzinfo=timezone.utc)
            return (
                0 if visibility == "visible" else 1,
                next_eligible_at,
                created_at,
                str(task.id),
            )

        with self.get_connection() as conn:
            if not queue_shard:
                rows = conn.execute(text(build_query()), base_params).fetchall()
                return [self._row_to_admission_release_candidate(row) for row in rows]

            aliases = queue_partition_aliases(queue_shard)
            if not aliases:
                return []

            candidates_by_id: dict[str, Task] = {}
            clauses: list[tuple[str, Dict[str, Any]]] = []
            for index, alias in enumerate(aliases):
                key = f"queue_partition_exact_{index}"
                clauses.append((f"queue_shard = :{key}", {key: alias}))
            if "default" in aliases:
                clauses.append(("queue_shard IS NULL", {}))

            for queue_clause, queue_params in clauses:
                params = dict(base_params)
                params.update(queue_params)
                rows = conn.execute(text(build_query(queue_clause)), params).fetchall()
                for row in rows:
                    task = self._row_to_admission_release_candidate(row)
                    candidates_by_id[str(task.id)] = task

            candidates = sorted(candidates_by_id.values(), key=sort_key)
            return candidates[:limit]
