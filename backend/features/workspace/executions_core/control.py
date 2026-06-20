"""Execution control helpers for workspace execution routes."""

from datetime import datetime

from fastapi import HTTPException

from backend.app.models.mindscape import EventType
from backend.app.models.workspace import TaskStatus
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.stores.tasks_store import TasksStore


def confirm_step_payload(
    *,
    execution_id: str,
    step_id: str,
) -> dict:
    """Confirm a step and resume execution context progress."""
    store = MindscapeStore()
    tasks_store = TasksStore(db_path=store.db_path)

    task = tasks_store.get_task_by_execution_id(execution_id)
    if not task:
        raise HTTPException(status_code=404, detail="Execution not found")

    event = store.get_event(step_id)
    if not event or event.event_type != EventType.PLAYBOOK_STEP:
        raise HTTPException(status_code=404, detail="Step not found")

    updated_payload = event.payload.copy() if event.payload else {}
    updated_payload["confirmation_status"] = "confirmed"
    updated_metadata = event.metadata.copy() if event.metadata else {}
    updated_metadata["confirmed_at"] = datetime.utcnow().isoformat()

    store.update_event(step_id, payload=updated_payload, metadata=updated_metadata)

    if task.execution_context:
        task.execution_context["paused_at"] = None
        task.execution_context["current_step_index"] = (
            event.payload.get("step_index", 0) + 1
        )
        tasks_store.update_task(task.id, execution_context=task.execution_context)

    return {
        "status": "confirmed",
        "step_id": step_id,
        "execution_id": execution_id,
        "message": "Step confirmed, execution will continue",
    }


def reject_step_payload(
    *,
    execution_id: str,
    step_id: str,
) -> dict:
    """Reject a step without resuming execution."""
    store = MindscapeStore()

    event = store.get_event(step_id)
    if not event or event.event_type != EventType.PLAYBOOK_STEP:
        raise HTTPException(status_code=404, detail="Step not found")

    updated_payload = event.payload.copy() if event.payload else {}
    updated_payload["confirmation_status"] = "rejected"
    updated_metadata = event.metadata.copy() if event.metadata else {}
    updated_metadata["rejected_at"] = datetime.utcnow().isoformat()

    store.update_event(step_id, payload=updated_payload, metadata=updated_metadata)

    return {
        "status": "rejected",
        "step_id": step_id,
        "execution_id": execution_id,
        "message": "Step rejected. You can retry or cancel execution.",
    }


def cancel_execution_payload(*, execution_id: str) -> dict:
    """Cancel an execution task by user request."""
    store = MindscapeStore()
    tasks_store = TasksStore(db_path=store.db_path)

    task = tasks_store.get_task_by_execution_id(execution_id)
    if not task:
        raise HTTPException(status_code=404, detail="Execution not found")

    tasks_store.update_task_status(
        task_id=task.id,
        status=TaskStatus.CANCELLED_BY_USER,
        error="Cancelled by user",
    )

    if task.execution_context:
        task.execution_context["failure_type"] = "cancelled_by_user"
        task.execution_context["failure_reason"] = "Execution cancelled by user"
        tasks_store.update_task(task.id, execution_context=task.execution_context)

    tasks_store.get_task_by_execution_id(execution_id)

    return {
        "status": "cancelled",
        "execution_id": execution_id,
        "message": "Execution cancelled successfully",
    }
