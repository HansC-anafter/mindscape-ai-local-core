"""
Agent Dispatch -- WS result finalization, landing, and compile reconciliation.
"""

import asyncio
import logging
import time
from typing import Any, Dict, Optional

from backend.app.services.compile_job_reconciler import (
    closed_session_compile_failed,
    summarize_meeting_session_tasks,
)

from .models import AgentClient, InflightTask

logger = logging.getLogger("backend.app.routes.agent_dispatch.message_handlers")


class MessageResultFinalizationMixin:
    """Mixin: side-effect finalization after WS result acknowledgement."""

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
            from backend.app.services.meeting_command_status_sync import (
                sync_meeting_command_from_agent_result,
            )

            await asyncio.to_thread(
                sync_meeting_command_from_agent_result,
                execution_id=execution_id,
                result=result,
                governance_result=governance_result,
                status=result_status,
            )
        except Exception:
            logger.debug(
                "[AgentWS] Meeting command late-result sync skipped for %s",
                execution_id,
                exc_info=True,
            )

        try:
            meeting_session_id = self._resolve_meeting_session_id_for_result(
                persisted_task=persisted_task,
                inflight=inflight,
                result=result,
            )
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
    def _resolve_meeting_session_id_for_result(
        *,
        persisted_task: Any,
        inflight: InflightTask,
        result: Dict[str, Any],
    ) -> Optional[str]:
        meeting_session_id = getattr(persisted_task, "meeting_session_id", None)
        if isinstance(meeting_session_id, str) and meeting_session_id.strip():
            return meeting_session_id.strip()

        candidate_maps = []
        if isinstance(result, dict):
            candidate_maps.append(result)
            metadata = result.get("metadata")
            if isinstance(metadata, dict):
                candidate_maps.append(metadata)

        payload = inflight.payload if isinstance(inflight.payload, dict) else {}
        if payload:
            candidate_maps.extend(
                [
                    payload,
                    payload.get("context"),
                    payload.get("inputs"),
                    payload.get("metadata"),
                    payload.get("execution_context"),
                ]
            )

        for candidate in candidate_maps:
            if not isinstance(candidate, dict):
                continue
            for key in ("meeting_session_id", "session_id"):
                value = candidate.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()

        workspace_id = getattr(inflight, "workspace_id", None)
        project_id = getattr(inflight, "project_id", None)
        thread_id = getattr(inflight, "thread_id", None)
        if workspace_id and project_id:
            try:
                from backend.app.services.stores.meeting_session_store import (
                    MeetingSessionStore,
                )

                session = MeetingSessionStore().get_active_session(
                    workspace_id,
                    project_id,
                    thread_id,
                )
                if session is not None and getattr(session, "id", None):
                    return session.id
            except Exception:
                logger.debug(
                    "[AgentWS] Active meeting session lookup failed for workspace=%s project=%s thread=%s",
                    workspace_id,
                    project_id,
                    thread_id,
                )
        return None

    @staticmethod
    def _reconcile_compile_job_after_task_terminal(meeting_session_id: str) -> None:
        try:
            from backend.app.models.compile_job import CompileJobStatus
            from backend.app.models.meeting_session import MeetingStatus
            from backend.app.services.stores.compile_job_store import CompileJobStore
            from backend.app.services.stores.meeting_session_store import (
                MeetingSessionStore,
            )
        except ImportError:
            logger.debug(
                "[AgentWS] Compile-job reconciliation skipped; compile-job source is unavailable"
            )
            return

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
            from app.services.stores.postgres.workspaces_store import (
                PostgresWorkspacesStore,
            )
            from backend.app.services.orchestration.governance_engine import (
                GovernanceEngine,
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
                workspace_id=workspace_id,
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
                workspace_id=workspace_id,
            )
            return {
                "success": False,
                "landing_failure": {
                    "error_code": "governance_landing_exception",
                    "message": "GovernanceEngine WS result landing failed",
                },
            }
