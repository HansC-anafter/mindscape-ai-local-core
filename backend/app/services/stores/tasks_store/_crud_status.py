"""Status update method for TasksStore CRUD."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import text

from app.models.workspace import Task, TaskStatus
from app.services.stores.base import StoreNotFoundError
from backend.app.services.meeting_command_status_sync import (
    sync_meeting_command_from_task_safely,
)
from backend.app.services.task_payload_budget import apply_task_payload_budget

from ._crud_control import _publish_terminal_event
from ._crud_helpers import (
    _RUNNER_TASK_TYPES,
    _TERMINAL_TASK_STATUSES,
    _coerce_task_status,
    _normalize_frontier_updates_for_status,
    _parse_resume_after,
    _utc_now,
)

logger = logging.getLogger(__name__)


class TasksStoreStatusUpdateMixin:
    """Task status update method."""

    def update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
    ) -> Task:
        """
        Update task status and related fields

        Args:
            task_id: Task ID
            status: New status
            result: Task result (optional)
            error: Error message (optional)
            started_at: Start timestamp (optional)
            completed_at: Completion timestamp (optional)

        Returns:
            Updated task when requested

        Raises:
            StoreNotFoundError: If task not found
        """
        updates = ["status = :status"]
        params: Dict[str, Any] = {"status": status.value, "task_id": task_id}

        if status == TaskStatus.RUNNING:
            updates.extend(
                [
                    "blocked_reason = NULL",
                    "blocked_payload = NULL",
                    "frontier_state = :frontier_state",
                    "frontier_enqueued_at = NULL",
                ]
            )
            params["frontier_state"] = "running"
        elif status.value in _TERMINAL_TASK_STATUSES:
            updates.extend(
                [
                    "blocked_reason = NULL",
                    "blocked_payload = NULL",
                    "runner_id = NULL",
                    "heartbeat_at = NULL",
                    "frontier_state = :frontier_state",
                    "frontier_enqueued_at = NULL",
                ]
            )
            params["frontier_state"] = "done"

        if result is not None:
            updates.append("result = :result")
            params["result"] = self.serialize_json(
                apply_task_payload_budget("result", result)
            )

        if error is not None:
            updates.append("error = :error")
            params["error"] = error

        if started_at is not None:
            updates.append("started_at = :started_at")
            params["started_at"] = started_at

        if completed_at is not None:
            updates.append("completed_at = :completed_at")
            params["completed_at"] = completed_at

        status_transition_changed = False
        with self.transaction() as conn:
            lock_clause = (
                " FOR UPDATE"
                if getattr(getattr(conn, "dialect", None), "name", "")
                == "postgresql"
                else ""
            )
            existing_row = conn.execute(
                text(
                    """
                    SELECT
                        status,
                        pack_id,
                        task_type,
                        created_at,
                        next_eligible_at,
                        blocked_reason,
                        frontier_state,
                        frontier_enqueued_at
                    FROM tasks
                    WHERE id = :task_id
                    """
                    + lock_clause
                ),
                {"task_id": task_id},
            ).fetchone()
            existing_status = None
            if existing_row:
                existing_status = (
                    existing_row._mapping["status"]
                    if hasattr(existing_row, "_mapping")
                    else existing_row[0]
                )
            status_transition_changed = existing_status != status.value
            query = text(f"UPDATE tasks SET {', '.join(updates)} WHERE id = :task_id")
            result_row = conn.execute(query, params)
            if result_row.rowcount == 0:
                raise StoreNotFoundError(f"Task not found: {task_id}")

            # Sync playbook_executions status only for a real transition.
            if status_transition_changed:
                try:
                    row = conn.execute(
                        text(
                            "SELECT execution_id, execution_context "
                            "FROM tasks WHERE id = :task_id"
                        ),
                        {"task_id": task_id},
                    ).fetchone()
                    if row:
                        execution_id = (
                            row._mapping["execution_id"]
                            if hasattr(row, "_mapping")
                            else row[0]
                        )
                        execution_context = self.deserialize_json(
                            row._mapping["execution_context"]
                            if hasattr(row, "_mapping")
                            else row[1]
                        )
                        self._sync_playbook_execution_status(
                            conn, execution_id, status, execution_context
                        )
                except Exception:
                    pass

            control_row = conn.execute(
                text(
                    """
                    SELECT workspace_id, execution_id, pack_id, started_at, completed_at
                    FROM tasks
                    WHERE id = :task_id
                    """
                ),
                {"task_id": task_id},
            ).fetchone()
            if control_row and status_transition_changed:
                mapping = (
                    control_row._mapping
                    if hasattr(control_row, "_mapping")
                    else None
                )
                workspace_id = (
                    mapping["workspace_id"] if mapping is not None else control_row[0]
                )
                execution_id = (
                    mapping["execution_id"] if mapping is not None else control_row[1]
                )
                pack_id = mapping["pack_id"] if mapping is not None else control_row[2]
                persisted_started_at = (
                    mapping["started_at"] if mapping is not None else control_row[3]
                )
                persisted_completed_at = (
                    mapping["completed_at"] if mapping is not None else control_row[4]
                )
                event_time = completed_at or started_at or _utc_now()
                run_id = self._run_id_for_task(task_id, execution_id)
                self._run_attempts_store().upsert_run(
                    run_id=run_id,
                    execution_id=execution_id or task_id,
                    workspace_id=workspace_id,
                    task_id=task_id,
                    pack_id=pack_id,
                    status=status.value,
                    started_at=persisted_started_at,
                    completed_at=persisted_completed_at,
                    conn=conn,
                )
                attempt_id = None
                if status.value in _TERMINAL_TASK_STATUSES:
                    attempt_id = self._record_latest_attempt_completion(
                        conn,
                        task_id=task_id,
                        status=status.value,
                        completed_at=persisted_completed_at or completed_at,
                        error_summary=error,
                    )
                self._record_task_control_event(
                    conn,
                    task_id=task_id,
                    workspace_id=workspace_id,
                    event_type="task.status_changed",
                    from_status=existing_status,
                    to_status=status.value,
                    run_id=run_id,
                    attempt_id=attempt_id,
                    summary=error,
                    payload={"has_result": result is not None},
                    idempotency_key=(
                        f"task:{task_id}:status:{status.value}:{event_time.isoformat()}"
                    ),
                    occurred_at=event_time,
                )
            if control_row:
                self._refresh_task_projection(conn, task_id)

            logger.info("Updated task %s status to %s", task_id, status.value)

        updated_task = self.get_task(task_id)
        sync_meeting_command_from_task_safely(updated_task)
        # Activity stream: push terminal status change
        if status_transition_changed:
            _publish_terminal_event(task_id, status.value, updated_task)

        return updated_task
