"""Task timeout helpers for TaskManager."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Dict, List

from backend.app.models.workspace import TaskStatus
from backend.app.services.conversation.task_manager_core.timeline_items import (
    create_timeout_timeline_item,
)
from backend.app.services.execution_core.clock import utc_now

logger = logging.getLogger(__name__)

TASK_TIMEOUT_MINUTES = 5


def collect_timeout_diagnostics(
    *,
    task: Any,
    execution_id: str,
    start_time: Any,
    timeout_minutes: int,
) -> Dict[str, Any]:
    """Collect diagnostic details for a timed-out task."""
    diagnostic_info = {
        "pack_id": task.pack_id,
        "execution_id": execution_id,
        "started_at": start_time.isoformat(),
        "timeout_after_minutes": timeout_minutes,
        "current_time": utc_now().isoformat(),
    }

    try:
        from backend.app.models.mindscape import EventType
        from backend.app.services.mindscape_store import MindscapeStore

        store = MindscapeStore()
        events = store.get_events_by_workspace(
            workspace_id=task.workspace_id,
            limit=100,
        )
        step_events = [
            event
            for event in events
            if event.event_type == EventType.PLAYBOOK_STEP
            and execution_id in (event.entity_ids or [])
        ]

        if step_events:
            diagnostic_info["steps_found"] = len(step_events)
            last_step = max(step_events, key=lambda event: event.timestamp)
            last_step_payload = (
                last_step.payload if isinstance(last_step.payload, dict) else {}
            )
            diagnostic_info["last_step"] = {
                "step_name": last_step_payload.get("step_name", "unknown"),
                "status": last_step_payload.get("status", "unknown"),
                "timestamp": (
                    last_step.timestamp.isoformat()
                    if hasattr(last_step.timestamp, "isoformat")
                    else str(last_step.timestamp)
                ),
            }
        else:
            diagnostic_info["steps_found"] = 0
            diagnostic_info["diagnosis"] = (
                "No execution steps found - playbook may not have started or is stuck at initialization"
            )
    except Exception as exc:
        logger.warning(
            "Failed to gather diagnostic info for timed out task %s: %s",
            task.id,
            exc,
        )
        diagnostic_info["diagnosis_error"] = str(exc)

    return diagnostic_info


def check_and_timeout_tasks(
    *,
    manager: Any,
    timeout_minutes: int = TASK_TIMEOUT_MINUTES,
) -> List[str]:
    """Check running tasks and fail those that exceeded the timeout window."""
    timed_out_task_ids = []
    try:
        running_tasks = manager.tasks_store.list_tasks_by_workspace(
            workspace_id=None,
            status=TaskStatus.RUNNING,
            limit=1000,
        )

        if not running_tasks:
            return timed_out_task_ids

        timeout_threshold = utc_now() - timedelta(minutes=timeout_minutes)

        for task in running_tasks:
            start_time = task.started_at or task.created_at
            if start_time and start_time < timeout_threshold:
                try:
                    execution_context = task.execution_context or {}
                    execution_id = task.execution_id or task.id
                    diagnostic_info = collect_timeout_diagnostics(
                        task=task,
                        execution_id=execution_id,
                        start_time=start_time,
                        timeout_minutes=timeout_minutes,
                    )
                    timeout_error = (
                        f"Task timed out after {timeout_minutes} minutes. "
                        f"Started at {start_time.isoformat()}. "
                        f"Diagnosis: {diagnostic_info.get('diagnosis', 'Unknown - check execution steps')}"
                    )

                    logger.warning(
                        "Task %s (pack: %s, execution: %s) timed out. Diagnostic info: %s",
                        task.id,
                        task.pack_id,
                        execution_id,
                        diagnostic_info,
                    )

                    execution_context["failure_type"] = "timeout"
                    execution_context["failure_reason"] = timeout_error
                    execution_context["timeout_diagnostic"] = diagnostic_info

                    manager.tasks_store.update_task_status(
                        task_id=task.id,
                        status=TaskStatus.FAILED,
                        error=timeout_error,
                        completed_at=utc_now(),
                    )

                    manager.tasks_store.update_task(
                        task.id,
                        execution_context=execution_context,
                    )

                    error_timeline_item = create_timeout_timeline_item(
                        task=task,
                        timeout_error=timeout_error,
                        timeout_minutes=timeout_minutes,
                        i18n=manager.i18n,
                        utc_now_fn=utc_now,
                    )
                    manager.timeline_items_store.create_timeline_item(
                        error_timeline_item
                    )

                    timed_out_task_ids.append(task.id)
                    logger.info("Task %s marked as timed out and failed", task.id)
                except Exception as exc:
                    logger.error(
                        "Failed to mark task %s as timed out: %s",
                        task.id,
                        exc,
                        exc_info=True,
                    )
    except Exception as exc:
        logger.error("Failed to check for timed out tasks: %s", exc, exc_info=True)

    return timed_out_task_ids
