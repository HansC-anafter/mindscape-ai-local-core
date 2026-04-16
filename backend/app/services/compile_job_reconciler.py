"""Compatibility helpers for legacy compile-job lifecycle hooks."""

from __future__ import annotations

from typing import Any


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
    """No-op reconciler used while compile-job source remains unavailable."""

    def __init__(self, **_: Any) -> None:
        pass

    async def recover_startup_orphans(self, limit: int = 500) -> dict[str, int]:
        return {
            "inspected": 0,
            "resumed": 0,
            "succeeded": 0,
            "failed": 0,
            "session_failed": 0,
            "skipped": 0,
            "limit": limit,
        }

    def requeue_running_jobs_for_shutdown(
        self,
        *,
        job_ids: list[str] | None = None,
    ) -> dict[str, int]:
        return {
            "inspected": len(job_ids or []),
            "requeued": 0,
            "session_reset": 0,
            "skipped": len(job_ids or []),
        }
