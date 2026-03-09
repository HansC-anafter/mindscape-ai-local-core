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
        if target_client_id:
            # Find specific client
            ws_clients = self._clients.get(workspace_id, {})
            client = ws_clients.get(target_client_id)
        else:
            client = self.get_client(workspace_id)

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
        max_idle = timeout
        last_activity = time.monotonic()

        while True:
            try:
                return await asyncio.wait_for(
                    asyncio.shield(result_future),
                    timeout=30.0,
                )
            except asyncio.TimeoutError:
                # Check if inflight task has received progress
                inflight = self._inflight.get(execution_id)
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
            # Skip if targeted to a different client
            if task.target_client_id and task.target_client_id != client.client_id:
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
