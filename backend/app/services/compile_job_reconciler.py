"""
Startup recovery for orphaned compile jobs.

Async compile currently runs in-process. If the backend restarts mid-compile,
accepted/running jobs can be stranded forever unless startup reconciles them
back to the persisted meeting session state.
"""

import logging
import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from backend.app.models.handoff import HandoffIn
from backend.app.models.meeting_session import MeetingStatus
from backend.app.models.workspace import TaskStatus
from backend.app.services.compile_job_task_registry import compile_job_task_registry
from backend.app.services.handoff_bundle_service import HandoffBundleService
from backend.app.services.stores.compile_job_store import CompileJobStore
from backend.app.services.stores.meeting_session_store import MeetingSessionStore
from backend.app.services.stores.tasks_store import TasksStore

logger = logging.getLogger(__name__)


def summarize_meeting_session_tasks(
    session_id: Optional[str],
    *,
    tasks_store: Optional[TasksStore] = None,
) -> Dict[str, Any]:
    if not session_id:
        return {
            "total": 0,
            "terminal": True,
            "incomplete": 0,
            "statuses": {},
        }

    store = tasks_store or TasksStore()
    tasks = store.list_tasks_by_meeting_session(session_id)
    statuses: Dict[str, int] = {}
    incomplete = 0

    for task in tasks:
        raw_status = getattr(task, "status", None)
        status = raw_status.value if hasattr(raw_status, "value") else str(raw_status)
        statuses[status] = statuses.get(status, 0) + 1
        if status in {TaskStatus.PENDING.value, TaskStatus.RUNNING.value}:
            incomplete += 1

    return {
        "total": len(tasks),
        "terminal": incomplete == 0,
        "incomplete": incomplete,
        "statuses": statuses,
    }


