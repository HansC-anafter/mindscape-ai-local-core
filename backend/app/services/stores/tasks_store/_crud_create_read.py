"""Create and direct lookup methods for TasksStore CRUD."""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import text

from app.models.workspace import Task
from backend.app.services.meeting_command_status_sync import (
    sync_meeting_command_from_task_safely,
)
from backend.app.services.task_admission_service import (
    ADMISSION_DEFERRED_REASON,
    TASK_ADMISSION_SERVICE,
)
from backend.app.services.task_payload_budget import apply_task_payload_budget

from ._crud_helpers import _derive_scheduler_fields, _enrich_runner_task_context

logger = logging.getLogger(__name__)


class TasksStoreCreateReadMixin:
    """Task create and direct read methods."""

    def create_task(self, task: Task) -> Task:
        """
        Create a new task record

        Args:
            task: Task model instance

        Returns:
            Created task
        """
        _enrich_runner_task_context(task)
        scheduler_fields = _derive_scheduler_fields(task)
        for key, value in scheduler_fields.items():
            setattr(task, key, value)

        admission_decision = TASK_ADMISSION_SERVICE.evaluate_on_create(self, task)
        if not admission_decision.allow:
            task.execution_context = admission_decision.execution_context
            task.next_eligible_at = admission_decision.next_eligible_at or task.next_eligible_at
            task.blocked_reason = ADMISSION_DEFERRED_REASON
            task.blocked_payload = admission_decision.blocked_payload
            task.frontier_state = "cold"
            task.frontier_enqueued_at = None
            task.queue_shard = admission_decision.queue_shard or task.queue_shard

        with self.transaction() as conn:
            project_id = task.project_id
            if not project_id and task.execution_context:
                project_id = task.execution_context.get("project_id")
            if not project_id and task.params:
                project_id = task.params.get("project_id")

            query = text(
                """
                INSERT INTO tasks (
                    id, workspace_id, message_id, execution_id, parent_execution_id,
                    project_id, pack_id,
                    task_type, status, params, result, execution_context,
                    meeting_session_id,
                    storyline_tags, created_at, next_eligible_at, blocked_reason,
                    blocked_payload, queue_shard, concurrency_key, frontier_state,
                    frontier_enqueued_at, started_at, completed_at, error
                ) VALUES (
                    :id, :workspace_id, :message_id, :execution_id, :parent_execution_id,
                    :project_id, :pack_id,
                    :task_type, :status, :params, :result, :execution_context,
                    :meeting_session_id,
                    :storyline_tags, :created_at, :next_eligible_at, :blocked_reason,
                    :blocked_payload, :queue_shard, :concurrency_key, :frontier_state,
                    :frontier_enqueued_at, :started_at, :completed_at, :error
                )
            """
            )
            # Auto-inject parent_execution_id from ContextVar if not set
            resolved_parent_id = getattr(task, "parent_execution_id", None)
            if not resolved_parent_id:
                try:
                    from backend.app.services.parameter_adapter.context import (
                        active_parent_execution_id,
                    )
                    ctx_parent = active_parent_execution_id.get()
                    # Pre-mortem guard: prevent self-parenting
                    if ctx_parent and ctx_parent != task.execution_id:
                        resolved_parent_id = ctx_parent
                except Exception:
                    pass  # ContextVar not available — safe to ignore

            task_params = apply_task_payload_budget("params", task.params)
            task_result = apply_task_payload_budget("result", task.result)
            task_execution_context = apply_task_payload_budget(
                "execution_context",
                task.execution_context,
            )
            task_blocked_payload = apply_task_payload_budget(
                "blocked_payload",
                task.blocked_payload,
            )

            params = {
                "id": task.id,
                "workspace_id": task.workspace_id,
                "message_id": task.message_id,
                "execution_id": task.execution_id,
                "parent_execution_id": resolved_parent_id,
                "project_id": project_id,
                "pack_id": task.pack_id,
                "task_type": task.task_type,
                "status": task.status.value,
                "params": self.serialize_json(task_params),
                "result": self.serialize_json(task_result),
                "execution_context": (
                    self.serialize_json(task_execution_context)
                    if task_execution_context
                    else None
                ),
                "meeting_session_id": task.meeting_session_id,
                "storyline_tags": self.serialize_json(task.storyline_tags),
                "created_at": task.created_at,
                "next_eligible_at": task.next_eligible_at,
                "blocked_reason": task.blocked_reason,
                "blocked_payload": self.serialize_json(task_blocked_payload),
                "queue_shard": task.queue_shard,
                "concurrency_key": task.concurrency_key,
                "frontier_state": task.frontier_state,
                "frontier_enqueued_at": task.frontier_enqueued_at,
                "started_at": task.started_at,
                "completed_at": task.completed_at,
                "error": task.error,
            }
            conn.execute(query, params)
            if task.task_type in ("playbook_execution", "tool_execution"):
                self._sync_playbook_execution_status(
                    conn,
                    task.execution_id,
                    task.status,
                    task_execution_context,
                )
            task.parent_execution_id = resolved_parent_id
            run_id = self._record_run_control_from_task(conn, task)
            self._record_task_control_event(
                conn,
                task_id=task.id,
                workspace_id=task.workspace_id,
                event_type="task.created",
                to_status=task.status.value,
                run_id=run_id,
                payload={
                    "pack_id": task.pack_id,
                    "task_type": task.task_type,
                    "queue_shard": task.queue_shard,
                },
                idempotency_key=f"task:{task.id}:created",
                occurred_at=task.created_at,
            )
            self._refresh_task_projection(conn, task.id)
            logger.info(
                "Created task: %s (workspace: %s, pack: %s)",
                task.id,
                task.workspace_id,
                task.pack_id,
            )

        sync_meeting_command_from_task_safely(task)
        self._enqueue_runner_task_after_commit(task)
        return task

    def get_task(self, task_id: str) -> Optional[Task]:
        """
        Get task by ID

        Args:
            task_id: Task ID

        Returns:
            Task model or None if not found
        """
        with self.get_connection() as conn:
            query = text("SELECT * FROM tasks WHERE id = :task_id")
            row = conn.execute(query, {"task_id": task_id}).fetchone()
            if not row:
                return None
            return self._row_to_task(row)

    def get_task_by_execution_id(self, execution_id: str) -> Optional[Task]:
        """
        Get task by execution_id

        Args:
            execution_id: Execution ID

        Returns:
            Task model or None if not found
        """
        with self.get_connection() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT * FROM tasks
                    WHERE execution_id = :execution_id
                    ORDER BY created_at DESC
                    LIMIT 1
                """
                ),
                {"execution_id": execution_id},
            ).fetchone()
            if not row:
                row = conn.execute(
                    text(
                        """
                        SELECT * FROM tasks
                        WHERE id = :execution_id
                        ORDER BY created_at DESC
                        LIMIT 1
                    """
                    ),
                    {"execution_id": execution_id},
                ).fetchone()
                if not row:
                    return None
            return self._row_to_task(row)
