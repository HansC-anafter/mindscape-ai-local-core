
"""Cold-frontier release read-only query methods for TasksStore."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from app.models.workspace import Task, TaskStatus
from backend.app.services.runner_topology import build_queue_partition_filter_clause

from ._query_common import (
    _ADMISSION_RELEASE_CANDIDATE_SELECT,
    _COLD_RELEASE_CANDIDATE_SELECT_FROM_ALIAS,
    _COLD_RELEASE_COMPACT_CANDIDATE_SELECT_FROM_ALIAS,
    _WORKSPACE_QUOTA_RELEASE_REASONS,
    _cold_release_scan_limit,
)


class TasksStoreColdReleaseQueryMixin:
    """Cold frontier release query methods for scheduler recovery paths."""

    def list_due_concurrency_locked_tasks(
        self,
        *,
        queue_shard: Optional[str] = None,
        limit: int = 200,
    ) -> List[Task]:
        return self._list_ranked_cold_release_candidates(
            blocked_reason="concurrency_locked",
            queue_shard=queue_shard,
            limit=limit,
            include_execution_context=True,
            rank_by_concurrency_key=True,
        )

    def _list_ranked_cold_release_candidates(
        self,
        *,
        blocked_reason: str,
        queue_shard: Optional[str],
        limit: int,
        include_execution_context: bool = True,
        rank_by_concurrency_key: bool = False,
    ) -> List[Task]:
        release_group_sql = (
            "COALESCE(NULLIF(concurrency_key, ''), pack_id)"
            if rank_by_concurrency_key
            else "pack_id"
        )
        query_parts = [
            f"""
            WITH sampled AS (
                SELECT
                    id,
                    pack_id,
                    {release_group_sql} AS release_group,
                    next_eligible_at,
                    created_at
                FROM tasks
                WHERE task_type IN (:task_type_pb, :task_type_tool)
                  AND status = :status
                  AND frontier_state = :frontier_state
                  AND next_eligible_at <= :now
            """,
        ]
        params: Dict[str, Any] = {
            "task_type_pb": "playbook_execution",
            "task_type_tool": "tool_execution",
            "status": TaskStatus.PENDING.value,
            "frontier_state": "cold",
            "now": datetime.now(timezone.utc),
            "limit": limit,
            "scan_limit": _cold_release_scan_limit(limit),
        }

        if blocked_reason:
            query_parts.append("AND blocked_reason = :blocked_reason")
            params["blocked_reason"] = blocked_reason
        else:
            query_parts.append("AND (blocked_reason IS NULL OR blocked_reason = '')")

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
                ORDER BY next_eligible_at ASC, created_at ASC, id ASC
                LIMIT :scan_limit
            ),
            ranked AS (
                SELECT
                    id,
                    ROW_NUMBER() OVER (
                        PARTITION BY release_group
                        ORDER BY next_eligible_at ASC, created_at ASC, id ASC
                    ) AS pack_rank,
                    next_eligible_at,
                    created_at
                FROM sampled
            """,
        )

        query_parts.append(
            """
            ),
            chosen AS (
                SELECT id, pack_rank, next_eligible_at, created_at
                FROM ranked
                ORDER BY pack_rank ASC, next_eligible_at ASC, created_at ASC, id ASC
                LIMIT :limit
            )
            """
        )
        query_parts.append(
            _COLD_RELEASE_CANDIDATE_SELECT_FROM_ALIAS
            if include_execution_context
            else _COLD_RELEASE_COMPACT_CANDIDATE_SELECT_FROM_ALIAS
        )
        query_parts.append(
            "ORDER BY c.pack_rank ASC, c.next_eligible_at ASC, c.created_at ASC, c.id ASC"
        )

        with self.get_connection() as conn:
            rows = conn.execute(text(" ".join(query_parts)), params).fetchall()
            return [
                self._row_to_blocked_release_candidate(
                    row, blocked_reason=blocked_reason
                )
                for row in rows
            ]

    def _list_ranked_cold_release_candidates_for_reasons(
        self,
        *,
        blocked_reasons: list[str],
        queue_shard: Optional[str],
        limit: int,
        include_execution_context: bool = True,
    ) -> List[Task]:
        normalized_reasons = [
            reason.strip()
            for reason in blocked_reasons
            if isinstance(reason, str) and reason.strip()
        ]
        if not normalized_reasons:
            return []

        query_parts = [
            """
            WITH sampled AS (
                SELECT
                    id,
                    pack_id,
                    blocked_reason,
                    next_eligible_at,
                    created_at
                FROM tasks
                WHERE task_type IN (:task_type_pb, :task_type_tool)
                  AND status = :status
                  AND frontier_state = :frontier_state
                  AND next_eligible_at <= :now
            """,
        ]
        params: Dict[str, Any] = {
            "task_type_pb": "playbook_execution",
            "task_type_tool": "tool_execution",
            "status": TaskStatus.PENDING.value,
            "frontier_state": "cold",
            "now": datetime.now(timezone.utc),
            "limit": limit,
            "scan_limit": _cold_release_scan_limit(limit),
        }
        reason_placeholders: list[str] = []
        for index, reason in enumerate(normalized_reasons):
            key = f"blocked_reason_{index}"
            params[key] = reason
            reason_placeholders.append(f":{key}")
        query_parts.append(
            f"AND blocked_reason IN ({', '.join(reason_placeholders)})"
        )

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
                ORDER BY next_eligible_at ASC, created_at ASC, id ASC
                LIMIT :scan_limit
            ),
            ranked AS (
                SELECT
                    id,
                    blocked_reason,
                    ROW_NUMBER() OVER (
                        PARTITION BY pack_id
                        ORDER BY next_eligible_at ASC, created_at ASC, id ASC
                    ) AS pack_rank,
                    next_eligible_at,
                    created_at
                FROM sampled
            ),
            chosen AS (
                SELECT id, blocked_reason, pack_rank, next_eligible_at, created_at
                FROM ranked
                ORDER BY pack_rank ASC, next_eligible_at ASC, created_at ASC, id ASC
                LIMIT :limit
            )
            """
        )
        query_parts.append(
            _COLD_RELEASE_CANDIDATE_SELECT_FROM_ALIAS
            if include_execution_context
            else _COLD_RELEASE_COMPACT_CANDIDATE_SELECT_FROM_ALIAS
        )
        query_parts.append(
            "ORDER BY c.pack_rank ASC, c.next_eligible_at ASC, c.created_at ASC, c.id ASC"
        )

        with self.get_connection() as conn:
            rows = conn.execute(text(" ".join(query_parts)), params).fetchall()
            return [
                self._row_to_blocked_release_candidate(
                    row,
                    blocked_reason=str(
                        getattr(row, "blocked_reason", "") or ""
                    ).strip(),
                )
                for row in rows
            ]

    def _list_ordered_cold_release_candidates(
        self,
        *,
        blocked_reason: str,
        queue_shard: Optional[str],
        limit: int,
        include_execution_context: bool = True,
    ) -> List[Task]:
        query_parts = [
            """
            WITH chosen AS (
                SELECT id, next_eligible_at, created_at
                FROM tasks
            WHERE task_type IN (:task_type_pb, :task_type_tool)
              AND status = :status
              AND blocked_reason = :blocked_reason
              AND frontier_state = :frontier_state
              AND next_eligible_at <= :now
            """,
        ]
        params: Dict[str, Any] = {
            "task_type_pb": "playbook_execution",
            "task_type_tool": "tool_execution",
            "status": TaskStatus.PENDING.value,
            "blocked_reason": blocked_reason,
            "frontier_state": "cold",
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
                ORDER BY next_eligible_at ASC, created_at ASC, id ASC
                LIMIT :limit
            )
            """
        )
        query_parts.append(
            _COLD_RELEASE_CANDIDATE_SELECT_FROM_ALIAS
            if include_execution_context
            else _COLD_RELEASE_COMPACT_CANDIDATE_SELECT_FROM_ALIAS
        )
        query_parts.append("ORDER BY c.next_eligible_at ASC, c.created_at ASC, c.id ASC")

        with self.get_connection() as conn:
            rows = conn.execute(text(" ".join(query_parts)), params).fetchall()
            return [
                self._row_to_blocked_release_candidate(
                    row, blocked_reason=blocked_reason
                )
                for row in rows
            ]

    def list_due_dependency_hold_tasks(
        self,
        *,
        queue_shard: Optional[str] = None,
        limit: int = 200,
    ) -> List[Task]:
        return self._list_ordered_cold_release_candidates(
            blocked_reason="dependency_hold",
            queue_shard=queue_shard,
            limit=limit,
            include_execution_context=False,
        )

    def list_due_resource_wait_tasks(
        self,
        *,
        queue_shard: Optional[str] = None,
        limit: int = 200,
    ) -> List[Task]:
        return self._list_ranked_cold_release_candidates(
            blocked_reason="resource_wait",
            queue_shard=queue_shard,
            limit=limit,
        )

    def list_due_workspace_quota_tasks(
        self,
        *,
        queue_shard: Optional[str] = None,
        limit: int = 200,
    ) -> List[Task]:
        return self._list_ranked_cold_release_candidates_for_reasons(
            blocked_reasons=list(_WORKSPACE_QUOTA_RELEASE_REASONS),
            queue_shard=queue_shard,
            limit=limit,
        )

    def count_ready_workspace_quota_tasks(
        self,
        *,
        workspace_id: str,
        queue_shard: str,
        selectors: list[str],
    ) -> int:
        selector_clauses: list[str] = []
        params: Dict[str, Any] = {
            "workspace_id": workspace_id,
            "status": TaskStatus.PENDING.value,
            "frontier_state": "ready",
        }

        queue_clause, queue_params = build_queue_partition_filter_clause(
            "queue_shard",
            queue_shard,
            param_prefix="queue_partition",
        )
        params.update(queue_params)

        if selectors:
            selector_params: Dict[str, Any] = {}
            placeholders: list[str] = []
            for index, selector in enumerate(selectors):
                key = f"selector_{index}"
                selector_params[key] = selector
                placeholders.append(f":{key}")
            params.update(selector_params)
            selector_list = ", ".join(placeholders)
            selector_clauses.append(
                f"""
                (
                    pack_id IN ({selector_list})
                    OR execution_context->>'playbook_code' IN ({selector_list})
                    OR task_type IN ({selector_list})
                )
                """
            )

        selector_sql = (
            f"AND {' AND '.join(selector_clauses)}" if selector_clauses else ""
        )
        with self.get_connection() as conn:
            value = conn.execute(
                text(
                    f"""
                    SELECT COUNT(*)::int
                    FROM tasks
                    WHERE workspace_id = :workspace_id
                      AND {queue_clause}
                      AND status = :status
                      AND frontier_state = :frontier_state
                      AND (blocked_reason IS NULL OR blocked_reason = '')
                      {selector_sql}
                    """
                ),
                params,
            ).scalar()
        try:
            return int(value or 0)
        except Exception:
            return 0

    def list_due_unblocked_cold_tasks(
        self,
        *,
        queue_shard: Optional[str] = None,
        limit: int = 200,
    ) -> List[Task]:
        return self._list_ranked_cold_release_candidates(
            blocked_reason="",
            queue_shard=queue_shard,
            limit=limit,
            include_execution_context=False,
        )

    def _list_due_blocked_cold_tasks(
        self,
        *,
        blocked_reason: str,
        queue_shard: Optional[str],
        limit: int,
    ) -> List[Task]:
        query_parts = [
            _ADMISSION_RELEASE_CANDIDATE_SELECT,
            """
            WHERE task_type IN (:task_type_pb, :task_type_tool)
              AND status = :status
              AND blocked_reason = :blocked_reason
              AND frontier_state = :frontier_state
              AND next_eligible_at <= :now
            """,
        ]
        params: Dict[str, Any] = {
            "task_type_pb": "playbook_execution",
            "task_type_tool": "tool_execution",
            "status": TaskStatus.PENDING.value,
            "blocked_reason": blocked_reason,
            "frontier_state": "cold",
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

        query_parts.append("ORDER BY next_eligible_at ASC, created_at ASC, id ASC")
        query_parts.append("LIMIT :limit")

        with self.get_connection() as conn:
            rows = conn.execute(text(" ".join(query_parts)), params).fetchall()
            return [
                self._row_to_blocked_release_candidate(
                    row, blocked_reason=blocked_reason
                )
                for row in rows
            ]
