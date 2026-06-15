
"""Runner candidate read-only query methods for TasksStore."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from app.models.workspace import Task, TaskStatus
from backend.app.services.runner_topology import (
    BROWSER_LOCAL_QUEUE_PARTITION,
    build_queue_partition_filter_clause,
    normalize_queue_partition,
    queue_partition_matches,
)
from backend.app.services.task_admission_service import ADMISSION_DEFERRED_REASON

from ._query_common import _ADMISSION_RELEASE_CANDIDATE_SELECT


class TasksStoreCandidateQueryMixin:
    """Candidate selection query methods for runner-facing read paths."""

    def list_runner_candidate_projections_by_ids(
        self,
        task_ids: list[str],
        queue_shard: str,
    ) -> list[dict[str, Any]]:
        ordered_ids: list[str] = []
        seen: set[str] = set()
        for raw_task_id in task_ids:
            task_id = str(raw_task_id or "").strip()
            if not task_id or task_id in seen:
                continue
            seen.add(task_id)
            ordered_ids.append(task_id)
        if not ordered_ids:
            return []

        queue_clause, queue_params = build_queue_partition_filter_clause(
            "queue_shard",
            queue_shard,
            param_prefix="candidate_queue",
        )
        if not queue_clause:
            return []

        id_params = {
            f"candidate_task_id_{index}": task_id
            for index, task_id in enumerate(ordered_ids)
        }
        id_placeholders = ", ".join(f":{key}" for key in id_params)
        query = text(
            f"""
            SELECT
                id::text AS id,
                pack_id,
                task_type,
                status,
                frontier_state,
                queue_shard,
                execution_context,
                created_at,
                frontier_enqueued_at
            FROM tasks
            WHERE id::text IN ({id_placeholders})
              AND {queue_clause}
              AND status = :pending_status
              AND frontier_state = :ready_frontier_state
            """
        )
        params: dict[str, Any] = {
            **id_params,
            **queue_params,
            "pending_status": TaskStatus.PENDING.value,
            "ready_frontier_state": "ready",
        }

        with self.get_connection() as conn:
            rows = conn.execute(query, params).fetchall()

        projections_by_id: dict[str, dict[str, Any]] = {}
        for row in rows:
            execution_context = self.deserialize_json(
                getattr(row, "execution_context", None),
                {},
            )
            if not isinstance(execution_context, dict):
                execution_context = {}
            task_id = str(getattr(row, "id", "") or "").strip()
            playbook_code = (
                str(
                    execution_context.get("playbook_code")
                    or getattr(row, "pack_id", "")
                    or ""
                )
                .strip()
                or None
            )
            projections_by_id[task_id] = {
                "task_id": task_id,
                "id": task_id,
                "pack_id": getattr(row, "pack_id", None),
                "playbook_code": playbook_code,
                "task_type": getattr(row, "task_type", None),
                "status": getattr(row, "status", None),
                "frontier_state": getattr(row, "frontier_state", None),
                "queue_shard": getattr(row, "queue_shard", None),
                "execution_context": execution_context,
                "created_at": getattr(row, "created_at", None),
                "frontier_enqueued_at": getattr(row, "frontier_enqueued_at", None),
            }

        return [
            projections_by_id[task_id]
            for task_id in ordered_ids
            if task_id in projections_by_id
        ]

    def count_running_browser_lanes(self, queue_shard: str) -> dict[str, int]:
        from backend.app.runner.browser_fair_candidate_scheduler import (
            normalize_browser_lane_key,
        )

        queue_clause, queue_params = build_queue_partition_filter_clause(
            "queue_shard",
            queue_shard,
            param_prefix="running_queue",
        )
        if not queue_clause:
            return {}

        query = text(
            f"""
            SELECT
                pack_id,
                execution_context->>'playbook_code' AS playbook_code,
                COUNT(*) AS running_count
            FROM tasks
            WHERE task_type IN (:task_type_pb, :task_type_tool)
              AND status = :running_status
              AND {queue_clause}
            GROUP BY pack_id, execution_context->>'playbook_code'
            """
        )
        params: dict[str, Any] = {
            **queue_params,
            "task_type_pb": "playbook_execution",
            "task_type_tool": "tool_execution",
            "running_status": TaskStatus.RUNNING.value,
        }

        counts: dict[str, int] = {}
        with self.get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
        for row in rows:
            lane_key = normalize_browser_lane_key(
                getattr(row, "pack_id", None),
                getattr(row, "playbook_code", None),
            )
            if not lane_key:
                continue
            counts[lane_key] = counts.get(lane_key, 0) + int(
                getattr(row, "running_count", 0) or 0
            )
        return counts

    def list_runnable_playbook_execution_tasks(
        self,
        workspace_id: Optional[str] = None,
        limit: int = 500,
        queue_shard: Optional[str] = None,
    ) -> List[Task]:
        scan_limit = min(max(limit * 64, 512), 4096)
        query_parts = [
            _ADMISSION_RELEASE_CANDIDATE_SELECT,
            """
            WHERE task_type IN (:task_type_pb, :task_type_tool)
            AND status = :status
            AND frontier_state = :frontier_state
            AND COALESCE(next_eligible_at, created_at) <= :now
            AND COALESCE(blocked_reason, '') <> :admission_blocked_reason
            """
        ]
        params: Dict[str, Any] = {
            "task_type_pb": "playbook_execution",
            "task_type_tool": "tool_execution",
            "status": TaskStatus.PENDING.value,
            "frontier_state": "ready",
            "now": datetime.now(timezone.utc),
            "admission_blocked_reason": ADMISSION_DEFERRED_REASON,
        }

        if workspace_id:
            query_parts.append("AND workspace_id = :workspace_id")
            params["workspace_id"] = workspace_id

        if queue_shard:
            queue_clause, queue_params = build_queue_partition_filter_clause(
                "queue_shard",
                queue_shard,
                param_prefix="queue_partition",
            )
            if (
                normalize_queue_partition(queue_shard, fallback=None)
                == BROWSER_LOCAL_QUEUE_PARTITION
            ):
                query_parts.append(
                    f"""
                    AND (
                        {queue_clause}
                        OR (
                            queue_shard IS NULL
                            AND execution_context->>'resource_class' = :legacy_resource_class
                        )
                    )
                    """
                )
                params["legacy_resource_class"] = "browser"
            else:
                query_parts.append(f"AND {queue_clause}")
            params.update(queue_params)

        query_parts.append(
            "ORDER BY frontier_enqueued_at ASC NULLS LAST, created_at ASC, id ASC"
        )
        query_parts.append("LIMIT :limit")
        params["limit"] = scan_limit

        with self.get_connection() as conn:
            rows = conn.execute(text(" ".join(query_parts)), params).fetchall()
            candidates = [
                self._row_to_blocked_release_candidate(row, blocked_reason="")
                for row in rows
            ]

        running_tasks = self.list_running_playbook_execution_tasks(
            workspace_id=None,
            limit=scan_limit,
        )
        active_keys = {
            key
            for task in running_tasks
            if (
                not queue_shard
                or queue_partition_matches(getattr(task, "queue_shard", None), queue_shard)
            )
            for key in [self._resolve_effective_concurrency_key(task)]
            if key
        }

        return self._select_fair_runnable_tasks(
            candidates=candidates,
            limit=limit,
            active_keys=active_keys,
        )
