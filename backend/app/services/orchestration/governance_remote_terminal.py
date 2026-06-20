"""Remote terminal event helper for ``GovernanceEngine``."""

from datetime import datetime, timezone
from typing import Any, Dict, Optional


def process_remote_terminal_event(
    engine: Any,
    *,
    tenant_id: str,
    workspace_id: str,
    execution_id: str,
    trace_id: str,
    status: str,
    result_payload: Optional[Dict[str, Any]],
    error_message: Optional[str],
    job_type: Optional[str] = None,
    capability_code: Optional[str] = None,
    playbook_code: Optional[str] = None,
    provider_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Handle remote terminal events through the existing governance facade."""
    from backend.app.models.workspace import TaskStatus

    normalized_status = (status or "").strip().lower()
    success_statuses = {"succeeded", "completed"}
    failure_statuses = {"failed", "cancelled", "timeout"}
    if normalized_status not in success_statuses | failure_statuses:
        return {
            "success": False,
            "execution_id": execution_id,
            "error": f"unsupported remote terminal status: {status}",
        }

    task = engine.tasks_store.get_task_by_execution_id(execution_id)
    if not task:
        return {
            "success": False,
            "execution_id": execution_id,
            "error": "execution shell not found",
            "error_code": "EXECUTION_SHELL_NOT_FOUND",
        }

    terminal_statuses = {
        TaskStatus.SUCCEEDED.value,
        TaskStatus.FAILED.value,
        TaskStatus.CANCELLED_BY_USER.value,
        TaskStatus.EXPIRED.value,
    }
    current_status = getattr(getattr(task, "status", None), "value", None) or str(
        getattr(task, "status", "")
    )
    if current_status in terminal_statuses:
        return {
            "success": True,
            "execution_id": execution_id,
            "idempotent": True,
            "task_status": current_status,
        }

    ctx = dict(getattr(task, "execution_context", None) or {})
    remote_execution = dict(ctx.get("remote_execution") or {})
    remote_execution.update(
        {
            "tenant_id": tenant_id,
            "trace_id": trace_id,
            "remote_dispatch_state": normalized_status,
            "provider_metadata": provider_metadata or {},
        }
    )
    if job_type:
        remote_execution["job_type"] = job_type
    if capability_code:
        remote_execution["capability_code"] = capability_code
    if isinstance(provider_metadata, dict):
        if provider_metadata.get("callback_delivered_at"):
            remote_execution["callback_delivered_at"] = provider_metadata.get(
                "callback_delivered_at"
            )
        if provider_metadata.get("callback_error"):
            remote_execution["callback_error"] = provider_metadata.get(
                "callback_error"
            )
        remote_execution_id = provider_metadata.get("remote_execution_id") or provider_metadata.get(
            "cloud_execution_id"
        )
        if remote_execution_id:
            remote_execution["remote_execution_id"] = remote_execution_id
        remote_state = provider_metadata.get("remote_state") or provider_metadata.get(
            "cloud_state"
        )
        if remote_state:
            remote_execution["remote_state"] = remote_state
    if error_message:
        remote_execution["error"] = error_message
    ctx.update(
        {
            "tenant_id": tenant_id,
            "trace_id": trace_id,
            "remote_execution": remote_execution,
        }
    )
    if job_type and not ctx.get("job_type"):
        ctx["job_type"] = job_type
    if capability_code and not ctx.get("capability_code"):
        ctx["capability_code"] = capability_code
    engine.tasks_store.update_task(task.id, execution_context=ctx)

    result_ingress_mode = str(
        remote_execution.get("result_ingress_mode")
        or ctx.get("remote_result_mode")
        or ""
    ).strip().lower()
    is_workflow_step_child = result_ingress_mode == "workflow_step_child"

    if is_workflow_step_child:
        if normalized_status in success_statuses:
            task_status = TaskStatus.SUCCEEDED
        elif normalized_status == "cancelled":
            task_status = TaskStatus.CANCELLED_BY_USER
        else:
            task_status = TaskStatus.FAILED

        child_result = {
            "remote_terminal_status": normalized_status,
            "provider_metadata": provider_metadata or {},
            "result_payload": result_payload,
        }
        engine.tasks_store.update_task_status(
            task.id,
            task_status,
            result=child_result,
            error=(
                None
                if task_status == TaskStatus.SUCCEEDED
                else error_message or f"remote execution {normalized_status}"
            ),
            completed_at=datetime.now(timezone.utc),
        )
        return {
            "success": True,
            "execution_id": execution_id,
            "task_id": task.id,
            "task_status": task_status.value,
            "remote_terminal_status": normalized_status,
            "artifact_id": None,
            "result_payload": result_payload,
            "result_ingress_mode": result_ingress_mode,
        }

    if normalized_status in success_statuses:
        completion_result = engine.process_completion(
            workspace_id=workspace_id,
            execution_id=execution_id,
            result_data=result_payload or {},
            project_id=getattr(task, "project_id", None) or ctx.get("project_id"),
            task_id=task.id,
            playbook_code=playbook_code or ctx.get("playbook_code"),
        ) or {"success": False}
        completion_result["remote_terminal_status"] = normalized_status
        return completion_result

    if normalized_status == "cancelled":
        task_status = TaskStatus.CANCELLED_BY_USER
    else:
        task_status = TaskStatus.FAILED

    engine.tasks_store.update_task_status(
        task.id,
        task_status,
        result={
            "remote_terminal_status": normalized_status,
            "provider_metadata": provider_metadata or {},
        },
        error=error_message or f"remote execution {normalized_status}",
    )
    return {
        "success": True,
        "execution_id": execution_id,
        "task_id": task.id,
        "task_status": task_status.value,
        "remote_terminal_status": normalized_status,
        "artifact_id": None,
    }
