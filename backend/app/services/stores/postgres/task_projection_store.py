"""Postgres read store for task summary projections."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from app.models.workspace import Task, TaskStatus

from ..postgres_base import PostgresStoreBase


_TERMINAL_TASK_STATUSES = {
    TaskStatus.SUCCEEDED.value,
    TaskStatus.FAILED.value,
    TaskStatus.CANCELLED_BY_USER.value,
    TaskStatus.EXPIRED.value,
}


def _frontier_state_for_status(status: str) -> str:
    if status == TaskStatus.RUNNING.value:
        return "running"
    if status in _TERMINAL_TASK_STATUSES:
        return "done"
    return "ready"


class TasksProjectionStore(PostgresStoreBase):
    """Read compact workspace task lists from projection tables."""

    def list_workspace_tasks(
        self,
        workspace_id: str,
        limit: int,
        include_completed: bool = False,
        task_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        normalized_task_type = (task_type or "").strip().lower()
        normalized_limit = max(1, min(100, int(limit or 20)))

        clauses = ["workspace_id = :workspace_id"]
        params: Dict[str, Any] = {
            "workspace_id": workspace_id,
            "limit": normalized_limit,
        }

        if not include_completed:
            clauses.append("status IN (:pending_status, :running_status)")
            params["pending_status"] = TaskStatus.PENDING.value
            params["running_status"] = TaskStatus.RUNNING.value

        if normalized_task_type == "execution":
            clauses.append("execution_id IS NOT NULL")
        elif normalized_task_type:
            clauses.append("task_type = :task_type")
            params["task_type"] = normalized_task_type

        order_clause = self._order_clause(
            include_completed=include_completed,
            normalized_task_type=normalized_task_type,
        )
        query = text(
            f"""
            SELECT
                task_id,
                workspace_id,
                execution_id,
                parent_execution_id,
                project_id,
                pack_id,
                task_type,
                status,
                queue_shard,
                dedupe_key,
                summary,
                error_summary,
                created_at,
                next_eligible_at,
                blocked_reason,
                frontier_state,
                frontier_enqueued_at,
                started_at,
                completed_at,
                updated_at,
                last_event_at
            FROM task_summary_projection
            WHERE {" AND ".join(clauses)}
            {order_clause}
            LIMIT :limit
            """
        )
        with self.get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_task_payload(row) for row in rows]

    def count_workspace_tasks(
        self,
        workspace_id: str,
        *,
        task_type: Optional[str] = None,
    ) -> int:
        normalized_task_type = (task_type or "").strip().lower()
        clauses = ["workspace_id = :workspace_id"]
        params: Dict[str, Any] = {"workspace_id": workspace_id}
        if normalized_task_type == "execution":
            clauses.append("execution_id IS NOT NULL")
        elif normalized_task_type:
            clauses.append("task_type = :task_type")
            params["task_type"] = normalized_task_type
        query = text(
            f"""
            SELECT COUNT(*) AS count
            FROM task_summary_projection
            WHERE {" AND ".join(clauses)}
            """
        )
        with self.get_connection() as conn:
            row = conn.execute(query, params).fetchone()
            return int(row.count if row is not None else 0)

    def _order_clause(
        self,
        *,
        include_completed: bool,
        normalized_task_type: str,
    ) -> str:
        if normalized_task_type == "execution":
            return "ORDER BY created_at DESC NULLS LAST, task_id DESC"
        if include_completed:
            return (
                "ORDER BY CASE WHEN status = 'running' THEN 0 ELSE 1 END, "
                "created_at DESC NULLS LAST, updated_at DESC, task_id DESC"
            )
        return (
            "ORDER BY CASE "
            "WHEN status = 'pending' THEN 0 "
            "WHEN status = 'running' THEN 1 "
            "ELSE 2 END, "
            "created_at DESC NULLS LAST, updated_at DESC, task_id DESC"
        )

    def _row_to_task_payload(self, row) -> Dict[str, Any]:
        mapping = row._mapping if hasattr(row, "_mapping") else row
        status = str(mapping["status"])
        task = Task(
            id=mapping["task_id"],
            workspace_id=mapping["workspace_id"],
            message_id=mapping["task_id"],
            execution_id=mapping["execution_id"],
            parent_execution_id=mapping["parent_execution_id"],
            project_id=mapping["project_id"],
            pack_id=mapping["pack_id"] or "",
            task_type=mapping["task_type"],
            status=TaskStatus(status),
            params={},
            result=None,
            execution_context=self._compact_execution_context(mapping),
            meeting_session_id=None,
            storyline_tags=[],
            created_at=self._datetime_or_now(mapping["created_at"]),
            next_eligible_at=self._datetime_or_now(mapping["next_eligible_at"]),
            blocked_reason=mapping["blocked_reason"],
            blocked_payload=None,
            queue_shard=mapping["queue_shard"] or "default",
            concurrency_key=mapping["dedupe_key"],
            frontier_state=(
                mapping["frontier_state"] or _frontier_state_for_status(status)
            ),
            frontier_enqueued_at=mapping["frontier_enqueued_at"],
            runner_id=None,
            heartbeat_at=None,
            started_at=mapping["started_at"],
            completed_at=mapping["completed_at"],
            error=mapping["error_summary"],
        )
        payload = task.model_dump()
        payload["summary"] = mapping["summary"]
        payload["updated_at"] = mapping["updated_at"]
        payload["last_event_at"] = mapping["last_event_at"]
        return payload

    def _compact_execution_context(self, mapping) -> Dict[str, Any]:
        context = {
            "project_id": mapping["project_id"],
            "status": mapping["status"],
            "summary": mapping["summary"],
        }
        return {key: value for key, value in context.items() if value is not None}

    def _datetime_or_now(self, value: Optional[datetime]) -> datetime:
        if isinstance(value, datetime):
            return value
        return datetime.now(timezone.utc)
