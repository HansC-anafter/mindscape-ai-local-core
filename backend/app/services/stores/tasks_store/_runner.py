"""
TasksStore runner lifecycle mixin — claim, heartbeat, zombie reaping, cancel.
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from sqlalchemy import text

from app.models.workspace import Task, TaskStatus

from ._base import _utc_now

logger = logging.getLogger(__name__)


class TasksStoreRunnerMixin:
    """Runner lifecycle operations for TasksStore."""

    def try_claim_task(self, task_id: str, runner_id: str) -> bool:
        now = _utc_now()

        with self.transaction() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT status, execution_context
                    FROM tasks
                    WHERE id = :task_id
                """
                ),
                {"task_id": task_id},
            ).fetchone()
            if not row:
                return False

            current_status = getattr(row, "status", None)
            if current_status != TaskStatus.PENDING.value:
                return False

            existing_ctx: Dict[str, Any] = {}
            raw_ctx = getattr(row, "execution_context", None)
            if raw_ctx:
                existing_ctx = self.deserialize_json(raw_ctx, {})

            ctx = dict(existing_ctx) if isinstance(existing_ctx, dict) else {}
            ctx["runner_id"] = runner_id
            ctx["heartbeat_at"] = now.isoformat()

            result = conn.execute(
                text(
                    """
                    UPDATE tasks
                    SET status = :running_status,
                        started_at = :started_at,
                        execution_context = :execution_context,
                        blocked_reason = NULL,
                        blocked_payload = NULL,
                        frontier_state = :frontier_state,
                        frontier_enqueued_at = NULL
                    WHERE id = :task_id AND status = :pending_status
                """
                ),
                {
                    "running_status": TaskStatus.RUNNING.value,
                    "pending_status": TaskStatus.PENDING.value,
                    "started_at": now,
                    "execution_context": self.serialize_json(ctx),
                    "frontier_state": "running",
                    "task_id": task_id,
                },
            )
            return result.rowcount == 1

    def update_task_heartbeat(
        self, task_id: str, runner_id: Optional[str] = None
    ) -> bool:
        """Update heartbeat and return True if the task should be aborted.

        Returns:
            should_abort: True if the DB task status indicates the runner
            should stop (cancelled, expired, or externally failed).
        """
        now = _utc_now()
        now_iso = now.isoformat()
        task = self.get_task(task_id)
        if not task:
            return True  # task deleted — abort

        ctx = task.execution_context if isinstance(task.execution_context, dict) else {}
        ctx = dict(ctx)
        ctx["heartbeat_at"] = now_iso
        if runner_id:
            ctx["runner_id"] = runner_id

        try:
            exec_mode = (ctx.get("execution_mode") or "").strip().lower()
        except Exception:
            exec_mode = ""

        should_revive = False
        if runner_id and exec_mode == "runner":
            try:
                if (
                    task.status == TaskStatus.FAILED
                    and (task.error or "") == "Execution interrupted by server restart"
                ):
                    hb = None
                    ca = getattr(task, "completed_at", None)
                    try:
                        hb_raw = ctx.get("heartbeat_at")
                        hb = (
                            datetime.fromisoformat(hb_raw)
                            if isinstance(hb_raw, str) and hb_raw.strip()
                            else None
                        )
                    except Exception:
                        hb = None
                    try:
                        ca_dt = ca if isinstance(ca, datetime) else None
                    except Exception:
                        ca_dt = None
                    if hb and ca_dt and hb > ca_dt:
                        should_revive = True
                    elif hb and not ca_dt:
                        should_revive = True
            except Exception:
                should_revive = False

        if should_revive:
            ctx["status"] = "running"
            self.update_task(
                task_id,
                execution_context=ctx,
                status=TaskStatus.RUNNING,
                error=None,
            )
        else:
            self.update_task(task_id, execution_context=ctx)
        logger.debug("Updated heartbeat for task %s (runner=%s)", task_id, runner_id)

        if should_revive:
            return False  # just revived — keep running

        return self.should_abort_task(task_id)

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
                "Task %s status=%s — signalling abort to runner", task_id, task.status
            )
            return True
        if (
            task.status == TaskStatus.FAILED
            and (task.error or "") != "Execution interrupted by server restart"
        ):
            logger.warning(
                "Task %s externally failed (%s) — signalling abort",
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

        reaped_ids: List[str] = []
        for task in tasks:
            ctx = (
                task.execution_context
                if isinstance(task.execution_context, dict)
                else {}
            )
            hb_raw = ctx.get("heartbeat_at")
            hb_dt = None
            if hb_raw and isinstance(hb_raw, str):
                try:
                    hb_dt = datetime.fromisoformat(hb_raw)
                    if hb_dt.tzinfo is None:
                        hb_dt = hb_dt.replace(tzinfo=timezone.utc)
                except Exception:
                    hb_dt = None

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
                # No heartbeat — check how long the task has been running
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

    def ensure_runner_heartbeats_table(self) -> None:
        """Create runner_heartbeats table if it does not exist."""
        with self.transaction() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS runner_heartbeats (
                        runner_id TEXT PRIMARY KEY,
                        heartbeat_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
            )

    def upsert_runner_heartbeat(self, runner_id: str) -> None:
        """Record that a runner is alive (called every poll cycle)."""
        try:
            with self.transaction() as conn:
                conn.execute(
                    text(
                        """
                        INSERT INTO runner_heartbeats (runner_id, heartbeat_at)
                        VALUES (:runner_id, NOW())
                        ON CONFLICT (runner_id)
                        DO UPDATE SET heartbeat_at = NOW()
                        """
                    ),
                    {"runner_id": runner_id},
                )
        except Exception:
            # Table might not exist yet; create it and retry.
            try:
                self.ensure_runner_heartbeats_table()
                with self.transaction() as conn:
                    conn.execute(
                        text(
                            """
                            INSERT INTO runner_heartbeats (runner_id, heartbeat_at)
                            VALUES (:runner_id, NOW())
                            ON CONFLICT (runner_id)
                            DO UPDATE SET heartbeat_at = NOW()
                            """
                        ),
                        {"runner_id": runner_id},
                    )
            except Exception:
                pass

    def has_active_runner(self, max_age_seconds: float = 120.0) -> bool:
        """Check if any runner has sent a heartbeat within max_age_seconds."""
        try:
            with self.get_connection() as conn:
                row = conn.execute(
                    text(
                        """
                        SELECT COUNT(*) AS cnt
                        FROM runner_heartbeats
                        WHERE heartbeat_at > NOW() - INTERVAL '1 second' * :max_age
                        """
                    ),
                    {"max_age": max_age_seconds},
                ).fetchone()
                if row:
                    cnt = (
                        row[0] if not hasattr(row, "_mapping") else row._mapping["cnt"]
                    )
                    return int(cnt) > 0
        except Exception:
            pass
        return False
