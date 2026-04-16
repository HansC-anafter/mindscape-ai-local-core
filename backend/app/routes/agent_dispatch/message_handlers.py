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

from backend.app.services.compile_job_reconciler import (
    closed_session_compile_failed,
    summarize_meeting_session_tasks,
)

from .models import AgentClient, InflightTask
from .result_payloads import merge_dispatch_transport_inputs

logger = logging.getLogger(__name__)


class MessageHandlersMixin:
    """Mixin: incoming WS message routing and result handling."""

    @staticmethod
    def _log_background_task_failure(task: asyncio.Task) -> None:
        try:
            exc = task.exception()
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("[AgentWS] Background result task inspection failed")
            return
        if exc is not None:
            logger.exception("[AgentWS] Background result task failed", exc_info=exc)

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
        elif msg_type == "resume_state":
            return self._handle_resume_state(client, data)
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
        started_at = time.monotonic()
        logger.info(
            "[AgentWS] Begin result handling: client=%s surface=%s execution_id=%s",
            client.client_id,
            client.surface_type,
            execution_id,
        )

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

        # Resolve the future
        if inflight.result_future and not inflight.result_future.done():
            inflight.result_future.set_result(result)

        # Track completion for idempotency and reconnect replay.
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

    async def _finalize_result_processing(
        self,
        *,
        client: AgentClient,
        inflight: InflightTask,
        execution_id: str,
        result: Dict[str, Any],
        result_status: str,
        raw_error: Optional[str],
        started_at: float,
    ) -> None:
        workspace_id = inflight.workspace_id

        persisted_task = None
        try:
            persisted_task = await asyncio.to_thread(
                self._persist_ws_result_to_db,
                execution_id,
                result_status,
                result,
                raw_error,
            )
        except Exception:
            logger.exception(f"[AgentWS] DB write failed for WS result {execution_id}")

        if inflight.origin_worker_id:
            try:
                await self._relay_to_origin_worker(
                    inflight,
                    "dispatch_result",
                    client_id=client.client_id,
                    result=result,
                )
            except Exception:
                logger.exception(
                    f"[AgentWS] Origin worker relay failed for {execution_id}"
                )

        governance_result = None
        if workspace_id:
            try:
                governance_result = await self._land_ws_result(
                    workspace_id,
                    execution_id,
                    result,
                    thread_id=inflight.thread_id,
                    project_id=inflight.project_id,
                )
            except Exception:
                logger.exception(
                    f"[AgentWS] Result landing failed for {execution_id} (non-blocking)"
                )

        if governance_result and not governance_result.get("success", True):
            self._mark_ws_result_failed_after_landing(
                execution_id=execution_id,
                result=result,
                governance_result=governance_result,
            )

        try:
            meeting_session_id = getattr(persisted_task, "meeting_session_id", None)
            if meeting_session_id:
                await asyncio.to_thread(
                    self._reconcile_compile_job_after_task_terminal,
                    meeting_session_id,
                )
        except Exception:
            logger.exception(
                "[AgentWS] Compile job terminal reconcile failed for execution %s",
                execution_id,
            )

        logger.info(
            f"[AgentWS] Result finalized for {execution_id}: "
            f"status={result_status} finalize_ms={int((time.monotonic() - started_at) * 1000)}"
        )

    @staticmethod
    def _persist_ws_result_to_db(
        execution_id: str,
        result_status: str,
        result: Dict[str, Any],
        raw_error: Optional[str],
    ):
        from datetime import datetime, timezone

        from backend.app.models.workspace import TaskStatus
        from backend.app.services.stores.tasks_store import TasksStore

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
            db_task = tasks_store.update_task_status(
                task_id=execution_id,
                status=task_status,
                result=result,
                error=raw_error,
                completed_at=datetime.now(timezone.utc),
            )
        return db_task

    @staticmethod
    def _reconcile_compile_job_after_task_terminal(meeting_session_id: str) -> None:
        from backend.app.models.compile_job import CompileJobStatus
        from backend.app.models.meeting_session import MeetingStatus
        from backend.app.services.stores.compile_job_store import CompileJobStore
        from backend.app.services.stores.meeting_session_store import (
            MeetingSessionStore,
        )

        meeting_session_store = MeetingSessionStore()
        compile_job_store = CompileJobStore()

        session = meeting_session_store.get_by_id(meeting_session_id)
        if session is None:
            return

        compile_job = compile_job_store.get_latest_for_session(meeting_session_id)
        compile_job_status = (
            compile_job.status.value if hasattr(compile_job.status, "value") else compile_job.status
        ) if compile_job is not None else None
        if compile_job is None or compile_job_status in {
            CompileJobStatus.SUCCEEDED.value,
            CompileJobStatus.FAILED.value,
        }:
            return

        task_summary = summarize_meeting_session_tasks(meeting_session_id)
        metadata = {
            "session_terminal_reconciled_at": getattr(session, "ended_at", None)
            and session.ended_at.isoformat()
            or None,
            "session_terminal_status": (
                getattr(session.status, "value", session.status)
            ),
            "session_task_total": task_summary["total"],
            "session_incomplete_tasks": task_summary["incomplete"],
            "session_task_statuses": task_summary["statuses"],
            "recovery_reason": "agent_result_terminal_reconcile",
        }

        if session.status == MeetingStatus.CLOSED and task_summary["terminal"]:
            dispatch_status = (getattr(session, "metadata", None) or {}).get(
                "dispatch_status"
            )
            if closed_session_compile_failed(
                task_summary,
                dispatch_status=dispatch_status,
            ):
                compile_job_store.mark_failed(
                    compile_job.id,
                    "meeting_session_closed_with_all_failed_tasks",
                    session_id=session.id,
                    metadata={**metadata, "dispatch_status": dispatch_status},
                )
            else:
                compile_job_store.mark_succeeded(
                    compile_job.id,
                    session_id=session.id,
                    result={
                        "session_id": session.id,
                        "meeting_status": "closed",
                        "decision": getattr(session, "decision", None),
                        "action_items_count": len(getattr(session, "action_items", []) or []),
                        "dispatch_status": dispatch_status,
                        "phase_results": [],
                        "program_run_id": (getattr(session, "metadata", None) or {}).get(
                            "program_run_id"
                        ),
                        "session_task_total": task_summary["total"],
                        "session_task_statuses": task_summary["statuses"],
                    },
                    metadata={**metadata, "dispatch_status": dispatch_status},
                )
        elif session.status == MeetingStatus.FAILED:
            compile_job_store.mark_failed(
                compile_job.id,
                "meeting_session_failed",
                session_id=session.id,
                metadata=metadata,
            )

    @staticmethod
    def _mark_ws_result_failed_after_landing(
        *,
        execution_id: str,
        result: Dict[str, Any],
        governance_result: Dict[str, Any],
    ) -> None:
        from datetime import datetime, timezone

        from backend.app.models.workspace import TaskStatus
        from backend.app.services.stores.tasks_store import TasksStore

        landing_failure = governance_result.get("landing_failure") or {}
        if not isinstance(landing_failure, dict):
            landing_failure = {}
        error_message = (
            str(landing_failure.get("message") or "").strip()
            or str(landing_failure.get("error_code") or "").strip()
            or "deliverable landing failed"
        )

        tasks_store = TasksStore()
        task = tasks_store.get_task(execution_id)
        if not task:
            logger.warning(
                "[AgentWS] Landing failure for %s could not update task: not found",
                execution_id,
            )
            return

        existing_result = getattr(task, "result", None)
        merged_result = dict(existing_result) if isinstance(existing_result, dict) else {}
        merged_result.update(result or {})
        merged_result["landing_failure"] = dict(landing_failure)
        governance_payload = (
            dict(merged_result.get("governance"))
            if isinstance(merged_result.get("governance"), dict)
            else {}
        )
        governance_payload["landing_failure"] = dict(landing_failure)
        merged_result["governance"] = governance_payload

        tasks_store.update_task_status(
            task_id=execution_id,
            status=TaskStatus.FAILED,
            result=merged_result,
            error=error_message,
            completed_at=datetime.now(timezone.utc),
        )
        logger.warning(
            "[AgentWS] Marked %s failed after governed landing error: %s",
            execution_id,
            error_message,
        )

    async def _land_ws_result(
        self,
        workspace_id: str,
        execution_id: str,
        result: Dict[str, Any],
        thread_id: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> Dict[str, Any]:
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
            governance_result = await asyncio.to_thread(
                governance.process_completion,
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
            if not isinstance(governance_result, dict):
                governance_result = {"success": False}
            self._mark_completed_execution(
                execution_id,
                result=result,
                status=str(result.get("status") or "completed"),
                landing_succeeded=bool(governance_result.get("success")),
                error=str(
                    (governance_result.get("landing_failure") or {}).get("message")
                    or ""
                ).strip()
                or None,
            )
            return governance_result
        except Exception:
            logger.exception(
                f"[AgentWS] GovernanceEngine WS result landing failed for {execution_id} "
                f"(non-blocking)"
            )
            self._mark_completed_execution(
                execution_id,
                result=result,
                status=str(result.get("status") or "completed"),
                landing_succeeded=False,
                error="governance_landing_exception",
            )
            return {
                "success": False,
                "landing_failure": {
                    "error_code": "governance_landing_exception",
                    "message": "GovernanceEngine WS result landing failed",
                },
            }
