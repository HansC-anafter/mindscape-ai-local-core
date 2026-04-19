"""Compile-job lifecycle helpers and startup recovery."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from backend.app.services.compile_job_task_registry import compile_job_task_registry

logger = logging.getLogger(__name__)


def summarize_meeting_session_tasks(meeting_session_id: str) -> dict[str, Any]:
    return {
        "meeting_session_id": meeting_session_id,
        "total": 0,
        "incomplete": 0,
        "terminal": False,
        "statuses": {},
    }


def closed_session_compile_failed(
    task_summary: dict[str, Any],
    *,
    dispatch_status: str | None = None,
) -> bool:
    if dispatch_status == "failed":
        return True
    statuses = task_summary.get("statuses") or {}
    total = int(task_summary.get("total") or 0)
    if not total or not statuses:
        return False
    failed = int(statuses.get("failed") or 0)
    succeeded = int(statuses.get("succeeded") or 0)
    return failed > 0 and succeeded == 0 and failed >= total


class CompileJobReconciler:
    """Recover interrupted compile jobs by replaying their saved request."""

    def __init__(
        self,
        *,
        compile_job_store: Any | None = None,
        meeting_session_store: Any | None = None,
        **_: Any,
    ) -> None:
        self.compile_job_store = compile_job_store
        self.meeting_session_store = meeting_session_store

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _extract_recovery_request(job: Any) -> dict[str, Any] | None:
        metadata = getattr(job, "metadata", None) or {}
        request = metadata.get("recovery_request")
        return request if isinstance(request, dict) else None

    def _mark_failed(
        self,
        job: Any,
        *,
        error: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if self.compile_job_store is None:
            return
        try:
            self.compile_job_store.mark_failed(
                job.id,
                error,
                session_id=getattr(job, "session_id", None),
                metadata=metadata,
            )
        except Exception:
            logger.warning(
                "Compile job reconcile failed to mark job %s failed",
                getattr(job, "id", None),
                exc_info=True,
            )

    async def _resume_as_new_compile(
        self,
        original_job_id: str,
        request: dict[str, Any],
    ) -> None:
        try:
            from backend.app.models.handoff import HandoffIn
            from backend.app.services.conversation.ingress_router import IngressRouter
            from backend.app.services.handoff_bundle_service import HandoffBundleService
            from backend.app.services.stores.postgres.workspaces_store import (
                PostgresWorkspacesStore,
            )

            handoff_payload = request.get("handoff_payload") or {}
            handoff_in = HandoffIn(**handoff_payload)
            workspace_id = request.get("workspace_id") or handoff_in.workspace_id
            workspace = await PostgresWorkspacesStore().get_workspace(workspace_id)
            if workspace is None:
                raise ValueError(f"Workspace {workspace_id} not found during recovery")

            route_decision = await IngressRouter().decide(
                execution_mode="meeting",
                meeting_enabled=True,
                executor_runtime=getattr(workspace, "resolved_executor_runtime", None),
                entry_point="compile",
            )

            result = await HandoffBundleService.compile_handoff_in(
                handoff_in=handoff_in,
                workspace=workspace,
                runtime_profile=getattr(workspace, "runtime_profile", None),
                profile_id=request.get("profile_id") or "default-user",
                thread_id=request.get("thread_id") or "",
                project_id=request.get("project_id") or "",
                model_name=request.get("model_name"),
                source_device_id=request.get("source_device_id"),
                route_decision=route_decision,
            )
            logger.info(
                "Compile job recovery replay launched original=%s replacement_job=%s replacement_session=%s",
                original_job_id,
                result.get("compile_job_id") or result.get("job_id"),
                result.get("session_id"),
            )
        except Exception:
            logger.warning(
                "Compile job recovery replay failed for original=%s",
                original_job_id,
                exc_info=True,
            )
        finally:
            compile_job_task_registry.unregister(original_job_id)

    async def recover_startup_orphans(self, limit: int = 500) -> dict[str, int]:
        summary = {
            "inspected": 0,
            "resumed": 0,
            "succeeded": 0,
            "failed": 0,
            "session_failed": 0,
            "skipped": 0,
            "limit": limit,
        }
        if self.compile_job_store is None:
            return summary

        try:
            jobs = self.compile_job_store.list_incomplete(limit=limit)
        except Exception:
            logger.warning(
                "Compile job startup recovery failed to list incomplete jobs",
                exc_info=True,
            )
            return summary

        for job in jobs:
            summary["inspected"] += 1
            request = self._extract_recovery_request(job)
            if not request:
                self._mark_failed(
                    job,
                    error="compile_job_recovery_missing_request_payload",
                    metadata={
                        "recovery_reason": "startup_orphan_missing_request",
                        "recovery_attempted_at": self._now_iso(),
                    },
                )
                summary["failed"] += 1
                continue

            self._mark_failed(
                job,
                error="compile_job_interrupted_by_restart_requeued",
                metadata={
                    "recovery_reason": "startup_orphan_requeued",
                    "recovery_attempted_at": self._now_iso(),
                },
            )
            task = asyncio.create_task(
                self._resume_as_new_compile(job.id, request),
                name=f"compile-job-recovery:{job.id}",
            )
            compile_job_task_registry.register(job.id, task)
            summary["resumed"] += 1

        return summary

    def requeue_running_jobs_for_shutdown(
        self,
        *,
        job_ids: list[str] | None = None,
    ) -> dict[str, int]:
        return {
            "inspected": len(job_ids or []),
            "requeued": len(job_ids or []),
            "session_reset": 0,
            "skipped": 0,
        }
