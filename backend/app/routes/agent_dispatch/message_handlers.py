"""
Agent Dispatch -- WS message handlers mixin.

Handles incoming messages from IDE clients: ack, progress, result,
ownership verification, and result landing to workspace filesystem.
"""

import asyncio
import json
import logging
import time
from typing import Any, Dict, Optional

from .models import AgentClient, InflightTask

logger = logging.getLogger(__name__)


class MessageHandlersMixin:
    """Mixin: incoming WS message routing and result handling."""

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

        Relaxed ownership: allows same-workspace clients to submit
        results for re-queued ('pending') or orphaned tasks after
        a client disconnect/reconnect cycle.

        Returns error dict if ownership fails, None if verified.
        """
        inflight = self._inflight.get(execution_id)
        if not inflight:
            return {
                "type": "error",
                "error": f"Unknown execution {execution_id}",
            }

        # Exact match -- original client still owns the task
        if inflight.client_id == client.client_id:
            return None

        # Re-queued task ('pending') -- any authenticated client may claim
        if inflight.client_id == "pending":
            logger.info(
                f"[AgentWS] Accepting result from {client.client_id} "
                f"for re-queued task {execution_id}"
            )
            return None

        # Same workspace -- allow result from sibling client
        # (handles reconnect with new client_id)
        if inflight.workspace_id == client.workspace_id:
            logger.info(
                f"[AgentWS] Accepting result from {client.client_id} "
                f"for task {execution_id} originally assigned to "
                f"{inflight.client_id} (same workspace)"
            )
            return None

        logger.warning(
            f"[AgentWS] Unauthorized: expected={inflight.client_id}, "
            f"got={client.client_id} for {execution_id} "
            f"(workspace mismatch: {inflight.workspace_id} vs {client.workspace_id})"
        )
        return {
            "type": "error",
            "error": "Not the assigned client",
        }

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
        if inflight.origin_worker_id:
            asyncio.create_task(
                self._relay_to_origin_worker(
                    inflight,
                    "dispatch_ack",
                    client_id=client.client_id,
                )
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
            inflight.last_progress_at = time.monotonic()
            if inflight.origin_worker_id:
                asyncio.create_task(
                    self._relay_to_origin_worker(
                        inflight,
                        "dispatch_progress",
                        client_id=client.client_id,
                        progress_pct=percent,
                        message=message,
                    )
                )

        logger.info(
            f"[AgentWS] Progress for {execution_id}: " f"{percent}% - {message}"
        )

        # Update cross-worker progress timestamp in DB
        try:
            self._db_update_pending_progress(execution_id)
        except Exception:
            pass  # Non-blocking

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

        # Land result to workspace filesystem via GovernanceEngine (best-effort)
        try:
            if workspace_id:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Schedule as a background task
                    asyncio.ensure_future(
                        self._land_ws_result(
                            workspace_id,
                            execution_id,
                            result,
                            thread_id=inflight.thread_id,
                            project_id=inflight.project_id,
                        )
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

        if inflight.origin_worker_id:
            asyncio.create_task(
                self._relay_to_origin_worker(
                    inflight,
                    "dispatch_result",
                    client_id=client.client_id,
                    result=result,
                )
            )

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
        thread_id: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> None:
        """Land a WebSocket result via GovernanceEngine."""
        try:
            from backend.app.services.orchestration.governance_engine import (
                GovernanceEngine,
            )
            from app.services.stores.postgres.workspaces_store import (
                PostgresWorkspacesStore,
            )

            ws_store = PostgresWorkspacesStore()
            ws = await ws_store.get_workspace(workspace_id)
            storage_base = getattr(ws, "storage_base_path", None) if ws else None
            artifacts_dir = getattr(ws, "artifacts_dir", None) or "artifacts"

            governance = GovernanceEngine()
            governance.process_completion(
                workspace_id=workspace_id,
                execution_id=execution_id,
                result_data=result,
                storage_base_path=storage_base,
                artifacts_dirname=artifacts_dir,
                thread_id=thread_id,
                project_id=project_id,
            )
            logger.info(
                f"[AgentWS] WS result landed via GovernanceEngine for {execution_id} "
                f"(storage={storage_base or 'DB-only'}, "
                f"thread_id={thread_id or 'none'}, "
                f"project_id={project_id or 'none'})"
            )
        except Exception:
            logger.exception(
                f"[AgentWS] GovernanceEngine WS result landing failed for {execution_id} "
                f"(non-blocking)"
            )
