"""
Helpers for local child task shells that track remote workflow step executions.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from backend.app.models.workspace import Task, TaskStatus
from backend.app.services.stores.tasks_store import TasksStore


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_remote_workflow_step_child_shell(
    *,
    child_execution_id: str,
    parent_execution_id: Optional[str],
    workspace_id: str,
    project_id: Optional[str],
    tenant_id: str,
    trace_id: str,
    step_id: str,
    tool_name: str,
    capability_code: Optional[str],
    parent_playbook_code: Optional[str],
    request_payload: Dict[str, Any],
    target_device_id: Optional[str],
    callback_payload: Optional[Dict[str, Any]] = None,
    replay_of_execution_id: Optional[str] = None,
    lineage_root_execution_id: Optional[str] = None,
):
    """Create or return a local child task shell for a remote workflow step."""
    tasks_store = TasksStore()
    existing = tasks_store.get_task_by_execution_id(child_execution_id)
    if existing:
        return tasks_store, existing

    remote_execution = {
        "tenant_id": tenant_id,
        "trace_id": trace_id,
        "cloud_dispatch_state": "queued",
        "cloud_execution_id": child_execution_id,
        "job_type": "tool",
        "capability_code": capability_code,
        "tool_name": tool_name,
        "workflow_step_id": step_id,
        "result_ingress_mode": "workflow_step_child",
        "request_payload": request_payload,
        "target_device_id": target_device_id,
        "callback_payload": callback_payload or {},
        "lineage_root_execution_id": lineage_root_execution_id or child_execution_id,
    }
    if replay_of_execution_id:
        remote_execution["replay_of_execution_id"] = replay_of_execution_id

    execution_context = {
        "playbook_code": parent_playbook_code,
        "execution_id": child_execution_id,
        "parent_execution_id": parent_execution_id,
        "status": "running",
        "workspace_id": workspace_id,
        "project_id": project_id,
        "workflow_step_id": step_id,
        "tool_name": tool_name,
        "remote_result_mode": "workflow_step_child",
        "remote_execution": remote_execution,
        "runner_skip_reason": "remote_workflow_step_child_shell",
    }
    task = Task(
        id=child_execution_id,
        workspace_id=workspace_id,
        message_id=str(uuid.uuid4()),
        execution_id=child_execution_id,
        parent_execution_id=parent_execution_id,
        project_id=project_id,
        pack_id=parent_playbook_code or tool_name,
        task_type="tool_execution",
        status=TaskStatus.RUNNING,
        execution_context=execution_context,
        created_at=_utc_now(),
        started_at=_utc_now(),
    )
    tasks_store.create_task(task)
    return tasks_store, task
