"""Shared task payload helpers for meeting graph task projections."""

from __future__ import annotations

from typing import Any, Dict

from backend.app.models.workspace import Task, TaskStatus
from backend.app.services.meeting_graph.projection_utils import (
    _as_dict,
    _as_list,
    _read_string,
)


def task_time(task: Task) -> str:
    dt = task.completed_at or task.started_at or task.created_at
    if not dt:
        return ""
    try:
        return dt.isoformat()
    except Exception:
        return str(dt)


def status_for_task(task: Task) -> str:
    if task.status == TaskStatus.RUNNING:
        return "running"
    if task.status == TaskStatus.PENDING:
        return "pending"
    if task.status == TaskStatus.FAILED:
        return "error"
    if task.status in {TaskStatus.CANCELLED_BY_USER, TaskStatus.EXPIRED}:
        return "blocked"
    return "ready"


def plan_payload_from_inputs(inputs: Dict[str, Any]) -> Dict[str, Any]:
    raw_plan = _as_dict(inputs.get("object_action_plan"))
    return _as_dict(raw_plan.get("request_plan")) or raw_plan


def role_entries_from_inputs(inputs: Dict[str, Any]) -> list[Dict[str, Any]]:
    entries = _as_list(inputs.get("object_action_entries"))
    if entries:
        return [entry for entry in entries if isinstance(entry, dict)]
    plan = _as_dict(inputs.get("object_action_plan"))
    return [entry for entry in _as_list(plan.get("role_assignments")) if isinstance(entry, dict)]


def task_inputs(task: Task) -> Dict[str, Any]:
    ctx = _as_dict(task.execution_context)
    inputs = _as_dict(ctx.get("inputs"))
    if inputs:
        return inputs
    return _as_dict(task.params)


def task_command_id(inputs: Dict[str, Any], plan_payload: Dict[str, Any]) -> str:
    request_context = _as_dict(inputs.get("request_context"))
    return _read_string(
        inputs.get("command_id")
        or request_context.get("command_id")
        or inputs.get("meeting_command_id")
        or _as_dict(inputs.get("command")).get("command_id")
        or plan_payload.get("command_id")
        or _as_dict(plan_payload.get("request_context")).get("command_id")
        or _as_dict(inputs.get("object_action_plan")).get("command_id")
    )


def task_closure(task: Task) -> Dict[str, Any]:
    return _as_dict(_as_dict(task.execution_context).get("object_action_closure"))


def planner_binding_from_task(task: Task) -> Dict[str, Any]:
    ctx = _as_dict(task.execution_context)
    binding = _as_dict(ctx.get("planner_contract_binding"))
    if binding:
        return binding
    return _as_dict(_as_dict(task.params).get("planner_contract_binding"))


def planner_tool_plan_from_task(task: Task) -> Dict[str, Any]:
    inputs = task_inputs(task)
    plan = _as_dict(inputs.get("planner_tool_plan"))
    if plan:
        return plan
    params = _as_dict(task.params)
    input_params = _as_dict(params.get("input_params"))
    return _as_dict(input_params.get("planner_tool_plan"))


def task_result(task: Task) -> Dict[str, Any]:
    return _as_dict(task.result)


def planner_result_status(task: Task) -> str:
    if task.status in {TaskStatus.PENDING, TaskStatus.RUNNING}:
        return "pending"
    if task.status == TaskStatus.FAILED:
        return "error"
    return "ready"


def planner_resource_kind(binding: Dict[str, Any]) -> str:
    return _read_string(binding.get("resource_kind"), "resource")


def planner_effect(binding: Dict[str, Any]) -> str:
    return _read_string(binding.get("effect"), "action").lower()


def planner_tool_name(task: Task, binding: Dict[str, Any]) -> str:
    return _read_string(
        binding.get("tool_name")
        or _as_dict(task.execution_context).get("tool_name")
        or _as_dict(task.params).get("tool_name"),
        "planner tool",
    )
