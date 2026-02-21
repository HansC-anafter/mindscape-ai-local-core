"""
Agent Dispatch -- Task dispatch and WebSocket message handling mixin.

Covers dispatch_and_wait, pending queue management, flush,
and incoming message routing (ack, progress, result).
"""

import asyncio
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

from .models import AgentClient, InflightTask, PendingTask
from .connection_manager import _get_core_db_connection

logger = logging.getLogger(__name__)


class TaskDispatchMixin:
    """Mixin: task dispatch, pending queue, and WS message handling."""

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
            target_client_id: Optional specific client to target
            timeout: Max seconds to wait for result (default 600s)

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
            # No local client -- check for remote WS connections
            has_remote = False
            try:
                has_remote = self.has_connections(workspace_id) and True
            except Exception:
                pass

            if has_remote:
                # Cross-worker dispatch: write to DB, poll for result
                logger.info(
                    f"[AgentWS] No local client for {workspace_id}, "
                    f"dispatching cross-worker for {execution_id}"
                )
                return await self._cross_worker_dispatch(
                    workspace_id=workspace_id,
                    message=message,
                    execution_id=execution_id,
                    timeout=timeout,
                )

            # No client available anywhere -- queue for later
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
                payload=message,
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
            # Update cross-worker heartbeat in PostgreSQL
            try:
                self._db_update_heartbeat(client.client_id)
            except Exception:
                pass
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
        """Handle progress update from IDE and persist to inflight state."""
        execution_id = data.get("execution_id", "")

        err = self._verify_ownership(client, execution_id)
        if err:
            return err

        progress = data.get("progress", {})
        percent = progress.get("percent", 0)
        message = progress.get("message", "")

        # Update inflight task metadata
        inflight = self._inflight.get(execution_id)
        if inflight:
            inflight.last_progress_pct = percent
            inflight.last_progress_msg = message

        logger.info(
            f"[AgentWS] Progress for {execution_id}: " f"{percent}% - {message}"
        )

        # Best-effort: update task status in DB
        try:
            from backend.app.services.stores.tasks_store import TasksStore
            from backend.app.models.workspace import TaskStatus

            tasks_store = TasksStore()
            db_task = tasks_store.get_task(execution_id)
            if db_task and db_task.status in (
                TaskStatus.PENDING,
                TaskStatus.RUNNING,
            ):
                if db_task.status == TaskStatus.PENDING:
                    tasks_store.update_task_status(
                        task_id=execution_id,
                        status=TaskStatus.RUNNING,
                    )
        except Exception:
            pass  # Non-blocking, best-effort

        return None

    def _handle_result(
        self,
        client: AgentClient,
        data: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        Handle task execution result from IDE.

        Persists result to DB (source of truth), resolves the in-memory
        Future for dispatch_and_wait callers, and lands the result to
        workspace filesystem.
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

        result_status = data.get("status", "unknown")

        # Persist result to DB (source of truth)
        workspace_id = inflight.workspace_id
        try:
            from backend.app.services.stores.tasks_store import TasksStore
            from backend.app.models.workspace import TaskStatus

            tasks_store = TasksStore()
            db_task = tasks_store.get_task(execution_id)
            if db_task and db_task.status in (
                TaskStatus.PENDING,
                TaskStatus.RUNNING,
            ):
                task_status = (
                    TaskStatus.SUCCEEDED
                    if result_status == "completed"
                    else TaskStatus.FAILED
                )
                from datetime import datetime, timezone

                tasks_store.update_task_status(
                    task_id=execution_id,
                    status=task_status,
                    result=result,
                    error=data.get("error"),
                    completed_at=datetime.now(timezone.utc),
                )
                logger.info(
                    f"[AgentWS] DB persisted WS result for {execution_id} "
                    f"(status={task_status.value})"
                )
        except Exception:
            logger.exception(f"[AgentWS] DB write failed for WS result {execution_id}")

        # Land result to workspace filesystem (best-effort)
        try:
            from app.services.task_result_landing import TaskResultLandingService
            from app.services.stores.postgres.workspaces_store import (
                PostgresWorkspacesStore,
            )

            if workspace_id:
                ws_store = PostgresWorkspacesStore()
                # Use sync wrapper since this handler is sync
                import asyncio

                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Schedule as a background task
                    asyncio.ensure_future(
                        self._land_ws_result(workspace_id, execution_id, result)
                    )
                else:
                    logger.warning(
                        f"[AgentWS] No running loop for result landing "
                        f"{execution_id}"
                    )
        except Exception:
            logger.exception(
                f"[AgentWS] Result landing setup failed for {execution_id} "
                f"(non-blocking)"
            )

        # Resolve the future
        if inflight.result_future and not inflight.result_future.done():
            inflight.result_future.set_result(result)

        # Track completion for idempotency (prevents duplicate re-queue)
        self._completed[execution_id] = time.monotonic()
        while len(self._completed) > self.COMPLETED_MAX_SIZE:
            self._completed.popitem(last=False)  # FIFO eviction

        logger.info(
            f"[AgentWS] Result received for {execution_id}: " f"status={result_status}"
        )
        if result_status not in ("completed", "dispatched_to_ide"):
            logger.warning(
                f"[AgentWS] DIAGNOSTIC: Non-success result for {execution_id}. "
                f"error={data.get('error')!r}, "
                f"output={str(data.get('output', ''))[:500]!r}, "
                f"client_id={client.client_id}, "
                f"surface_type={client.surface_type}, "
                f"raw_keys={list(data.keys())}"
            )

        return {
            "type": "result_ack",
            "execution_id": execution_id,
        }

    async def _land_ws_result(
        self,
        workspace_id: str,
        execution_id: str,
        result: Dict[str, Any],
    ) -> None:
        """Land WS result to workspace filesystem (async helper)."""
        try:
            from app.services.task_result_landing import TaskResultLandingService
            from app.services.stores.postgres.workspaces_store import (
                PostgresWorkspacesStore,
            )

            ws_store = PostgresWorkspacesStore()
            ws = await ws_store.get_workspace(workspace_id)
            storage_base = getattr(ws, "storage_base_path", None) if ws else None
            artifacts_dir = getattr(ws, "artifacts_dir", None) or "artifacts"

            landing = TaskResultLandingService()
            landing.land_result(
                workspace_id=workspace_id,
                execution_id=execution_id,
                result_data=result,
                storage_base_path=storage_base,
                artifacts_dirname=artifacts_dir,
            )
            logger.info(
                f"[AgentWS] WS result landed for {execution_id} "
                f"(storage={storage_base or 'DB-only'})"
            )
        except Exception:
            logger.exception(
                f"[AgentWS] WS result landing failed for {execution_id} "
                f"(non-blocking)"
            )

    # ============================================================
    #  Cross-worker dispatch (DB-mediated)
    # ============================================================

    async def _cross_worker_dispatch(
        self,
        workspace_id: str,
        message: Dict[str, Any],
        execution_id: str,
        timeout: float = 600.0,
    ) -> Dict[str, Any]:
        """Dispatch a task via PostgreSQL for a remote worker to pick up.

        Flow:
          1. INSERT into pending_dispatch (status='pending')
          2. Poll pending_dispatch.result_data for completed result
          3. Return result or timeout error
        """
        # Write task to pending_dispatch
        try:
            await asyncio.to_thread(
                self._db_insert_pending_dispatch,
                execution_id,
                workspace_id,
                message,
            )
        except Exception as e:
            logger.exception(
                f"[AgentWS] Failed to insert pending_dispatch " f"for {execution_id}"
            )
            return {
                "execution_id": execution_id,
                "status": "failed",
                "error": f"Cross-worker dispatch failed: {e}",
            }

        # Poll pending_dispatch for result written by consumer worker
        poll_interval = 0.5
        start = time.monotonic()
        while (time.monotonic() - start) < timeout:
            try:
                result = await asyncio.to_thread(
                    self._db_poll_pending_result, execution_id
                )
                if result is not None:
                    logger.info(
                        f"[AgentWS] Cross-worker result received " f"for {execution_id}"
                    )
                    return result
            except Exception:
                pass
            await asyncio.sleep(poll_interval)

        # Timeout
        try:
            await asyncio.to_thread(
                self._db_update_pending_status, execution_id, "timeout"
            )
        except Exception:
            pass

        logger.error(
            f"[AgentWS] Cross-worker dispatch timed out "
            f"for {execution_id} after {timeout}s"
        )
        return {
            "execution_id": execution_id,
            "status": "timeout",
            "error": f"No result received within {timeout}s (cross-worker)",
        }

    async def consume_pending_dispatches(self) -> None:
        """Background task: poll pending_dispatch and dispatch locally.

        Run this only on workers that have local WS connections.
        Picks pending tasks, dispatches them via local WS, awaits
        the result future, and writes result back to pending_dispatch.
        """
        logger.info(
            f"[AgentWS] Starting pending dispatch consumer "
            f"(worker pid={os.getpid()})"
        )
        while True:
            try:
                # Only consume if this worker has local WS connections
                if not self.has_local_connections():
                    await asyncio.sleep(1.0)
                    continue

                rows = await asyncio.to_thread(
                    self._db_pick_pending_dispatches, limit=5
                )
                if not rows:
                    await asyncio.sleep(0.5)
                    continue

                for row in rows:
                    exec_id = row["execution_id"]
                    ws_id = row["workspace_id"]
                    payload = row["payload"]

                    logger.info(
                        f"[AgentWS] Consumer picked cross-worker task "
                        f"{exec_id} for workspace {ws_id}"
                    )

                    # Dispatch via local WS (get_client will find local)
                    client = self.get_client(ws_id)
                    if not client:
                        logger.warning(
                            f"[AgentWS] No local client for {ws_id} "
                            f"despite having connections"
                        )
                        await asyncio.to_thread(
                            self._db_update_pending_status, exec_id, "pending"
                        )
                        continue

                    # Create inflight entry for this task
                    loop = asyncio.get_event_loop()
                    result_future: asyncio.Future = loop.create_future()
                    inflight = InflightTask(
                        execution_id=exec_id,
                        workspace_id=ws_id,
                        client_id=client.client_id,
                        result_future=result_future,
                        payload=payload,
                    )
                    self._inflight[exec_id] = inflight

                    try:
                        await client.websocket.send_text(json.dumps(payload))
                        logger.info(
                            f"[AgentWS] Consumer dispatched {exec_id} to "
                            f"client {client.client_id}"
                        )
                    except Exception as e:
                        self._inflight.pop(exec_id, None)
                        logger.error(
                            f"[AgentWS] Consumer failed to send " f"{exec_id}: {e}"
                        )
                        # Write failure result to pending_dispatch
                        fail_result = {
                            "execution_id": exec_id,
                            "status": "failed",
                            "error": f"Consumer dispatch failed: {e}",
                        }
                        await asyncio.to_thread(
                            self._db_write_pending_result,
                            exec_id,
                            fail_result,
                        )
                        continue

                    # Await the result from _handle_result
                    try:
                        result = await asyncio.wait_for(result_future, timeout=600.0)
                        logger.info(
                            f"[AgentWS] Consumer got result for "
                            f"{exec_id}: status={result.get('status')}"
                        )
                        # Write result to pending_dispatch for
                        # the originating worker to pick up
                        await asyncio.to_thread(
                            self._db_write_pending_result,
                            exec_id,
                            result,
                        )
                    except asyncio.TimeoutError:
                        self._inflight.pop(exec_id, None)
                        logger.error(
                            f"[AgentWS] Consumer timed out waiting "
                            f"for result on {exec_id}"
                        )
                        timeout_result = {
                            "execution_id": exec_id,
                            "status": "timeout",
                            "error": "Consumer-side timeout (120s)",
                        }
                        await asyncio.to_thread(
                            self._db_write_pending_result,
                            exec_id,
                            timeout_result,
                        )

            except Exception:
                logger.exception("[AgentWS] Error in pending dispatch consumer")
                await asyncio.sleep(2.0)

    # ============================================================
    #  DB helpers for cross-worker dispatch
    # ============================================================

    @staticmethod
    def _db_insert_pending_dispatch(
        execution_id: str,
        workspace_id: str,
        payload: Dict[str, Any],
    ) -> None:
        """Insert a task into pending_dispatch table."""
        conn = _get_core_db_connection()
        if not conn:
            raise RuntimeError("No core DB connection")
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO pending_dispatch "
                    "(execution_id, workspace_id, payload, status) "
                    "VALUES (%s, %s, %s, 'pending') "
                    "ON CONFLICT (execution_id) DO NOTHING",
                    (execution_id, workspace_id, json.dumps(payload)),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def _db_poll_pending_result(
        execution_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Poll pending_dispatch.result_data for a completed result."""
        conn = _get_core_db_connection()
        if not conn:
            return None
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT result_data, status FROM pending_dispatch "
                    "WHERE execution_id = %s",
                    (execution_id,),
                )
                row = cur.fetchone()
                if not row:
                    return None
                result_data, status = row
                if status == "done" and result_data is not None:
                    if isinstance(result_data, str):
                        return json.loads(result_data)
                    return result_data
                return None
        finally:
            conn.close()

    @staticmethod
    def _db_write_pending_result(
        execution_id: str,
        result: Dict[str, Any],
    ) -> None:
        """Write result_data to pending_dispatch for cross-worker retrieval."""
        conn = _get_core_db_connection()
        if not conn:
            return
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE pending_dispatch "
                    "SET result_data = %s, status = 'done', "
                    "completed_at = NOW() "
                    "WHERE execution_id = %s",
                    (json.dumps(result), execution_id),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            logger.exception(
                f"[AgentWS] Failed to write result to "
                f"pending_dispatch for {execution_id}"
            )
        finally:
            conn.close()

    @staticmethod
    def _db_update_pending_status(execution_id: str, status: str) -> None:
        """Update pending_dispatch status."""
        conn = _get_core_db_connection()
        if not conn:
            return
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE pending_dispatch SET status = %s "
                    "WHERE execution_id = %s",
                    (status, execution_id),
                )
            conn.commit()
        except Exception:
            conn.rollback()
        finally:
            conn.close()

    @staticmethod
    def _db_pick_pending_dispatches(limit: int = 5) -> List[Dict[str, Any]]:
        """Pick pending tasks atomically using FOR UPDATE SKIP LOCKED."""
        conn = _get_core_db_connection()
        if not conn:
            return []
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, execution_id, workspace_id, payload "
                    "FROM pending_dispatch "
                    "WHERE status = 'pending' "
                    "ORDER BY created_at ASC "
                    "LIMIT %s "
                    "FOR UPDATE SKIP LOCKED",
                    (limit,),
                )
                rows = cur.fetchall()
                if not rows:
                    conn.rollback()
                    return []

                result = []
                for row in rows:
                    row_id, exec_id, ws_id, payload_data = row
                    cur.execute(
                        "UPDATE pending_dispatch "
                        "SET status = 'picked', picked_by_pid = %s, "
                        "picked_at = NOW() "
                        "WHERE id = %s",
                        (os.getpid(), row_id),
                    )
                    # Parse payload
                    if isinstance(payload_data, str):
                        payload_data = json.loads(payload_data)
                    result.append(
                        {
                            "execution_id": exec_id,
                            "workspace_id": ws_id,
                            "payload": payload_data,
                        }
                    )

                conn.commit()
                return result
        except Exception:
            conn.rollback()
            return []
        finally:
            conn.close()
