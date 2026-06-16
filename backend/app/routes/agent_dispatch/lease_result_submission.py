"""REST polling result submission helper for agent dispatch leases."""

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger("backend.app.routes.agent_dispatch.lease_manager")


class LeaseResultSubmissionMixin:
    """Mixin: result persistence and in-memory lease cleanup."""

    def submit_result(
        self,
        execution_id: str,
        result_data: Dict[str, Any],
        client_id: Optional[str] = None,
        lease_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Submit a task result via REST.

        Architecture: DB is the source of truth, in-memory Future is a
        notification mechanism to instantly wake up the waiting coroutine.

        Flow:
          1. Write result to DB (primary, source of truth)
          2. Notify in-memory Future if present (instant event, not polling)
          3. Clean up in-memory structures (reserved, inflight, pending)

        Idempotent: second call = no-op.
        Returns context dict on success, or None on rejection.
        """
        if execution_id in self._completed:
            logger.info(f"[AgentWS] Duplicate submit for {execution_id}, no-op")
            return {"accepted": True, "duplicate": True}

        reserved = self._reserved.get(execution_id)
        if reserved:
            if lease_id and reserved.lease_id != lease_id:
                logger.warning(
                    f"[AgentWS] submit_result lease_id mismatch for {execution_id}"
                )
                return None
            if client_id and reserved.client_id != client_id:
                logger.warning(
                    f"[AgentWS] submit_result client mismatch for {execution_id}"
                )
                return None

        workspace_id = None
        thread_id = None
        project_id = None
        db_written = False
        try:
            from backend.app.services.stores.tasks_store import TasksStore
            from backend.app.models.workspace import TaskStatus

            tasks_store = TasksStore()
            db_task = tasks_store.get_task(execution_id)
            if db_task and db_task.status in (
                TaskStatus.PENDING,
                TaskStatus.RUNNING,
            ):
                status = result_data.get("status", "completed")
                task_status = (
                    TaskStatus.SUCCEEDED if status == "completed" else TaskStatus.FAILED
                )
                tasks_store.update_task_status(
                    task_id=execution_id,
                    status=task_status,
                    result=result_data,
                    error=result_data.get("error"),
                    completed_at=datetime.now(timezone.utc),
                )
                workspace_id = db_task.workspace_id
                exec_ctx = db_task.execution_context or {}
                thread_id = exec_ctx.get("thread_id")
                project_id = db_task.project_id or exec_ctx.get("project_id")
                db_written = True
                logger.info(
                    f"[AgentWS] DB primary: result persisted for {execution_id} "
                    f"(status={task_status.value})"
                )
            elif db_task:
                logger.info(
                    f"[AgentWS] DB task {execution_id} already "
                    f"{db_task.status.value}, no-op"
                )
                self._completed[execution_id] = time.monotonic()
                return {"accepted": True, "duplicate": True}
        except Exception:
            logger.exception(
                f"[AgentWS] DB write failed for {execution_id}, "
                f"continuing with in-memory path"
            )

        if not db_written:
            try:
                dispatch_record = self._db_get_pending_dispatch_record(execution_id)
            except Exception:
                logger.exception(
                    "[AgentWS] Failed to load durable dispatch row for %s",
                    execution_id,
                )
                dispatch_record = None

            if dispatch_record:
                record_status = str(dispatch_record.get("status") or "").strip().lower()
                if record_status == "done":
                    self._completed[execution_id] = time.monotonic()
                    return {"accepted": True, "duplicate": True}

                try:
                    self._db_write_pending_result(execution_id, result_data)
                    db_written = True
                    workspace_id = str(dispatch_record.get("workspace_id") or "").strip() or None
                    payload = dispatch_record.get("payload")
                    payload_context = (
                        (payload or {}).get("context")
                        if isinstance(payload, dict)
                        else {}
                    ) or {}
                    if not thread_id:
                        thread_id = payload_context.get("thread_id")
                    if not project_id:
                        project_id = payload_context.get("project_id")
                    logger.info(
                        "[AgentWS] Durable dispatch row accepted replayed result for %s",
                        execution_id,
                    )
                except Exception:
                    logger.exception(
                        "[AgentWS] Failed to persist replayed result for %s "
                        "to pending_dispatch",
                        execution_id,
                    )

        inflight = self._inflight.pop(execution_id, None)
        if inflight and inflight.result_future and not inflight.result_future.done():
            inflight.result_future.set_result(result_data)
            if not workspace_id:
                workspace_id = inflight.workspace_id
            if not thread_id:
                thread_id = inflight.thread_id or (
                    (inflight.payload or {}).get("context") or {}
                ).get("thread_id")
            if not project_id:
                project_id = inflight.project_id or (
                    (inflight.payload or {}).get("context") or {}
                ).get("project_id")
            logger.info(f"[AgentWS] Future notified for {execution_id}")

        reserved = self._reserved.pop(execution_id, None)
        if reserved:
            payload_context = (reserved.task.payload or {}).get("context") or {}
            if not thread_id:
                thread_id = payload_context.get("thread_id")
            if not project_id:
                project_id = payload_context.get("project_id")

        for ws_id, queue in self._pending_queue.items():
            for i, task in enumerate(queue):
                if task.execution_id == execution_id:
                    if not workspace_id:
                        workspace_id = task.workspace_id
                    payload_context = (task.payload or {}).get("context") or {}
                    if not thread_id:
                        thread_id = payload_context.get("thread_id")
                    if not project_id:
                        project_id = payload_context.get("project_id")
                    queue.pop(i)
                    break

        self._completed[execution_id] = time.monotonic()
        while len(self._completed) > self.COMPLETED_MAX_SIZE:
            self._completed.popitem(last=False)

        if db_written or inflight:
            return {
                "accepted": True,
                "workspace_id": workspace_id or "",
                "task_id": execution_id,
                "thread_id": thread_id,
                "project_id": project_id,
            }

        logger.warning(
            f"[AgentWS] Result for unknown execution {execution_id} "
            f"(not in DB, not in memory)"
        )
        return None
