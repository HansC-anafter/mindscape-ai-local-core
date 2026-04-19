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

from backend.app.models.workspace.enums import TaskStatus

from .models import ReservedTask

logger = logging.getLogger(__name__)


class LeaseManagerMixin:
    """Mixin: REST polling lease management and result submission."""

    @staticmethod
    def _meeting_session_is_recoverable(session: Any) -> bool:
        if session is None:
            return True
        if getattr(session, "ended_at", None) is not None:
            return False
        status = getattr(session, "status", None)
        if hasattr(status, "value"):
            status = status.value
        normalized_status = str(status or "").strip().lower()
        if not normalized_status:
            return True
        return normalized_status in {"planned", "active", "closing"}

    @staticmethod
    def _extract_task_meeting_session_id(task: Any) -> str:
        direct = str(getattr(task, "meeting_session_id", "") or "").strip()
        if direct:
            return direct

        execution_context = (
            getattr(task, "execution_context", None)
            if isinstance(getattr(task, "execution_context", None), dict)
            else {}
        )
        from_execution_context = str(
            execution_context.get("meeting_session_id") or ""
        ).strip()
        if from_execution_context:
            return from_execution_context

        params = getattr(task, "params", None)
        if isinstance(params, dict):
            from_params = str(
                params.get("meeting_session_id")
                or ((params.get("metadata") or {}).get("meeting_session_id") if isinstance(params.get("metadata"), dict) else "")
                or (((params.get("context") or {}).get("meeting_session_id")) if isinstance(params.get("context"), dict) else "")
                or ""
            ).strip()
            if from_params:
                return from_params

        return ""

    def _reserve_from_pending_queue(
        self,
        *,
        workspace_id: str,
        client_id: str,
        surface_type: Optional[str],
        limit: int,
        lease_seconds: float,
    ) -> List[ReservedTask]:
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

        return reserved

    def _recover_orphaned_pending_tasks(
        self,
        *,
        workspace_id: str,
        surface_type: Optional[str],
        limit: int,
    ) -> int:
        """Rehydrate orphaned REST-polling tasks from durable task rows."""
        try:
            from backend.app.routes.agent_dispatch.models import PendingTask
            from backend.app.services.stores.tasks_store import TasksStore
            from backend.app.services.stores.meeting_session_store import (
                MeetingSessionStore,
            )
        except Exception:
            logger.exception("[AgentWS] Failed to import task recovery dependencies")
            return 0

        tasks_store = TasksStore()
        meeting_session_store = MeetingSessionStore()
        query_limit = max(limit, min(limit * 4, 500))
        try:
            pending_tasks = tasks_store.list_tasks_by_workspace(
                workspace_id=workspace_id,
                status=TaskStatus.PENDING,
                limit=query_limit,
                exclude_cancelled=True,
                task_type="agent_dispatch",
            )
        except Exception:
            logger.exception(
                "[AgentWS] Failed to query durable pending agent tasks for %s",
                workspace_id,
            )
            return 0

        known_ids = set(self._reserved.keys()) | set(self._inflight.keys()) | set(
            self._completed.keys()
        )
        for pending in self._pending_queue.get(workspace_id, []):
            execution_id = str(getattr(pending, "execution_id", "") or "").strip()
            if execution_id:
                known_ids.add(execution_id)

        recovered = 0
        remaining_capacity = max(
            getattr(self, "MAX_PENDING_QUEUE", 100)
            - len(self._pending_queue.get(workspace_id, [])),
            0,
        )
        if remaining_capacity <= 0:
            return 0

        meeting_session_cache: Dict[str, bool] = {}
        stale_discarded = 0
        for task in pending_tasks:
            execution_id = str(
                getattr(task, "execution_id", None) or getattr(task, "id", None) or ""
            ).strip()
            if not execution_id or execution_id in known_ids:
                continue
            if getattr(task, "task_type", None) != "agent_dispatch":
                continue

            payload = getattr(task, "params", None)
            if not isinstance(payload, dict) or payload.get("type") != "dispatch":
                continue

            task_surface_type = (
                payload.get("agent_id")
                or payload.get("surface_type")
                or getattr(task, "pack_id", None)
            )
            if surface_type and task_surface_type and task_surface_type != surface_type:
                continue

            meeting_session_id = self._extract_task_meeting_session_id(task)
            if meeting_session_id:
                recoverable = meeting_session_cache.get(meeting_session_id)
                if recoverable is None:
                    session = meeting_session_store.get_by_id(meeting_session_id)
                    recoverable = self._meeting_session_is_recoverable(session)
                    meeting_session_cache[meeting_session_id] = recoverable
                if not recoverable:
                    stale_discarded += 1
                    try:
                        task_id = str(getattr(task, "id", "") or execution_id).strip()
                        if task_id:
                            tasks_store.update_task_status(
                                task_id,
                                TaskStatus.EXPIRED,
                                error=(
                                    "Stale agent_dispatch task for ended meeting session "
                                    f"{meeting_session_id}"
                                ),
                                completed_at=datetime.now(timezone.utc),
                            )
                    except Exception:
                        logger.exception(
                            "[AgentWS] Failed to expire stale pending agent task %s",
                            execution_id,
                        )
                    continue

            execution_context = (
                task.execution_context if isinstance(task.execution_context, dict) else {}
            )
            pending = PendingTask(
                execution_id=execution_id,
                workspace_id=workspace_id,
                payload=dict(payload),
                target_client_id=payload.get("target_client_id")
                or execution_context.get("target_client_id"),
            )
            self._enqueue_pending(pending)
            known_ids.add(execution_id)
            recovered += 1

            if recovered >= limit or recovered >= remaining_capacity:
                break

        if recovered:
            logger.warning(
                "[AgentWS] Recovered %s orphaned pending agent task(s) for %s",
                recovered,
                workspace_id,
            )
        if stale_discarded:
            logger.warning(
                "[AgentWS] Discarded %s stale pending agent task(s) for ended meetings in %s",
                stale_discarded,
                workspace_id,
            )

        return recovered

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

        # Track polling liveness: record when this client last polled
        if not hasattr(self, "_last_poll_by_client"):
            self._last_poll_by_client: Dict[str, float] = {}
        self._last_poll_by_client[client_id] = time.monotonic()

        reserved = self._reserve_from_pending_queue(
            workspace_id=workspace_id,
            client_id=client_id,
            surface_type=surface_type,
            limit=limit,
            lease_seconds=lease_seconds,
        )
        if not reserved:
            recovered = self._recover_orphaned_pending_tasks(
                workspace_id=workspace_id,
                surface_type=surface_type,
                limit=limit,
            )
            if recovered:
                reserved = self._reserve_from_pending_queue(
                    workspace_id=workspace_id,
                    client_id=client_id,
                    surface_type=surface_type,
                    limit=limit,
                    lease_seconds=lease_seconds,
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

    def has_recent_poll_activity(self, max_age_seconds: float = 120.0) -> bool:
        """Check if any client has polled within the specified time window."""
        if not hasattr(self, "_last_poll_by_client"):
            return False
        now = time.monotonic()
        return any(
            (now - ts) < max_age_seconds for ts in self._last_poll_by_client.values()
        )

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

        # Notify in-memory Future (instant wake-up for waiting coroutine)
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

        # Clean up in-memory structures
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
