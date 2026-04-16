import asyncio

from app.services.compile_job_dispatch_manager import (
    get_compile_job_dispatch_manager,
)
from app.services.compile_job_reconciler import (
    CompileJobReconciler,
    closed_session_compile_failed,
    summarize_meeting_session_tasks,
)
from app.services.compile_job_task_registry import compile_job_task_registry


def test_compile_job_reconciler_compat_surface() -> None:
    reconciler = CompileJobReconciler()

    startup_summary = asyncio.run(reconciler.recover_startup_orphans(limit=25))
    shutdown_summary = reconciler.requeue_running_jobs_for_shutdown(
        job_ids=["job_a", "job_b"],
    )

    assert startup_summary == {
        "inspected": 0,
        "resumed": 0,
        "succeeded": 0,
        "failed": 0,
        "session_failed": 0,
        "skipped": 0,
        "limit": 25,
    }
    assert shutdown_summary == {
        "inspected": 2,
        "requeued": 0,
        "session_reset": 0,
        "skipped": 2,
    }


def test_compile_job_compat_helpers() -> None:
    get_compile_job_dispatch_manager().start_background_services()
    get_compile_job_dispatch_manager().stop_background_services()

    assert summarize_meeting_session_tasks("meeting_123") == {
        "meeting_session_id": "meeting_123",
        "total": 0,
        "incomplete": 0,
        "terminal": False,
        "statuses": {},
    }
    assert closed_session_compile_failed(
        {"total": 2, "statuses": {"failed": 2, "succeeded": 0}},
        dispatch_status=None,
    )
    assert closed_session_compile_failed(
        {"total": 0, "statuses": {}},
        dispatch_status="failed",
    )
    assert compile_job_task_registry.snapshot() == []
