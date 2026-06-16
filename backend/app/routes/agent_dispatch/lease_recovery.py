"""Reservation and durable recovery helpers for agent dispatch leases."""

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.app.models.workspace.enums import TaskStatus

from .models import ReservedTask

logger = logging.getLogger("backend.app.routes.agent_dispatch.lease_manager")


class LeaseRecoveryMixin:
    """Mixin: REST polling reservation, reclaim, and durable recovery."""

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
                or (
                    (params.get("metadata") or {}).get("meeting_session_id")
                    if isinstance(params.get("metadata"), dict)
                    else ""
                )
                or (
                    ((params.get("context") or {}).get("meeting_session_id"))
                    if isinstance(params.get("context"), dict)
                    else ""
                )
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
            if surface_type:
                task_agent_id = t.payload.get("agent_id", "")
                if task_agent_id and task_agent_id != surface_type:
                    remaining.append(t)
                    continue

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
        self._reclaim_expired_reserves()

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
