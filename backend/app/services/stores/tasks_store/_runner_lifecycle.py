"""TasksStore runner lifecycle methods."""

from __future__ import annotations

import logging
from datetime import timezone
from typing import List, Optional

from sqlalchemy import text
from app.models.workspace import TaskStatus

from ._base import _utc_now
from ._runner_helpers import _effective_runner_heartbeat_at

logger = logging.getLogger(__name__)


class TasksStoreRunnerLifecycleMixin:
    """Runner heartbeat abort, zombie reaping, and cancel operations."""

    def update_task_heartbeat(
        self, task_id: str, runner_id: Optional[str] = None
    ) -> bool:
        """Return True if the task should be aborted without mutating heartbeat.

        Returns:
            should_abort: True if the DB task status indicates the runner
            should stop (cancelled, expired, or externally failed).
        """
        restart_error = "Execution interrupted by server restart"
        abort_statuses = {
            TaskStatus.CANCELLED_BY_USER.value,
            TaskStatus.EXPIRED.value,
        }

        with self.get_connection() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT status, error
                    FROM tasks
                    WHERE id = :task_id
                    """
                ),
                {"task_id": task_id},
            ).fetchone()
            if not row:
                return True

            status_raw = getattr(row, "status", None)
            error_raw = getattr(row, "error", None) or ""
            if status_raw in abort_statuses:
                logger.warning(
                    "Task %s status=%s - signalling abort to runner",
                    task_id,
                    status_raw,
                )
                return True
            if status_raw == TaskStatus.FAILED.value and error_raw != restart_error:
                logger.warning(
                    "Task %s externally failed (%s) - signalling abort",
                    task_id,
                    error_raw,
                )
                return True

        logger.debug("Checked abort state for task %s (runner=%s)", task_id, runner_id)
        return False

    def should_abort_task(self, task_id: str) -> bool:
        """Return True when the runner should abort the task without mutating heartbeat."""
        task = self.get_task(task_id)
        if not task:
            return True

        abort_statuses = {
            TaskStatus.CANCELLED_BY_USER,
            TaskStatus.EXPIRED,
        }
        if task.status in abort_statuses:
            logger.warning(
                "Task %s status=%s - signalling abort to runner", task_id, task.status
            )
            return True
        if (
            task.status == TaskStatus.FAILED
            and (task.error or "") != "Execution interrupted by server restart"
        ):
            logger.warning(
                "Task %s externally failed (%s) - signalling abort",
                task_id,
                task.error,
            )
            return True
        return False

    def reap_zombie_tasks(
        self,
        heartbeat_ttl_minutes: int = 10,
        no_heartbeat_ttl_minutes: int = 30,
    ) -> List[str]:
        """Reap zombie tasks that have stale or missing heartbeats.

        A task is considered zombie if:
        - It has a heartbeat older than heartbeat_ttl_minutes, OR
        - It has no heartbeat and has been running for > no_heartbeat_ttl_minutes

        Args:
            heartbeat_ttl_minutes: Max age of heartbeat before task is reaped
            no_heartbeat_ttl_minutes: Max running time without any heartbeat

        Returns:
            List of reaped task IDs
        """
        from datetime import timedelta

        now = _utc_now()
        tasks = self.list_tasks_by_workspace(
            workspace_id=None, status=TaskStatus.RUNNING
        )
        try:
            from ._runner import RunnerLiveStateStore

            live_state_store = RunnerLiveStateStore()
        except Exception:
            live_state_store = None

        reaped_ids: List[str] = []
        for task in tasks:
            ctx = (
                task.execution_context
                if isinstance(task.execution_context, dict)
                else {}
            )
            hb_dt = _effective_runner_heartbeat_at(task, ctx, live_state_store)

            is_zombie = False
            reason = ""

            if hb_dt:
                age = now - hb_dt
                if age > timedelta(minutes=heartbeat_ttl_minutes):
                    is_zombie = True
                    reason = (
                        f"Zombie: heartbeat stale for {int(age.total_seconds())}s "
                        f"(threshold {heartbeat_ttl_minutes}m)"
                    )
            else:
                # Use task age when no heartbeat exists.
                started = task.started_at or task.created_at
                if started:
                    if started.tzinfo is None:
                        started = started.replace(tzinfo=timezone.utc)
                    age = now - started
                    if age > timedelta(minutes=no_heartbeat_ttl_minutes):
                        is_zombie = True
                        reason = (
                            f"Zombie: no heartbeat, running for {int(age.total_seconds())}s "
                            f"(threshold {no_heartbeat_ttl_minutes}m)"
                        )

            if is_zombie:
                try:
                    self.update_task_status(
                        task_id=task.id,
                        status=TaskStatus.FAILED,
                        error=reason,
                        completed_at=now,
                    )
                    reaped_ids.append(task.id)
                    logger.warning("Reaped zombie task %s: %s", task.id, reason)
                except Exception as e:
                    logger.error("Failed to reap zombie task %s: %s", task.id, e)

        if reaped_ids:
            logger.info("Zombie reaper: reaped %d tasks", len(reaped_ids))
        else:
            logger.debug("Zombie reaper: no zombie tasks found")

        return reaped_ids

    def cancel_task(self, task_id: str) -> bool:
        """Cancel a task by setting its status to CANCELLED_BY_USER.

        Works on PENDING or RUNNING tasks. For RUNNING tasks, the runner
        will detect the cancellation via the heartbeat abort check.

        Args:
            task_id: Task ID to cancel

        Returns:
            True if the task was cancelled, False if not found or
            already in a terminal state.
        """
        task = self.get_task(task_id)
        if not task:
            return False

        if task.status not in (TaskStatus.PENDING, TaskStatus.RUNNING):
            return False

        now = _utc_now()
        try:
            self.update_task_status(
                task_id=task_id,
                status=TaskStatus.CANCELLED_BY_USER,
                error="Cancelled by user",
                completed_at=now,
            )
            logger.info("Task %s cancelled by user", task_id)
            return True
        except Exception as e:
            logger.error("Failed to cancel task %s: %s", task_id, e)
            return False
