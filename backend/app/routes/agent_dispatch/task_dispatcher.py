"""
Agent Dispatch — Task dispatch and WebSocket message handling mixin.

Covers dispatch_and_wait, pending queue management, flush,
and incoming message routing (ack, progress, result).
"""

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional

from .models import AgentClient, InflightTask, PendingTask

logger = logging.getLogger(__name__)


class TaskDispatchMixin:
    """Mixin: task dispatch, pending queue, and WS message handling."""

    async def dispatch_and_wait(
        self,
        workspace_id: str,
        message: Dict[str, Any],
        execution_id: str,
        target_client_id: Optional[str] = None,
        timeout: float = 120.0,
    ) -> Dict[str, Any]:
        """
        Dispatch a task to an IDE client and wait for the result.

        If no client is available, queues the task for later pickup.

        Args:
            workspace_id: Target workspace
            message: Dispatch message payload
            execution_id: Unique execution ID
            target_client_id: Optional specific client to target
            timeout: Max seconds to wait for result (default 120s)

        Returns:
            Raw result dict from the IDE
        """
        loop = asyncio.get_event_loop()
        result_future: asyncio.Future = loop.create_future()

        client = self.get_client(workspace_id, target_client_id)

        if client:
            # Direct dispatch via WebSocket
            inflight = InflightTask(
                execution_id=execution_id,
                workspace_id=workspace_id,
                client_id=client.client_id,
                result_future=result_future,
                payload=message,  # retain for re-queue on disconnect
            )
            self._inflight[execution_id] = inflight

            try:
                await client.websocket.send_text(json.dumps(message))
                logger.info(
                    f"[AgentWS] Dispatched {execution_id} to "
                    f"client {client.client_id}"
                )
            except Exception as e:
                self._inflight.pop(execution_id, None)
                result_future.set_result(
                    {
                        "execution_id": execution_id,
                        "status": "failed",
                        "error": f"Failed to send dispatch: {e}",
                    }
                )
        else:
            # No client available — queue for later
            pending = PendingTask(
                execution_id=execution_id,
                workspace_id=workspace_id,
                payload=message,
                target_client_id=target_client_id,
            )
            self._enqueue_pending(pending)

            # Create inflight entry that will be resolved when
            # a client picks up and completes the task
            inflight = InflightTask(
                execution_id=execution_id,
                workspace_id=workspace_id,
                client_id="pending",
                result_future=result_future,
                payload=message,  # retain for re-queue
            )
            self._inflight[execution_id] = inflight

            logger.info(
                f"[AgentWS] No client available for {workspace_id}, "
                f"queued task {execution_id}"
            )

        try:
            return await asyncio.wait_for(result_future, timeout=timeout)
        except asyncio.TimeoutError:
            self._inflight.pop(execution_id, None)
            logger.error(
                f"[AgentWS] dispatch_and_wait timed out for {execution_id} "
                f"after {timeout}s"
            )
            return {
                "execution_id": execution_id,
                "status": "timeout",
                "error": f"No result received within {timeout}s",
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

    # ============================================================
    #  Message handling
    # ============================================================

    async def handle_message(
        self,
        client: AgentClient,
        data: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        Handle an incoming message from an IDE client.

        Message types:
          - auth_response: Client authentication response
          - ack: Task acknowledged by client
          - progress: Task progress update
          - result: Task execution result
          - ping: Heartbeat ping

        Returns an optional response message to send back.
        """
        msg_type = data.get("type", "")

        if msg_type == "auth_response":
            return await self._handle_auth_response(client, data)

        # All other messages require authentication
        if not client.authenticated:
            return {
                "type": "error",
                "error": "Not authenticated",
                "code": "AUTH_REQUIRED",
            }

        if msg_type == "ack":
            return self._handle_ack(client, data)
        elif msg_type == "progress":
            return self._handle_progress(client, data)
        elif msg_type == "result":
            return self._handle_result(client, data)
        elif msg_type == "ping":
            client.last_heartbeat = time.monotonic()
            return {"type": "pong", "ts": time.time()}
        else:
            logger.warning(
                f"[AgentWS] Unknown message type '{msg_type}' "
                f"from client {client.client_id}"
            )
            return None

    # ============================================================
    #  Ownership verification + message handlers
    # ============================================================

    def _verify_ownership(
        self,
        client: AgentClient,
        execution_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Check client owns the inflight task.

        Returns error dict if ownership fails, None if verified.
        """
        inflight = self._inflight.get(execution_id)
        if not inflight:
            return {
                "type": "error",
                "error": f"Unknown execution {execution_id}",
            }
        if inflight.client_id != client.client_id:
            logger.warning(
                f"[AgentWS] Unauthorized: expected={inflight.client_id}, "
                f"got={client.client_id} for {execution_id}"
            )
            return {
                "type": "error",
                "error": "Not the assigned client",
            }
        return None  # ownership verified

    def _handle_ack(
        self,
        client: AgentClient,
        data: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Handle task acknowledgment from IDE."""
        execution_id = data.get("execution_id", "")

        err = self._verify_ownership(client, execution_id)
        if err:
            return err

        inflight = self._inflight[execution_id]
        inflight.acked = True
        logger.info(
            f"[AgentWS] Task {execution_id} acknowledged by "
            f"client {client.client_id}"
        )
        return None

    def _handle_progress(
        self,
        client: AgentClient,
        data: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Handle progress update from IDE."""
        execution_id = data.get("execution_id", "")

        err = self._verify_ownership(client, execution_id)
        if err:
            return err

        progress = data.get("progress", {})
        logger.debug(
            f"[AgentWS] Progress for {execution_id}: "
            f"{progress.get('percent', '?')}% - {progress.get('message', '')}"
        )
        # Progress could be forwarded to the UI via graph_websocket or SSE
        return None

    def _handle_result(
        self,
        client: AgentClient,
        data: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        Handle task execution result from IDE.

        Resolves the Future for dispatch_and_wait callers.
        """
        execution_id = data.get("execution_id", "")

        # Check ownership before popping (use get first)
        err = self._verify_ownership(client, execution_id)
        if err:
            return err

        inflight = self._inflight.pop(execution_id, None)

        if not inflight:
            logger.warning(
                f"[AgentWS] Result for unknown/completed execution {execution_id}"
            )
            return None

        # Build result dict
        result = {
            "execution_id": execution_id,
            "status": data.get("status", "completed"),
            "output": data.get("output", ""),
            "duration_seconds": data.get("duration_seconds", 0),
            "tool_calls": data.get("tool_calls", []),
            "files_modified": data.get("files_modified", []),
            "files_created": data.get("files_created", []),
            "error": data.get("error"),
            "governance": data.get("governance", {}),
            "metadata": {
                **data.get("metadata", {}),
                "transport": "ws_push",
                "client_id": client.client_id,
                "surface_type": client.surface_type,
            },
        }

        # Resolve the future
        if inflight.result_future and not inflight.result_future.done():
            inflight.result_future.set_result(result)

        # Track completion for idempotency (prevents duplicate re-queue)
        self._completed[execution_id] = time.monotonic()
        while len(self._completed) > self.COMPLETED_MAX_SIZE:
            self._completed.popitem(last=False)  # FIFO eviction

        logger.info(
            f"[AgentWS] Result received for {execution_id}: "
            f"status={data.get('status', 'unknown')}"
        )

        return {
            "type": "result_ack",
            "execution_id": execution_id,
        }
