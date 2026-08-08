"""Field update method for TasksStore CRUD."""

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
from backend.app.services.task_projection_adapters import project_task_identity

from ._crud_control import _publish_terminal_event
from ._crud_helpers import (
    _RUNNER_TASK_TYPES,
    _TERMINAL_TASK_STATUSES,
    coerce_task_status_enum,
    _coerce_task_status,
    _normalize_frontier_updates_for_status,
    _parse_resume_after,
    _utc_now,
)

logger = logging.getLogger(__name__)


_TASK_SUMMARY_PROJECTION_FIELDS = frozenset(
    {
        "workspace_id",
        "execution_id",
        "parent_execution_id",
        "pack_id",
        "task_type",
        "status",
        "queue_shard",
        "concurrency_key",
        "error",
        "created_at",
        "next_eligible_at",
        "blocked_reason",
        "frontier_state",
        "frontier_enqueued_at",
        "started_at",
        "completed_at",
    }
)


class TasksStoreUpdateMixin:
    """Task field update method."""

    def update_task(
        self,
        task_id: str,
        execution_context: Optional[Dict[str, Any]] = None,
        project_id: Optional[str] = None,
        *,
        return_updated: bool = True,
        expected_statuses: Optional[tuple[TaskStatus, ...]] = None,
        **kwargs,
    ) -> Optional[Task]:
        """
        Update task fields

        Args:
            task_id: Task ID
            execution_context: Execution context dict to update
            **kwargs: Other fields to update

        Returns:
            Updated task

        Raises:
            StoreNotFoundError: If task not found
        """
        kwargs = _normalize_frontier_updates_for_status(kwargs)

        updates = []
        params: Dict[str, Any] = {"task_id": task_id}

        if execution_context is not None:
            updates.append("execution_context = :execution_context")
            params["execution_context"] = self.serialize_json(
                apply_task_payload_budget("execution_context", execution_context)
            )
            if project_id is None and execution_context.get("project_id"):
                project_id = execution_context.get("project_id")

        if project_id is not None:
            updates.append("project_id = :project_id")
            params["project_id"] = project_id

        for key, value in kwargs.items():
            if key in ["params", "result", "storyline_tags", "blocked_payload"]:
                updates.append(f"{key} = :{key}")
                if key in ["params", "result", "storyline_tags", "blocked_payload"]:
                    value = apply_task_payload_budget(key, value)
                params[key] = self.serialize_json(value)
            elif key in ["status"]:
                updates.append(f"{key} = :{key}")
                params[key] = value.value if hasattr(value, "value") else value
            elif key in [
                "started_at",
                "completed_at",
                "created_at",
                "next_eligible_at",
                "frontier_enqueued_at",
                "heartbeat_at",
            ]:
                updates.append(f"{key} = :{key}")
                params[key] = value
            else:
                updates.append(f"{key} = :{key}")
                params[key] = value

        if not updates:
            return self.get_task(task_id)

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
            existing_mapping = None
            if existing_row:
                existing_mapping = (
                    existing_row._mapping if hasattr(existing_row, "_mapping") else None
                )
                existing_status = (
                    existing_mapping["status"]
                    if existing_mapping is not None
                    else existing_row[0]
                )
            if expected_statuses is not None and existing_status not in {
                item.value for item in expected_statuses
            }:
                return None
            requested_status = kwargs.get("status")
            if requested_status is not None:
                requested_status_raw = (
                    requested_status.value
                    if hasattr(requested_status, "value")
                    else str(requested_status)
                )
                status_transition_changed = (
                    existing_status != requested_status_raw
                )
            if execution_context is not None and existing_row:
                explicit_update_keys = set(kwargs.keys())
                status_source = kwargs.get("status", existing_status)
                status_raw = _coerce_task_status(status_source)
                existing_task_type = (
                    existing_mapping["task_type"]
                    if existing_mapping is not None
                    else existing_row[2]
                )
                if (
                    existing_task_type in _RUNNER_TASK_TYPES
                    and status_raw == TaskStatus.PENDING.value
                ):
                    now = _utc_now()
                    existing_next_eligible_at = self._coerce_datetime(
                        existing_mapping["next_eligible_at"]
                        if existing_mapping is not None
                        else existing_row[4]
                    )
                    effective_next_eligible_at = existing_next_eligible_at
                    parsed_resume_after = _parse_resume_after(
                        execution_context.get("resume_after")
                    )
                    if (
                        parsed_resume_after is not None
                        and "next_eligible_at" not in explicit_update_keys
                    ):
                        updates.append("next_eligible_at = :next_eligible_at")
                        params["next_eligible_at"] = parsed_resume_after
                        effective_next_eligible_at = parsed_resume_after

                    existing_blocked_reason = (
                        existing_mapping["blocked_reason"]
                        if existing_mapping is not None
                        else existing_row[5]
                    )
                    effective_blocked_reason = existing_blocked_reason
                    derived_blocked_reason = execution_context.get("runner_skip_reason")
                    if (
                        not derived_blocked_reason
                        and isinstance(execution_context.get("dependency_hold"), dict)
                    ):
                        derived_blocked_reason = "dependency_hold"
                    if (
                        derived_blocked_reason
                        and "blocked_reason" not in explicit_update_keys
                    ):
                        updates.append("blocked_reason = :blocked_reason")
                        params["blocked_reason"] = derived_blocked_reason
                        effective_blocked_reason = derived_blocked_reason

                    if effective_blocked_reason:
                        derived_frontier_state = "cold"
                    elif effective_next_eligible_at and effective_next_eligible_at > now:
                        derived_frontier_state = "cold"
                    else:
                        derived_frontier_state = "ready"

                    if "frontier_state" not in explicit_update_keys:
                        updates.append("frontier_state = :frontier_state")
                        params["frontier_state"] = derived_frontier_state

                    if "frontier_enqueued_at" not in explicit_update_keys:
                        existing_frontier_enqueued_at = self._coerce_datetime(
                            existing_mapping["frontier_enqueued_at"]
                            if existing_mapping is not None
                            else existing_row[7]
                        )
                        existing_created_at = self._coerce_datetime(
                            existing_mapping["created_at"]
                            if existing_mapping is not None
                            else existing_row[3]
                        )
                        if derived_frontier_state == "ready":
                            frontier_enqueued_at = (
                                existing_frontier_enqueued_at
                                or existing_created_at
                                or now
                            )
                        else:
                            frontier_enqueued_at = None
                        updates.append("frontier_enqueued_at = :frontier_enqueued_at")
                        params["frontier_enqueued_at"] = frontier_enqueued_at
            query = text(f"UPDATE tasks SET {', '.join(updates)} WHERE id = :task_id")
            result_row = conn.execute(query, params)
            if result_row.rowcount == 0:
                raise StoreNotFoundError(f"Task not found: {task_id}")

            identity_keys = {"params", "execution_context", "pack_id"}
            identity_projection_changed = bool(
                execution_context is not None or identity_keys.intersection(kwargs)
            )
            if identity_projection_changed:
                identity_row = conn.execute(
                    text("SELECT * FROM tasks WHERE id = :task_id"),
                    {"task_id": task_id},
                ).fetchone()
                if identity_row is not None:
                    project_task_identity(
                        conn=conn,
                        task=self._row_to_task(identity_row),
                        reason="identity_changed",
                    )

            # Sync playbook_executions status when task status is set.
            try:
                status_val = kwargs.get("status")
                if status_val is not None and status_transition_changed:
                    status_obj = coerce_task_status_enum(status_val)
                    row = conn.execute(
                        text("SELECT execution_id FROM tasks WHERE id = :task_id"),
                        {"task_id": task_id},
                    ).fetchone()
                    execution_id = None
                    if row:
                        execution_id = (
                            row._mapping["execution_id"]
                            if hasattr(row, "_mapping")
                            else row[0]
                        )
                    self._sync_playbook_execution_status(
                        conn, execution_id, status_obj, execution_context
                    )
            except Exception:
                pass

            status_val = kwargs.get("status")
            should_refresh_projection = (
                project_id is not None
                or bool(_TASK_SUMMARY_PROJECTION_FIELDS.intersection(kwargs))
                or identity_projection_changed
            )
            if status_val is not None and status_transition_changed:
                status_raw = (
                    status_val.value if hasattr(status_val, "value") else str(status_val)
                )
                control_row = conn.execute(
                    text(
                        """
                        SELECT workspace_id, execution_id, pack_id, started_at, completed_at, error
                        FROM tasks
                        WHERE id = :task_id
                        """
                    ),
                    {"task_id": task_id},
                ).fetchone()
                if control_row:
                    mapping = (
                        control_row._mapping
                        if hasattr(control_row, "_mapping")
                        else None
                    )
                    workspace_id = (
                        mapping["workspace_id"]
                        if mapping is not None
                        else control_row[0]
                    )
                    execution_id = (
                        mapping["execution_id"]
                        if mapping is not None
                        else control_row[1]
                    )
                    pack_id = (
                        mapping["pack_id"] if mapping is not None else control_row[2]
                    )
                    persisted_started_at = (
                        mapping["started_at"] if mapping is not None else control_row[3]
                    )
                    persisted_completed_at = (
                        mapping["completed_at"]
                        if mapping is not None
                        else control_row[4]
                    )
                    persisted_error = (
                        mapping["error"] if mapping is not None else control_row[5]
                    )
                    event_time = persisted_completed_at or persisted_started_at or _utc_now()
                    run_id = self._run_id_for_task(task_id, execution_id)
                    self._run_attempts_store().upsert_run(
                        run_id=run_id,
                        execution_id=execution_id or task_id,
                        workspace_id=workspace_id,
                        task_id=task_id,
                        pack_id=pack_id,
                        status=status_raw,
                        started_at=persisted_started_at,
                        completed_at=persisted_completed_at,
                        conn=conn,
                    )
                    attempt_id = None
                    if status_raw in _TERMINAL_TASK_STATUSES:
                        attempt_id = self._record_latest_attempt_completion(
                            conn,
                            task_id=task_id,
                            status=status_raw,
                            completed_at=persisted_completed_at,
                            error_summary=persisted_error,
                        )
                    self._record_task_control_event(
                        conn,
                        task_id=task_id,
                        workspace_id=workspace_id,
                        event_type="task.status_changed",
                        from_status=existing_status,
                        to_status=status_raw,
                        run_id=run_id,
                        attempt_id=attempt_id,
                        summary=persisted_error,
                        payload={"source": "update_task"},
                        idempotency_key=(
                            f"task:{task_id}:update_status:{status_raw}:{event_time.isoformat()}"
                        ),
                        occurred_at=event_time,
                    )
                    should_refresh_projection = True
            if should_refresh_projection:
                self._refresh_task_projection(
                    conn,
                    task_id,
                    refresh_compact_inputs=identity_projection_changed,
                )

            logger.debug("Updated task %s", task_id)

        updated_task = self.get_task(task_id) if return_updated else None
        if updated_task is not None:
            sync_meeting_command_from_task_safely(updated_task)
        # Activity stream: push terminal status change
        status_val = kwargs.get("status")
        if status_val is not None and status_transition_changed:
            raw = status_val.value if hasattr(status_val, "value") else str(status_val)
            _publish_terminal_event(task_id, raw, updated_task)

        return updated_task

    def try_resume_resource_block(
        self,
        task_id: str,
        *,
        expected_blocked_reason: str,
        execution_context: Dict[str, Any],
        resumed_at: datetime,
    ) -> bool:
        """Atomically move one still-blocked task back to the runnable frontier."""
        serialized_context = self.serialize_json(
            apply_task_payload_budget("execution_context", execution_context)
        )
        with self.transaction() as conn:
            result = conn.execute(
                text(
                    """
                    UPDATE tasks
                    SET execution_context = :execution_context,
                        blocked_reason = NULL,
                        blocked_payload = NULL,
                        next_eligible_at = :resumed_at,
                        frontier_state = 'ready',
                        frontier_enqueued_at = :resumed_at,
                        runner_id = NULL,
                        heartbeat_at = NULL
                    WHERE id = :task_id
                      AND status = :pending_status
                      AND frontier_state = 'cold'
                      AND blocked_reason = :expected_blocked_reason
                    """
                ),
                {
                    "task_id": task_id,
                    "pending_status": TaskStatus.PENDING.value,
                    "expected_blocked_reason": expected_blocked_reason,
                    "execution_context": serialized_context,
                    "resumed_at": resumed_at,
                },
            )
            resumed = result.rowcount == 1
            if resumed:
                self._refresh_task_projection(conn, task_id)
            return resumed
