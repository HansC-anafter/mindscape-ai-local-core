"""
Agent Dispatch -- Core task dispatch mixin.

Handles dispatch_and_wait, pending queue management, and flush.
Message handling is in message_handlers.py.
Cross-worker dispatch is in cross_worker.py.
"""

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional

from .models import AgentClient, InflightTask, PendingTask

logger = logging.getLogger(__name__)


class TaskDispatchMixin:
    """Mixin: core task dispatch, pending queue, and flush."""

    ACK_DEADLINE_SECONDS: float = 30.0
    WAIT_SLICE_SECONDS: float = 30.0

    @staticmethod
    def _resolve_surface_type(message: Dict[str, Any]) -> Optional[str]:
        return message.get("agent_id") or message.get("surface_type")

    def _normalize_completed_entry(
        self,
        execution_id: str,
        raw_entry: Any,
    ) -> Dict[str, Any]:
        if isinstance(raw_entry, dict):
            normalized = dict(raw_entry)
        else:
            normalized = {}
            if isinstance(raw_entry, (int, float)):
                normalized["completed_at_monotonic"] = float(raw_entry)
        normalized.setdefault("execution_id", execution_id)
        if "completed_at_monotonic" not in normalized:
            normalized["completed_at_monotonic"] = time.monotonic()
        if "completed_at" not in normalized:
            normalized["completed_at"] = time.time()
        return normalized

    def _mark_completed_execution(
        self,
        execution_id: str,
        *,
        result: Optional[Dict[str, Any]] = None,
        status: str = "completed",
        landing_succeeded: Optional[bool] = None,
        error: Optional[str] = None,
        acceptance_state: Optional[str] = None,
    ) -> Dict[str, Any]:
        entry = self._normalize_completed_entry(
            execution_id,
            self._completed.get(execution_id),
        )
        entry["completed_at_monotonic"] = time.monotonic()
        entry["completed_at"] = time.time()
        entry["status"] = status
        if result is not None:
            entry["result"] = result
        if landing_succeeded is not None:
            entry["landing_succeeded"] = landing_succeeded
        if error is not None:
            entry["error"] = error
        if acceptance_state is not None:
            entry["acceptance_state"] = acceptance_state
        self._completed[execution_id] = entry
        self._completed.move_to_end(execution_id)
        while len(self._completed) > self.COMPLETED_MAX_SIZE:
            self._completed.popitem(last=False)
        return entry

    def _build_resume_sync(
        self,
        *,
        workspace_id: str,
        recent_execution_ids: List[str],
        pending_rest_execution_ids: List[str],
        last_completed_at: Optional[float],
    ) -> Dict[str, Any]:
        client_known = {
            str(execution_id).strip()
            for execution_id in [*recent_execution_ids, *pending_rest_execution_ids]
            if str(execution_id).strip()
        }
        replayed_completions: List[Dict[str, Any]] = []
        duplicates_to_ignore: List[str] = []

        for execution_id, raw_entry in self._completed.items():
            entry = self._normalize_completed_entry(execution_id, raw_entry)
            completed_at = entry.get("completed_at")
            if (
                isinstance(last_completed_at, (int, float))
                and isinstance(completed_at, (int, float))
                and completed_at <= float(last_completed_at)
            ):
                continue
            if execution_id in client_known:
                duplicates_to_ignore.append(execution_id)
                continue
            replayed_completions.append(
                {
                    "execution_id": execution_id,
                    "completed_at": completed_at,
                    "status": entry.get("status", "completed"),
                    "landing_succeeded": entry.get("landing_succeeded"),
                    "acceptance_state": entry.get("acceptance_state"),
                }
            )

        tasks_to_requeue: List[Dict[str, Any]] = []
        for execution_id, inflight in self._inflight.items():
            if inflight.workspace_id != workspace_id or execution_id in self._completed:
                continue
            tasks_to_requeue.append(
                {
                    "execution_id": execution_id,
                    "client_id": inflight.client_id,
                    "acked": inflight.acked,
                }
            )

        return {
            "type": "resume_sync",
            "workspace_id": workspace_id,
            "replayed_completions": replayed_completions,
            "tasks_to_requeue": tasks_to_requeue,
            "duplicates_to_ignore": duplicates_to_ignore,
        }

    async def dispatch_and_wait(
        self,
        workspace_id: str,
        message: Dict[str, Any],
        execution_id: str,
        target_client_id: Optional[str] = None,
        timeout: float = 600.0,
    ) -> Dict[str, Any]:
        """
        Dispatch a task to an IDE client and wait for the result.

        If no client is available, queues the task for later pickup.

        Args:
            workspace_id: Target workspace
            message: Dispatch message payload
            execution_id: Unique execution ID
            target_client_id: Optional specific client target
            timeout: Max wait time in seconds

        Returns:
            Result dict with execution_id, status, output, etc.
        """
        # Check if already completed (idempotency guard)
        if execution_id in self._completed:
            logger.info(
                f"[AgentWS] Ignoring duplicate dispatch for "
                f"already-completed {execution_id}"
            )
            return {
                "execution_id": execution_id,
                "status": "completed",
                "output": "(duplicate dispatch ignored)",
            }

        client = None
        surface_type = self._resolve_surface_type(message)

        if target_client_id:
            client = self.get_client(
                workspace_id,
                target_client_id,
                surface_type=surface_type,
            )
        else:
            client = self.get_client(workspace_id, surface_type=surface_type)

        if not client:
            logger.info(
                f"[AgentWS] No local client for {workspace_id}, "
                f"dispatching cross-worker for {execution_id}"
            )
            return await self._cross_worker_dispatch(
                workspace_id,
                message,
                execution_id,
                timeout,
                target_client_id=target_client_id,
                surface_type=surface_type,
            )

        # Create future for result
        loop = asyncio.get_event_loop()
        result_future: asyncio.Future = loop.create_future()

        inflight = InflightTask(
            execution_id=execution_id,
            workspace_id=workspace_id,
            client_id=client.client_id,
            result_future=result_future,
            payload=message,
            thread_id=(message.get("context") or {}).get("thread_id"),
            project_id=(message.get("context") or {}).get("project_id"),
        )
        self._inflight[execution_id] = inflight

        # Send task to IDE client
        try:
            await client.websocket.send_text(json.dumps(message))
            logger.info(
                f"[AgentWS] Dispatched {execution_id} to "
                f"client {client.client_id} in {workspace_id}"
            )
        except Exception as e:
            self._inflight.pop(execution_id, None)
            logger.error(f"[AgentWS] Failed to send task {execution_id}: {e}")
            # Enqueue for later retry
            pending = PendingTask(
                execution_id=execution_id,
                workspace_id=workspace_id,
                payload=message,
                target_client_id=target_client_id,
            )
            self._enqueue_pending(pending)
            inflight.client_id = "pending"
            self._inflight[execution_id] = inflight

        # Wait for result with activity-aware timeout.
        # Instead of a hard timeout, poll every 30s and check if the
        # inflight task has received progress updates. Only timeout
        # when there has been no activity for `timeout` seconds.
        #
        # ACK fail-fast: if the client never acknowledges within
        # ACK_DEADLINE seconds, the client is likely dead/disconnected.
        # Fail fast instead of waiting the full idle timeout.
        ack_deadline = self.ACK_DEADLINE_SECONDS
        wait_slice = max(0.05, self.WAIT_SLICE_SECONDS)
        max_idle = timeout
        dispatch_time = time.monotonic()
        last_activity = dispatch_time

        while True:
            try:
                return await asyncio.wait_for(
                    asyncio.shield(result_future),
                    timeout=wait_slice,
                )
            except asyncio.TimeoutError:
                inflight = self._inflight.get(execution_id)

                # ACK fail-fast: no acknowledgment within deadline
                if inflight and not inflight.acked:
                    elapsed = time.monotonic() - dispatch_time
                    if elapsed > ack_deadline:
                        stale_client = None
                        if inflight.client_id and inflight.client_id != "pending":
                            stale_client = self.get_client(
                                workspace_id,
                                inflight.client_id,
                                surface_type=surface_type,
                            )
                        self._inflight.pop(execution_id, None)
                        if stale_client:
                            try:
                                self.disconnect(
                                    stale_client,
                                    requeue_inflight=False,
                                )
                            except Exception:
                                logger.exception(
                                    "[AgentWS] Failed to evict stale client %s "
                                    "after ACK timeout for %s",
                                    stale_client.client_id,
                                    execution_id,
                                )
                        logger.error(
                            f"[AgentWS] dispatch_and_wait: no ACK after "
                            f"{elapsed:.0f}s, client likely disconnected. "
                            f"exec={execution_id}"
                        )
                        logger.warning(
                            "[AgentWS] Retrying %s via shared transport after "
                            "ACK timeout",
                            execution_id,
                        )
                        return await self._cross_worker_dispatch(
                            workspace_id,
                            message,
                            execution_id,
                            timeout,
                            target_client_id=target_client_id,
                            surface_type=surface_type,
                        )

                # Activity-aware idle timeout (post-ACK)
                if inflight and inflight.last_progress_at > last_activity:
                    last_activity = inflight.last_progress_at

                idle = time.monotonic() - last_activity
                if idle > max_idle:
                    self._inflight.pop(execution_id, None)
                    logger.error(
                        f"[AgentWS] dispatch_and_wait: no activity for "
                        f"{idle:.0f}s (max_idle={max_idle}s), "
                        f"exec={execution_id}"
                    )
                    return {
                        "execution_id": execution_id,
                        "status": "timeout",
                        "error": f"No activity for {idle:.0f}s",
                    }

    def _enqueue_pending(self, task: PendingTask) -> None:
        """Add a task to the pending queue, respecting max size."""
        queue = self._pending_queue[task.workspace_id]
        if len(queue) >= self.MAX_PENDING_QUEUE:
            # Drop oldest
            dropped = queue.pop(0)
            logger.warning(
                f"[AgentWS] Pending queue full for {task.workspace_id}, "
                f"dropping oldest task {dropped.execution_id}"
            )
        queue.append(task)

        # Wake any long-polling clients waiting for this workspace
        event = self._task_events.get(task.workspace_id)
        if event:
            event.set()

    async def flush_pending(self, workspace_id: str, client: AgentClient) -> int:
        """
        Send all pending tasks for a workspace to a newly connected client.

        Returns the number of tasks flushed.
        """
        queue = self._pending_queue.get(workspace_id, [])
        if not queue:
            return 0

        flushed = 0
        remaining = []

        for task in queue:
            task_surface_type = task.payload.get("agent_id") or task.payload.get(
                "surface_type"
            )

            # Skip if targeted to a different client
            if task.target_client_id and task.target_client_id != client.client_id:
                remaining.append(task)
                continue

            if task_surface_type and task_surface_type != client.surface_type:
                remaining.append(task)
                continue

            task.attempts += 1
            if task.attempts > task.max_attempts:
                # Give up on this task
                inflight = self._inflight.pop(task.execution_id, None)
                if (
                    inflight
                    and inflight.result_future
                    and not inflight.result_future.done()
                ):
                    inflight.result_future.set_result(
                        {
                            "execution_id": task.execution_id,
                            "status": "failed",
                            "error": f"Max dispatch attempts ({task.max_attempts}) exceeded",
                        }
                    )
                continue

            try:
                await client.websocket.send_text(json.dumps(task.payload))

                # Update inflight to point to this client
                if task.execution_id in self._inflight:
                    self._inflight[task.execution_id].client_id = client.client_id
                    self._inflight[task.execution_id].dispatched_at = time.monotonic()

                flushed += 1
                logger.info(
                    f"[AgentWS] Flushed pending task {task.execution_id} "
                    f"to client {client.client_id}"
                )
            except Exception as e:
                logger.warning(
                    f"[AgentWS] Failed to flush task {task.execution_id}: {e}"
                )
                remaining.append(task)

        self._pending_queue[workspace_id] = remaining

        if flushed:
            logger.info(
                f"[AgentWS] Flushed {flushed} pending tasks to "
                f"client {client.client_id} in workspace {workspace_id}"
            )

        return flushed
