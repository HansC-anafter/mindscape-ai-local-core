"""Run-control and event helpers for TasksStore CRUD."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional

from redis import Redis
from sqlalchemy import text

from app.models.workspace import TaskStatus
from backend.app.services.runner_topology import (
    DEFAULT_LOCAL_QUEUE_PARTITION,
    normalize_queue_partition,
)
from backend.app.services.run_attempts_store import RunAttemptsStore
from backend.app.services.task_events_store import TaskEventsStore
from backend.app.services.task_projection_builder import TaskProjectionBuilder

from ._crud_helpers import _TERMINAL_TASK_STATUSES, _coerce_task_status, _utc_now

logger = logging.getLogger(__name__)


class TasksStoreControlMixin:
    """Run-control stores, task events, and post-commit queue helpers."""

    def _enqueue_runner_task_after_commit(self, task: Task) -> None:
        """Best-effort Redis enqueue after the DB transaction has committed."""
        if os.getenv(
            "LOCAL_CORE_TASK_POST_COMMIT_ENQUEUE_ENABLED",
            "true",
        ).lower() in {"0", "false", "no", "off"}:
            return
        if task.status != TaskStatus.PENDING:
            return
        if task.task_type not in ("playbook_execution", "tool_execution"):
            return
        if getattr(task, "frontier_state", "ready") != "ready":
            return
        if getattr(task, "next_eligible_at", None) and task.next_eligible_at > _utc_now():
            return

        try:
            from backend.app.services.stores.redis.runner_queue_store import (
                RedisRunnerQueueStore,
            )
            from backend.app.services.host_resources.route_identity_projection import (
                build_route_identity_projection,
            )

            q_store = RedisRunnerQueueStore(
                pack_id=normalize_queue_partition(
                    getattr(task, "queue_shard", None),
                    fallback=DEFAULT_LOCAL_QUEUE_PARTITION,
                )
            )
            success = q_store.enqueue_task_sync(
                task.id,
                route_identity=build_route_identity_projection(task),
            )
            if not success:
                logger.warning(
                    f"[DB Bridge] Failed post-commit enqueue for task {task.id}. "
                    "Will rely on Reaper Sync."
                )
        except Exception as e:
            logger.error(
                f"[DB Bridge] Exception during post-commit enqueue for task {task.id}: {e}"
            )

    def _sync_playbook_execution_status(
        self,
        conn,
        execution_id: Optional[str],
        status: TaskStatus,
        execution_context: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not execution_id:
            return
        is_auto_resumed = bool(
            execution_context and execution_context.get("auto_resumed")
        )
        if status in (
            TaskStatus.FAILED,
            TaskStatus.CANCELLED_BY_USER,
            TaskStatus.EXPIRED,
        ):
            # Skip auto-resume placeholder failures to avoid clobbering retries
            # that were already queued by the lifecycle hook.
            if is_auto_resumed:
                return
            target_status = "failed"
        elif status == TaskStatus.SUCCEEDED:
            target_status = "done"
        elif status == TaskStatus.PENDING:
            target_status = "queued"
        elif status == TaskStatus.RUNNING:
            target_status = "running"
        else:
            return
        try:
            params = {
                "status": target_status,
                "updated_at": _utc_now(),
                "id": execution_id,
            }
            if target_status == "failed":
                conn.execute(
                    text(
                        """
                        UPDATE playbook_executions
                        SET status = :status, updated_at = :updated_at
                        WHERE id = :id
                          AND NOT EXISTS (
                            SELECT 1 FROM tasks
                            WHERE execution_id = :id
                              AND status IN ('pending', 'running')
                          )
                        """
                    ),
                    params,
                )
            elif target_status == "queued":
                conn.execute(
                    text(
                        """
                        UPDATE playbook_executions
                        SET status = :status, updated_at = :updated_at
                        WHERE id = :id
                          AND status NOT IN ('done', 'failed')
                          AND NOT EXISTS (
                            SELECT 1 FROM tasks
                            WHERE execution_id = :id
                              AND status = 'running'
                          )
                        """
                    ),
                    params,
                )
            elif target_status == "running":
                conn.execute(
                    text(
                        """
                        UPDATE playbook_executions
                        SET status = :status, updated_at = :updated_at
                        WHERE id = :id
                          AND status NOT IN ('done', 'failed')
                        """
                    ),
                    params,
                )
            else:
                conn.execute(
                    text(
                        """
                        UPDATE playbook_executions
                        SET status = :status, updated_at = :updated_at
                        WHERE id = :id
                        """
                    ),
                    params,
                )
        except Exception as e:
            logger.warning(
                "Failed to sync playbook_executions status for %s: %s",
                execution_id,
                e,
            )

    def __init__(self, db_path: Optional[str] = None, db_role: str = "core"):
        super().__init__(db_role=db_role)
        self.db_path = db_path
        self._run_attempts_store_instance: Optional[RunAttemptsStore] = None
        self._task_events_store_instance: Optional[TaskEventsStore] = None
        self._task_projection_builder_instance: Optional[TaskProjectionBuilder] = None

    def _task_events_store(self) -> TaskEventsStore:
        store = self._task_events_store_instance
        if store is None:
            store = TaskEventsStore(db_role=self.db_role)
            self._task_events_store_instance = store
        return store

    def _run_attempts_store(self) -> RunAttemptsStore:
        store = self._run_attempts_store_instance
        if store is None:
            store = RunAttemptsStore(db_role=self.db_role)
            self._run_attempts_store_instance = store
        return store

    def _task_projection_builder(self) -> TaskProjectionBuilder:
        builder = self._task_projection_builder_instance
        if builder is None:
            builder = TaskProjectionBuilder(db_role=self.db_role)
            self._task_projection_builder_instance = builder
        return builder

    def _run_id_for_task(self, task_id: str, execution_id: Optional[str]) -> str:
        return execution_id or task_id

    def _record_run_control_from_task(
        self,
        conn,
        task: Task,
        *,
        status: Optional[str] = None,
    ) -> str:
        run_id = self._run_id_for_task(task.id, task.execution_id)
        self._run_attempts_store().upsert_run(
            run_id=run_id,
            execution_id=task.execution_id or task.id,
            workspace_id=task.workspace_id,
            task_id=task.id,
            pack_id=task.pack_id,
            status=status or _coerce_task_status(task.status),
            started_at=task.started_at,
            completed_at=task.completed_at,
            conn=conn,
        )
        return run_id

    def _record_task_control_event(
        self,
        conn,
        *,
        task_id: str,
        workspace_id: str,
        event_type: str,
        from_status: Optional[str] = None,
        to_status: Optional[str] = None,
        run_id: Optional[str] = None,
        attempt_id: Optional[str] = None,
        summary: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
        idempotency_key: Optional[str] = None,
        occurred_at: Optional[datetime] = None,
    ) -> str:
        return self._task_events_store().record_task_event(
            task_id=task_id,
            workspace_id=workspace_id,
            event_type=event_type,
            from_status=from_status,
            to_status=to_status,
            run_id=run_id,
            attempt_id=attempt_id,
            summary=summary,
            payload=payload,
            idempotency_key=idempotency_key,
            occurred_at=occurred_at,
            conn=conn,
        )

    def _refresh_task_projection(self, conn, task_id: str) -> None:
        self._task_projection_builder().upsert_task_summary_from_task_id(
            task_id,
            conn=conn,
        )

    def _record_latest_attempt_completion(
        self,
        conn,
        *,
        task_id: str,
        status: str,
        completed_at: Optional[datetime] = None,
        error_summary: Optional[str] = None,
    ) -> Optional[str]:
        return self._run_attempts_store().complete_latest_attempt_for_task(
            task_id=task_id,
            status=status,
            completed_at=completed_at,
            error_summary=error_summary,
            conn=conn,
        )

    def _record_task_claim(
        self,
        conn,
        *,
        task_id: str,
        runner_id: str,
        started_at: datetime,
    ) -> Optional[str]:
        row = conn.execute(
            text(
                """
                SELECT id, workspace_id, execution_id, pack_id, status
                FROM tasks
                WHERE id = :task_id
                """
            ),
            {"task_id": task_id},
        ).fetchone()
        if not row:
            return None
        mapping = row._mapping if hasattr(row, "_mapping") else None
        workspace_id = mapping["workspace_id"] if mapping is not None else row[1]
        execution_id = mapping["execution_id"] if mapping is not None else row[2]
        pack_id = mapping["pack_id"] if mapping is not None else row[3]
        status = mapping["status"] if mapping is not None else row[4]
        run_id = self._run_id_for_task(task_id, execution_id)
        self._run_attempts_store().upsert_run(
            run_id=run_id,
            execution_id=execution_id or task_id,
            workspace_id=workspace_id,
            task_id=task_id,
            pack_id=pack_id,
            status=status,
            started_at=started_at,
            conn=conn,
        )
        attempt_id = self._run_attempts_store().create_attempt(
            run_id=run_id,
            task_id=task_id,
            runner_id=runner_id,
            status=status,
            started_at=started_at,
            idempotency_key=(
                f"task:{task_id}:runner:{runner_id}:claim:{started_at.isoformat()}"
            ),
            conn=conn,
        )
        self._record_task_control_event(
            conn,
            task_id=task_id,
            workspace_id=workspace_id,
            event_type="task.claimed",
            from_status=TaskStatus.PENDING.value,
            to_status=status,
            run_id=run_id,
            attempt_id=attempt_id,
            payload={"runner_id": runner_id},
            idempotency_key=f"task:{task_id}:claimed:{attempt_id}",
            occurred_at=started_at,
        )
        self._refresh_task_projection(conn, task_id)
        return attempt_id


def _publish_terminal_event(
    task_id: str, status_raw: str, task_obj: Optional["Task"] = None
) -> None:
    """Fire-and-forget publish to activity stream on terminal status.

    Uses sync Redis because this function is called from sync DB threads
    where asyncio event loops are not running.
    """
    _TERMINAL = {
        "completed",
        "succeeded",
        "failed",
        "cancelled",
        "cancelled_by_user",
        "expired",
    }
    if status_raw.lower() not in _TERMINAL:
        return
    try:
        import json
        import os

        ws_id = task_obj.workspace_id if task_obj else ""
        if not ws_id:
            return

        enabled = os.getenv("REDIS_ENABLED", "true").lower() == "true"
        if not enabled:
            return

        thread_id = ""
        if task_obj and task_obj.execution_context:
            thread_id = task_obj.execution_context.get("thread_id", "")
        if not thread_id and task_obj and task_obj.meeting_session_id:
            thread_id = task_obj.meeting_session_id

        payload = {
            "type": "task_completed",
            "task_id": task_id,
            "execution_id": task_obj.execution_id if task_obj else None,
            "status": status_raw,
            "pack_id": task_obj.pack_id if task_obj else None,
            "thread_id": thread_id,
        }

        channel = f"workspace:{ws_id}:stream"
        message = json.dumps(payload, ensure_ascii=False)

        # Use sync Redis — we're already in a sync thread
        from redis import Redis

        client = Redis(
            host=os.getenv("REDIS_HOST", "redis"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            password=os.getenv("REDIS_PASSWORD") or None,
            db=int(os.getenv("REDIS_DB", "0")),
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        try:
            client.publish(channel, message)
        finally:
            client.close()
    except Exception:
        pass  # non-fatal
