"""Atomic cold-frontier release transitions for runner maintenance."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import text

from app.models.workspace import TaskStatus


class TasksStoreFrontierReleaseMixin:
    """Release due blocked tasks without hydrating their full JSON payload."""

    def try_release_resource_wait_task(
        self,
        task_id: str,
        *,
        released_at: datetime,
    ) -> bool:
        with self.transaction() as conn:
            result = conn.execute(
                text(
                    """
                    UPDATE tasks
                    SET execution_context = (
                            execution_context::jsonb
                            - 'resource_admission'
                            - 'runner_resource_leases'
                            - 'resume_after'
                        )::json,
                        next_eligible_at = :released_at,
                        blocked_reason = NULL,
                        blocked_payload = NULL,
                        frontier_state = 'ready',
                        frontier_enqueued_at = :released_at
                    WHERE id = :task_id
                      AND status = :pending_status
                      AND frontier_state = 'cold'
                      AND blocked_reason = 'resource_wait'
                      AND next_eligible_at <= :released_at
                    """
                ),
                {
                    "task_id": task_id,
                    "pending_status": TaskStatus.PENDING.value,
                    "released_at": released_at,
                },
            )
            released = result.rowcount == 1
            if released:
                self._refresh_task_projection(conn, task_id)
            return released


__all__ = ["TasksStoreFrontierReleaseMixin"]
