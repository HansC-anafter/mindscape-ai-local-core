"""
Service helpers for replaying remote workflow-step child executions.
"""

import copy
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from backend.app.models.workspace import TaskStatus
from backend.app.services.remote_execution_child_tasks import (
    ensure_remote_workflow_step_child_shell,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def extract_remote_step_resend_payload(task, *, workspace_id: str) -> Dict[str, Any]:
    if not task:
        raise ValueError("Task not found")
    if task.workspace_id != workspace_id:
        raise ValueError("Task does not belong to this workspace")

    ctx = task.execution_context if isinstance(task.execution_context, dict) else {}
    remote_execution = (
        ctx.get("remote_execution") if isinstance(ctx.get("remote_execution"), dict) else {}
    )
    result_ingress_mode = str(
        remote_execution.get("result_ingress_mode")
        or ctx.get("remote_result_mode")
        or ""
    ).strip().lower()
    if result_ingress_mode != "workflow_step_child":
        raise ValueError("Task is not a remote workflow-step child execution")

    request_payload = remote_execution.get("request_payload")
    if not isinstance(request_payload, dict):
        raise ValueError("Missing remote request payload for step resend")

    tool_name = remote_execution.get("tool_name") or request_payload.get("tool_name")
    if not isinstance(tool_name, str) or not tool_name.strip():
        raise ValueError("Missing remote tool_name for step resend")

    return {
        "request_payload": request_payload,
        "tool_name": tool_name.strip(),
        "trace_id": str(
            remote_execution.get("trace_id") or ctx.get("trace_id") or task.execution_id
        ),
        "tenant_id": str(
            remote_execution.get("tenant_id") or ctx.get("tenant_id") or "default"
        ),
        "capability_code": remote_execution.get("capability_code") or ctx.get("capability_code"),
        "workflow_step_id": remote_execution.get("workflow_step_id") or ctx.get("workflow_step_id"),
        "playbook_code": ctx.get("playbook_code") or task.pack_id,
        "parent_execution_id": task.parent_execution_id or ctx.get("parent_execution_id"),
        "project_id": task.project_id or ctx.get("project_id"),
        "target_device_id": remote_execution.get("target_device_id"),
        "lineage_root_execution_id": (
            remote_execution.get("lineage_root_execution_id")
            or task.execution_id
            or task.id
        ),
    }


async def resend_remote_workflow_step_child_task(
    *,
    task,
    workspace_id: str,
    connector,
    target_device_id: Optional[str] = None,
) -> Dict[str, Any]:
    replay = extract_remote_step_resend_payload(task, workspace_id=workspace_id)
    if connector is None:
        raise ValueError("Cloud Connector not available for remote step resend")

    new_execution_id = str(uuid.uuid4())
    trace_id = replay["trace_id"]
    request_payload = copy.deepcopy(replay["request_payload"])
    nested_inputs = request_payload.get("inputs")
    if not isinstance(nested_inputs, dict):
        nested_inputs = {}
        request_payload["inputs"] = nested_inputs
    nested_inputs["execution_id"] = new_execution_id
    nested_inputs.setdefault("trace_id", trace_id)
    nested_inputs.setdefault("workspace_id", workspace_id)
    if replay["parent_execution_id"]:
        nested_inputs.setdefault("parent_execution_id", replay["parent_execution_id"])
    if replay["workflow_step_id"]:
        nested_inputs.setdefault("workflow_step_id", replay["workflow_step_id"])
    nested_inputs["resend_of_execution_id"] = task.execution_id or task.id

    resolved_target_device_id = target_device_id or replay["target_device_id"]
    original_ctx = dict(task.execution_context or {})
    original_remote = dict(original_ctx.get("remote_execution") or {})
    replay_children = list(original_remote.get("replay_children_execution_ids") or [])
    replay_children.append(new_execution_id)
    original_remote["latest_replay_execution_id"] = new_execution_id
    original_remote["replay_children_execution_ids"] = replay_children
    original_remote["replay_requested_at"] = _utc_now_iso()
    original_remote["lineage_root_execution_id"] = replay["lineage_root_execution_id"]
    original_ctx["remote_execution"] = original_remote

    child_tasks_store, child_task = ensure_remote_workflow_step_child_shell(
        child_execution_id=new_execution_id,
        parent_execution_id=replay["parent_execution_id"],
        workspace_id=workspace_id,
        project_id=replay["project_id"],
        tenant_id=replay["tenant_id"],
        trace_id=trace_id,
        step_id=replay["workflow_step_id"] or replay["tool_name"],
        tool_name=replay["tool_name"],
        capability_code=replay["capability_code"],
        parent_playbook_code=replay["playbook_code"],
        request_payload=request_payload,
        target_device_id=resolved_target_device_id,
        callback_payload={"mode": "local_core_terminal_event"},
        replay_of_execution_id=task.execution_id or task.id,
        lineage_root_execution_id=replay["lineage_root_execution_id"],
    )
    child_tasks_store.update_task(task.id, execution_context=original_ctx)

    try:
        cloud_result = await connector.start_remote_execution(
            tenant_id=replay["tenant_id"],
            playbook_code=replay["playbook_code"] or replay["tool_name"],
            request_payload=request_payload,
            workspace_id=workspace_id,
            capability_code=replay["capability_code"],
            execution_id=new_execution_id,
            trace_id=trace_id,
            job_type="tool",
            callback_payload={"mode": "local_core_terminal_event"},
            target_device_id=resolved_target_device_id,
        )
    except Exception as exc:
        failure_ctx = dict(child_task.execution_context or {})
        failure_remote = dict(failure_ctx.get("remote_execution") or {})
        failure_remote["cloud_dispatch_state"] = "dispatch_failed"
        failure_remote["error"] = str(exc)
        failure_ctx["remote_execution"] = failure_remote
        child_tasks_store.update_task(child_task.id, execution_context=failure_ctx)
        child_tasks_store.update_task_status(
            child_task.id,
            TaskStatus.FAILED,
            result={
                "remote_terminal_status": "dispatch_failed",
                "provider_metadata": {},
                "result_payload": None,
            },
            error=str(exc),
        )
        raise

    updated_ctx = dict(child_task.execution_context or {})
    updated_remote = dict(updated_ctx.get("remote_execution") or {})
    updated_remote["cloud_dispatch_state"] = cloud_result.get("state", "pending")
    updated_remote["cloud_execution_id"] = cloud_result.get("id") or new_execution_id
    updated_ctx["remote_execution"] = updated_remote
    child_tasks_store.update_task(child_task.id, execution_context=updated_ctx)

    return {
        "success": True,
        "status": "resent",
        "original_execution_id": task.execution_id or task.id,
        "execution_id": new_execution_id,
        "trace_id": trace_id,
        "workspace_id": workspace_id,
        "workflow_step_id": replay["workflow_step_id"],
        "tool_name": replay["tool_name"],
        "target_device_id": resolved_target_device_id,
        "cloud_execution_id": cloud_result.get("id") or new_execution_id,
        "lineage_root_execution_id": replay["lineage_root_execution_id"],
    }