class CompileJobReconciler:
    """Reconcile orphaned compile jobs against meeting session truth."""

    def __init__(
        self,
        *,
        compile_job_store: Optional[CompileJobStore] = None,
        meeting_session_store: Optional[MeetingSessionStore] = None,
        tasks_store: Optional[TasksStore] = None,
    ) -> None:
        self._compile_job_store = compile_job_store or CompileJobStore()
        self._meeting_session_store = meeting_session_store or MeetingSessionStore()
        self._tasks_store = tasks_store or TasksStore()

    def reconcile_startup_orphans(self, *, limit: int = 200) -> Dict[str, int]:
        jobs = self._compile_job_store.list_incomplete(limit=limit)
        summary = {
            "inspected": len(jobs),
            "succeeded": 0,
            "failed": 0,
            "session_failed": 0,
        }

        for job in jobs:
            outcome = self._reconcile_job(job)
            if outcome == "succeeded":
                summary["succeeded"] += 1
            elif outcome == "failed":
                summary["failed"] += 1
            elif outcome == "failed_with_session_terminalized":
                summary["failed"] += 1
                summary["session_failed"] += 1

        if summary["inspected"] > 0:
            logger.warning(
                "Compile job startup reconcile inspected=%d succeeded=%d failed=%d session_failed=%d",
                summary["inspected"],
                summary["succeeded"],
                summary["failed"],
                summary["session_failed"],
            )
        else:
            logger.info("Compile job startup reconcile found no orphaned jobs")

        return summary

    async def dispatch_pending_accepted_jobs(
        self,
        *,
        limit: int = 50,
    ) -> Dict[str, int]:
        jobs = self._compile_job_store.list_accepted(limit=limit)
        summary = {
            "inspected": len(jobs),
            "resumed": 0,
            "succeeded": 0,
            "failed": 0,
            "session_failed": 0,
            "skipped": 0,
        }

        for job in jobs:
            outcome = await self._recover_job(
                job,
                claim_metadata={
                    "dispatch_reason": "runtime_queue_claim",
                    "queued_dispatch": True,
                },
                reconcile_reason="runtime_dispatch_reconcile",
                failure_stage="queued_dispatch",
            )
            if outcome == "resumed":
                summary["resumed"] += 1
            elif outcome == "succeeded":
                summary["succeeded"] += 1
            elif outcome == "failed":
                summary["failed"] += 1
            elif outcome == "failed_with_session_terminalized":
                summary["failed"] += 1
                summary["session_failed"] += 1
            elif outcome == "skipped":
                summary["skipped"] += 1

        if summary["inspected"] > 0:
            logger.info(
                "Compile job dispatch inspected=%d resumed=%d succeeded=%d failed=%d session_failed=%d skipped=%d",
                summary["inspected"],
                summary["resumed"],
                summary["succeeded"],
                summary["failed"],
                summary["session_failed"],
                summary["skipped"],
            )

        return summary

    async def recover_startup_orphans(self, *, limit: int = 200) -> Dict[str, int]:
        jobs = self._compile_job_store.list_incomplete(limit=limit)
        summary = {
            "inspected": len(jobs),
            "resumed": 0,
            "succeeded": 0,
            "failed": 0,
            "session_failed": 0,
            "skipped": 0,
        }

        for job in jobs:
            outcome = await self._recover_job(
                job,
                claim_metadata={
                    "recovery_reason": "startup_resume",
                    "recovered_from_startup": True,
                },
                reconcile_reason="startup_orphan_reconcile",
                failure_stage="startup_resume",
            )
            if outcome == "resumed":
                summary["resumed"] += 1
            elif outcome == "succeeded":
                summary["succeeded"] += 1
            elif outcome == "failed":
                summary["failed"] += 1
            elif outcome == "failed_with_session_terminalized":
                summary["failed"] += 1
                summary["session_failed"] += 1
            elif outcome == "skipped":
                summary["skipped"] += 1

        if summary["inspected"] > 0:
            logger.warning(
                "Compile job startup recovery inspected=%d resumed=%d succeeded=%d failed=%d session_failed=%d skipped=%d",
                summary["inspected"],
                summary["resumed"],
                summary["succeeded"],
                summary["failed"],
                summary["session_failed"],
                summary["skipped"],
            )
        else:
            logger.info("Compile job startup recovery found no orphaned jobs")

        return summary

    def requeue_running_jobs_for_shutdown(
        self,
        *,
        job_ids: Optional[list[str]] = None,
    ) -> Dict[str, int]:
        candidate_ids = list(job_ids or [])
        if not candidate_ids:
            candidate_ids = [
                job.id
                for job in self._compile_job_store.list_incomplete(limit=500)
                if self._job_status_value(job) == "running"
            ]

        summary = {
            "inspected": len(candidate_ids),
            "requeued": 0,
            "session_reset": 0,
            "skipped": 0,
        }

        interrupted_at = datetime.now(timezone.utc).isoformat()

        for job_id in candidate_ids:
            job = self._compile_job_store.get_by_id(job_id)
            if not job or self._job_status_value(job) != "running":
                summary["skipped"] += 1
                continue

            recovery_context = self._recovery_context(job)
            if not recovery_context:
                summary["skipped"] += 1
                continue

            session = (
                self._meeting_session_store.get_by_id(job.session_id)
                if getattr(job, "session_id", None)
                else None
            )
            session_reset = self._reset_session_for_resume(
                session,
                interrupted_at=interrupted_at,
            )

            requeued_job = self._compile_job_store.requeue_for_resume(
                job.id,
                session_id=getattr(session, "id", None),
                metadata={
                    "recovery_reason": "graceful_shutdown_requeue",
                    "shutdown_requeued": True,
                    "shutdown_requeued_at": interrupted_at,
                },
            )
            if not requeued_job:
                summary["skipped"] += 1
                continue

            summary["requeued"] += 1
            if session_reset:
                summary["session_reset"] += 1

        if summary["inspected"] > 0:
            logger.warning(
                "Compile job graceful-shutdown requeue inspected=%d requeued=%d session_reset=%d skipped=%d",
                summary["inspected"],
                summary["requeued"],
                summary["session_reset"],
                summary["skipped"],
            )

        return summary

    async def _recover_job(
        self,
        job: Any,
        *,
        claim_metadata: Optional[Dict[str, Any]] = None,
        reconcile_reason: str = "startup_orphan_reconcile",
        failure_stage: str = "startup_resume",
    ) -> str:
        job_status = self._job_status_value(job)
        if job_status in {"accepted", "running"}:
            session = (
                self._meeting_session_store.get_by_id(job.session_id)
                if getattr(job, "session_id", None)
                else None
            )
            if self._session_closed_successfully(session):
                return self._reconcile_job(job, reason=reconcile_reason)
            if self._session_terminal_failed(session):
                return self._reconcile_job(job, reason=reconcile_reason)
            if session is None:
                return self._reconcile_job(job, reason=reconcile_reason)

            recovery_context = self._recovery_context(job)
            if not recovery_context:
                return self._reconcile_job(job, reason=reconcile_reason)

            if job_status == "running":
                self._reset_session_for_resume(
                    session,
                    interrupted_at=datetime.now(timezone.utc).isoformat(),
                )
                requeued_job = self._compile_job_store.requeue_for_resume(
                    job.id,
                    session_id=getattr(session, "id", None),
                    metadata={
                        "recovery_reason": reconcile_reason,
                        "recovered_from_running": True,
                    },
                )
                if not requeued_job:
                    return "skipped"
                job = requeued_job

            claimed_job = self._compile_job_store.try_claim_for_resume(
                job.id,
                session_id=getattr(session, "id", None),
                metadata=claim_metadata,
            )
            if not claimed_job:
                return "skipped"

            self._schedule_resume(
                claimed_job,
                session=session,
                recovery_context=recovery_context,
                failure_stage=failure_stage,
                claim_metadata=claim_metadata,
            )
            return "resumed"

        return self._reconcile_job(job, reason=reconcile_reason)

    def _schedule_resume(
        self,
        job: Any,
        *,
        session: Any,
        recovery_context: Dict[str, Any],
        failure_stage: str,
        claim_metadata: Optional[Dict[str, Any]],
    ) -> None:
        task = asyncio.create_task(
            self._resume_compile_job(
                job,
                session=session,
                recovery_context=recovery_context,
                failure_stage=failure_stage,
                claim_metadata=claim_metadata,
            )
        )
        compile_job_task_registry.register(job.id, task)

    async def _resume_compile_job(
        self,
        job: Any,
        *,
        session: Any,
        recovery_context: Dict[str, Any],
        failure_stage: str,
        claim_metadata: Optional[Dict[str, Any]],
    ) -> None:
        try:
            from backend.app.services.conversation.ingress_router import IngressRouter
            from backend.app.services.stores.postgres.workspaces_store import (
                PostgresWorkspacesStore,
            )

            workspace_id = recovery_context.get("workspace_id") or job.workspace_id
            workspace = await PostgresWorkspacesStore().get_workspace(workspace_id)
            if not workspace:
                raise RuntimeError(f"Workspace {workspace_id} not found for compile resume")

            handoff_in_payload = recovery_context.get("handoff_in")
            if not isinstance(handoff_in_payload, dict):
                raise RuntimeError("Compile resume metadata missing handoff_in payload")

            route_decision = await IngressRouter().decide(
                execution_mode="meeting",
                meeting_enabled=True,
                entry_point="compile",
            )

            await HandoffBundleService().compile_handoff_in(
                handoff_in=HandoffIn(**handoff_in_payload),
                workspace=workspace,
                runtime_profile=getattr(workspace, "runtime_profile", None),
                profile_id=recovery_context.get("profile_id") or job.profile_id,
                thread_id=recovery_context.get("thread_id") or job.thread_id,
                project_id=recovery_context.get("project_id") or job.project_id,
                model_name=recovery_context.get("model_name"),
                source_device_id=(
                    recovery_context.get("source_device_id") or job.source_device_id
                ),
                route_decision=route_decision,
                compile_job_id=job.id,
                compile_job_store=self._compile_job_store,
                session_override=session,
                session_reused_override=bool(
                    (job.metadata or {}).get("active_session_reused")
                ),
                executor_target_client_id=recovery_context.get(
                    "executor_target_client_id"
                ),
            )
        except Exception as exc:
            logger.error("Startup compile resume failed for %s: %s", job.id, exc)
            HandoffBundleService._mark_compile_session_failed(
                session=session,
                error=exc,
                stage=failure_stage,
            )
            self._compile_job_store.mark_failed(
                job.id,
                str(exc),
                session_id=getattr(session, "id", None),
                metadata=claim_metadata,
            )
        finally:
            compile_job_task_registry.unregister(job.id)

    def _reconcile_job(
        self,
        job: Any,
        *,
        reason: str = "startup_orphan_reconcile",
    ) -> str:
        session = (
            self._meeting_session_store.get_by_id(job.session_id)
            if getattr(job, "session_id", None)
            else None
        )
        session_status = self._session_status_value(session)
        metadata = {
            "recovery_reason": reason,
            "session_status": session_status,
        }
        if reason == "startup_orphan_reconcile":
            metadata["reconciled_from_startup"] = True

        task_summary = summarize_meeting_session_tasks(
            getattr(session, "id", None),
            tasks_store=self._tasks_store,
        )
        metadata["session_task_total"] = task_summary["total"]
        metadata["session_incomplete_tasks"] = task_summary["incomplete"]
        metadata["session_task_statuses"] = task_summary["statuses"]

        if self._session_closed_successfully(session) and task_summary["terminal"]:
            self._compile_job_store.mark_succeeded(
                job.id,
                session_id=getattr(session, "id", None),
                result={
                    "status": "compiled",
                    "session_id": getattr(session, "id", None),
                    "task_ir_id": None,
                    "persisted": False,
                    "action_items_count": len(getattr(session, "action_items", []) or []),
                    "reconciled_from_session": True,
                },
                metadata=metadata,
            )
            return "succeeded"
        if self._session_closed_successfully(session) and not task_summary["terminal"]:
            self._compile_job_store.mark_failed(
                job.id,
                "meeting_session_closed_with_nonterminal_tasks",
                session_id=getattr(session, "id", None),
                metadata=metadata,
            )
            return "failed"

        error = self._build_recovery_error(session=session)

        if self._session_terminal_failed(session):
            self._compile_job_store.mark_failed(
                job.id,
                error,
                session_id=getattr(session, "id", None),
                metadata=metadata,
            )
            return "failed"

        if session is not None:
            HandoffBundleService._mark_compile_session_failed(
                session=session,
                error=RuntimeError(error),
                stage="startup_recovery",
            )

        self._compile_job_store.mark_failed(
            job.id,
            error,
            session_id=getattr(session, "id", None),
            metadata=metadata,
        )
        return "failed_with_session_terminalized" if session is not None else "failed"

    @staticmethod
    def _session_status_value(session: Any) -> Optional[str]:
        if session is None:
            return None
        status = getattr(session, "status", None)
        return status.value if hasattr(status, "value") else status

    @classmethod
    def _job_status_value(cls, job: Any) -> Optional[str]:
        status = getattr(job, "status", None)
        return status.value if hasattr(status, "value") else status

    @classmethod
    def _session_closed_successfully(cls, session: Any) -> bool:
        return cls._session_status_value(session) == "closed"

    @classmethod
    def _session_terminal_failed(cls, session: Any) -> bool:
        return cls._session_status_value(session) in {"failed", "aborted"}

    @staticmethod
    def _build_recovery_error(*, session: Any) -> str:
        session_id = getattr(session, "id", None)
        if session_id:
            return (
                "Compile job was interrupted by backend restart before completion "
                f"(session={session_id})."
            )
        return "Compile job was interrupted by backend restart before completion."

    @staticmethod
    def _recovery_context(job: Any) -> Optional[Dict[str, Any]]:
        metadata = getattr(job, "metadata", None) or {}
        ctx = metadata.get("_internal_recovery_context")
        return dict(ctx) if isinstance(ctx, dict) else None

    def _reset_session_for_resume(
        self,
        session: Any,
        *,
        interrupted_at: str,
    ) -> bool:
        if session is None:
            return False
        if self._session_closed_successfully(session) or self._session_terminal_failed(
            session
        ):
            return False

        session.metadata = dict(getattr(session, "metadata", None) or {})
        session.metadata.pop("pipeline_failure", None)
        session.metadata["pipeline_stage_status"] = "interrupted"
        session.metadata["pipeline_interrupted_at"] = interrupted_at
        session.metadata["pipeline_interrupted_stage"] = session.metadata.get(
            "pipeline_stage"
        )
        session.metadata["shutdown_requeued"] = True
        session.metadata["shutdown_requeued_at"] = interrupted_at
        session.status = MeetingStatus.PLANNED
        session.ended_at = None
        session.round_count = 0
        session.minutes_md = ""
        session.action_items = []
        self._meeting_session_store.update(session)
        return True
