"""
Agent Dispatch — REST lease management mixin.

Handles task reservation with leased timeouts for REST polling clients,
acknowledgment with lease extension, progress-based lease reset,
inflight listing for crash recovery, and result submission.
"""

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .models import ReservedTask

logger = logging.getLogger(__name__)


class LeaseManagerMixin:
    """Mixin: REST polling lease management and result submission."""

    def reserve_pending_tasks(
        self,
        workspace_id: str,
        client_id: str,
        surface_type: Optional[str] = None,
        limit: int = 5,
        lease_seconds: float = 60.0,
    ) -> List[Dict[str, Any]]:
        """
        Atomic reserve: pending tasks with lease timeout (REST polling).

        Tasks are atomically moved from queue to _reserved with lease_id.
        If the client crashes (lease expires), tasks auto-return to queue.
        Respects target_client_id filtering on PendingTask.
        """
        # Lazy reclaim expired leases before reserving new ones
        self._reclaim_expired_reserves()

        queue = self._pending_queue.get(workspace_id, [])
        reserved, remaining = [], []

        for t in queue:
            # Filter by agent_id if surface_type is specified
            # Prevents multi-runner cross-contamination
            if surface_type:
                task_agent_id = t.payload.get("agent_id", "")
                if task_agent_id and task_agent_id != surface_type:
                    remaining.append(t)
                    continue

            # Skip if targeted to a different client
            if t.target_client_id and t.target_client_id != client_id:
                remaining.append(t)
                continue

            if len(reserved) < limit:
                r = ReservedTask(
                    task=t,
                    client_id=client_id,
                    reserved_at=time.monotonic(),
                    lease_seconds=lease_seconds,
                )
                self._reserved[t.execution_id] = r
                reserved.append(r)
            else:
                remaining.append(t)

        self._pending_queue[workspace_id] = remaining

        if reserved:
            logger.info(
                f"[AgentWS] Reserved {len(reserved)} tasks for "
                f"client {client_id} in workspace {workspace_id}"
            )

        # Return payload + lease_id for each reserved task
        results = []
        for r in reserved:
            payload = dict(r.task.payload)
            payload["lease_id"] = r.lease_id
            results.append(payload)
        return results

    def _reclaim_expired_reserves(self) -> None:
        """Return expired reserved tasks back to the pending queue."""
        for eid, r in list(self._reserved.items()):
            if r.expired:
                self._reserved.pop(eid)
                self._enqueue_pending(r.task)
                logger.warning(f"[AgentWS] Lease expired for {eid}, re-queued")

    def ack_task(
        self,
        execution_id: str,
        lease_id: str,
        client_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Acknowledge task pickup and extend lease (30s -> 300s).

        Verifies lease_id to prevent ghost duplicate execution.
        Idempotent: re-acking same task+lease returns same result.
        Returns lease info dict or None if rejected.
        """
        reserved = self._reserved.get(execution_id)
        if not reserved:
            # Idempotent: already completed?
            if execution_id in self._completed:
                return {"execution_id": execution_id, "status": "already_completed"}
            return None

        # Verify lease_id
        if reserved.lease_id != lease_id:
            logger.warning(
                f"[AgentWS] ack lease_id mismatch for {execution_id}: "
                f"expected {reserved.lease_id}, got {lease_id}"
            )
            return None

        # Verify client ownership
        if client_id and reserved.client_id != client_id:
            logger.warning(
                f"[AgentWS] ack client mismatch for {execution_id}: "
                f"reserved by {reserved.client_id}, acked by {client_id}"
            )
            return None

        # Idempotent: already acked
        if reserved.acked:
            return {
                "execution_id": execution_id,
                "lease_id": lease_id,
                "lease_expires_at": reserved.lease_deadline,
                "status": "already_acked",
            }

        # Extend lease and mark acked
        reserved.acked = True
        reserved.extend_lease(270.0)  # 30s initial + 270s = 300s total
        logger.info(f"[AgentWS] Task {execution_id} acked, lease extended to 300s")

        return {
            "execution_id": execution_id,
            "lease_id": lease_id,
            "lease_expires_at": reserved.lease_deadline,
            "status": "acked",
        }

    def report_progress(
        self,
        execution_id: str,
        lease_id: str,
        progress_pct: Optional[float] = None,
        message: Optional[str] = None,
        client_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Report task progress and reset lease timer.

        Verifies lease_id. Idempotent: duplicate calls just update timestamp.
        Returns False if lease cap (30min) exceeded.
        """
        reserved = self._reserved.get(execution_id)
        if not reserved:
            return None

        if reserved.lease_id != lease_id:
            return None
        if client_id and reserved.client_id != client_id:
            return None

        # Reset lease timer (120s from now)
        if not reserved.reset_lease(120.0):
            logger.warning(
                f"[AgentWS] Lease cap exceeded for {execution_id}, "
                f"cumulative={reserved.cumulative_lease:.0f}s"
            )
            return {
                "execution_id": execution_id,
                "status": "lease_cap_exceeded",
                "cumulative_lease": reserved.cumulative_lease,
            }

        return {
            "execution_id": execution_id,
            "lease_expires_at": reserved.lease_deadline,
            "progress_pct": progress_pct,
            "status": "ok",
        }

    def list_inflight(
        self,
        client_id: str,
    ) -> List[Dict[str, Any]]:
        """
        List tasks currently reserved/inflight for a specific client.

        Used for crash recovery: runner restarts and picks up where it left off.
        """
        self._reclaim_expired_reserves()
        results = []
        for eid, r in self._reserved.items():
            if r.client_id == client_id:
                payload = dict(r.task.payload)
                payload["lease_id"] = r.lease_id
                payload["acked"] = r.acked
                payload["lease_expires_at"] = r.lease_deadline
                results.append(payload)
        return results

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
        # Idempotent: already completed
        if execution_id in self._completed:
            logger.info(f"[AgentWS] Duplicate submit for {execution_id}, no-op")
            return {"accepted": True, "duplicate": True}

        # --- Lease/client verification (in-memory, optional) ---
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

        # Persist result to DB (source of truth)
        workspace_id = None
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
                db_written = True
                logger.info(
                    f"[AgentWS] DB primary: result persisted for {execution_id} "
                    f"(status={task_status.value})"
                )
            elif db_task:
                # Task already completed/failed in DB
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

        # Notify in-memory Future (instant wake-up for waiting coroutine)
        inflight = self._inflight.pop(execution_id, None)
        if inflight and inflight.result_future and not inflight.result_future.done():
            inflight.result_future.set_result(result_data)
            if not workspace_id:
                workspace_id = inflight.workspace_id
            logger.info(f"[AgentWS] Future notified for {execution_id}")

        # Clean up in-memory structures
        self._reserved.pop(execution_id, None)

        for ws_id, queue in self._pending_queue.items():
            for i, task in enumerate(queue):
                if task.execution_id == execution_id:
                    if not workspace_id:
                        workspace_id = task.workspace_id
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
            }

        logger.warning(
            f"[AgentWS] Result for unknown execution {execution_id} "
            f"(not in DB, not in memory)"
        )
        return None
