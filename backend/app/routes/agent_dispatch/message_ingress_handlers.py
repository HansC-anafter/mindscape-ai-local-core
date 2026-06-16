"""
Agent Dispatch -- incoming WS message routing and ingress handlers.
"""

import asyncio
import logging
import time
from typing import Any, Dict, Optional

from .models import AgentClient
from .result_payloads import merge_dispatch_transport_inputs

logger = logging.getLogger("backend.app.routes.agent_dispatch.message_handlers")


class MessageIngressHandlersMixin:
    """Mixin: incoming WS message routing, ownership, and ingress updates."""

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
        elif msg_type == "resume_state":
            return self._handle_resume_state(client, data)
        elif msg_type == "ping":
            client.last_heartbeat = time.monotonic()
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

        if inflight.client_id == client.client_id:
            return None

        if inflight.client_id == "pending":
            logger.info(
                f"[AgentWS] Accepting result from {client.client_id} "
                f"for re-queued task {execution_id}"
            )
            return None

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

    def _handle_resume_state(
        self,
        client: AgentClient,
        data: Dict[str, Any],
    ) -> Dict[str, Any]:
        recent_execution_ids = data.get("recent_execution_ids") or []
        pending_rest_execution_ids = data.get("pending_rest_execution_ids") or []
        last_completed_at = data.get("last_completed_at")
        if not isinstance(recent_execution_ids, list):
            recent_execution_ids = []
        if not isinstance(pending_rest_execution_ids, list):
            pending_rest_execution_ids = []
        if not isinstance(last_completed_at, (int, float)):
            last_completed_at = None

        response = self._build_resume_sync(
            workspace_id=client.workspace_id,
            recent_execution_ids=recent_execution_ids,
            pending_rest_execution_ids=pending_rest_execution_ids,
            last_completed_at=last_completed_at,
        )
        logger.info(
            "[AgentWS] Resume sync for client=%s workspace=%s replay=%d requeue=%d dup=%d",
            client.client_id,
            client.workspace_id,
            len(response.get("replayed_completions") or []),
            len(response.get("tasks_to_requeue") or []),
            len(response.get("duplicates_to_ignore") or []),
        )
        return response

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

        try:
            self._db_update_pending_progress(execution_id)
        except Exception:
            pass

        try:
            from backend.app.models.workspace import TaskStatus
            from backend.app.services.stores.tasks_store import TasksStore

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
            pass

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
        started_at = time.monotonic()
        logger.info(
            "[AgentWS] Begin result handling: client=%s surface=%s execution_id=%s",
            client.client_id,
            client.surface_type,
            execution_id,
        )

        err = self._verify_ownership(client, execution_id)
        if err:
            return err

        inflight = self._inflight.pop(execution_id, None)

        if not inflight:
            logger.warning(
                f"[AgentWS] Result for unknown/completed execution {execution_id}"
            )
            return None

        result = {
            "execution_id": execution_id,
            "status": data.get("status", "completed"),
            "output": data.get("output", ""),
            "duration_seconds": data.get("duration_seconds", 0),
            "tool_calls": data.get("tool_calls", []),
            "attachments": data.get("attachments", []),
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
        result = merge_dispatch_transport_inputs(result, inflight.payload or {})

        result_status = data.get("status", "unknown")

        try:
            self._db_write_pending_result(execution_id, result)
        except Exception:
            logger.exception(
                "[AgentWS] Failed to persist durable WS result for %s",
                execution_id,
            )

        if inflight.result_future and not inflight.result_future.done():
            inflight.result_future.set_result(result)

        self._mark_completed_execution(
            execution_id,
            result=result,
            status=result_status,
        )

        logger.info(
            f"[AgentWS] Result accepted for {execution_id}: "
            f"status={result_status} ack_ready_ms={int((time.monotonic() - started_at) * 1000)}"
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

        finalize_task = asyncio.create_task(
            self._finalize_result_processing(
                client=client,
                inflight=inflight,
                execution_id=execution_id,
                result=result,
                result_status=result_status,
                raw_error=data.get("error"),
                started_at=started_at,
            )
        )
        finalize_task.add_done_callback(self._log_background_task_failure)

        return {
            "type": "result_ack",
            "execution_id": execution_id,
        }
