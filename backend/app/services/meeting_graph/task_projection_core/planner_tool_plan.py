"""Planner tool plan task graph projection builder."""

from __future__ import annotations

from typing import Any, Dict, List

from backend.app.models.meeting_graph import (
    MeetingExecutionGraphEdge,
    MeetingExecutionGraphNode,
)
from backend.app.models.workspace import Task, TaskStatus
from backend.app.services.meeting_graph.projection_utils import (
    _as_dict,
    _as_list,
    _edge,
    _json_output,
    _read_string,
    _safe_id,
    _short_id,
)
from backend.app.services.meeting_graph.task_projection_core.common import (
    planner_result_status,
    status_for_task,
    task_result,
    task_time,
)


def build_planner_tool_plan_nodes(
    task: Task,
    plan: Dict[str, Any],
) -> tuple[List[MeetingExecutionGraphNode], List[MeetingExecutionGraphEdge]]:
    result_payload = task_result(task)
    tool_result = _as_dict(result_payload.get("result"))
    plan_steps_result = [
        item for item in _as_list(tool_result.get("plan_steps")) if isinstance(item, dict)
    ]
    result_by_step_id = {
        _read_string(item.get("step_id")): item
        for item in plan_steps_result
        if _read_string(item.get("step_id"))
    }
    plan_id = _read_string(plan.get("plan_id"), task.id)
    run_node_id = f"runner-task-{_safe_id(task.id)}"
    plan_node_id = f"planner-tool-plan-{_safe_id(plan_id)}"
    result_node_id = f"planner-tool-plan-result-{_safe_id(task.id)}"
    task_status = status_for_task(task)
    result_status = planner_result_status(task)
    categories = [item for item in _as_list(plan.get("categories")) if isinstance(item, dict)]
    steps = [item for item in _as_list(plan.get("steps")) if isinstance(item, dict)]

    nodes: List[MeetingExecutionGraphNode] = [
        MeetingExecutionGraphNode(
            id=plan_node_id,
            eyebrow="Planner tool plan",
            title=_read_string(plan.get("pack_id"), "meeting planner"),
            detail=f"{len(categories)} categories · {len(steps)} tool steps",
            status="ready",
            kind="planner_tool_plan",
            lane="commands",
            output=_json_output(plan),
            defaultInspector="graph",
            metadata={
                "task_id": task.id,
                "plan": plan,
            },
        ),
        MeetingExecutionGraphNode(
            id=run_node_id,
            eyebrow="Runner task",
            title=_read_string(task.pack_id, "meeting.execute_planner_tool_plan"),
            detail=f"{task.status.value if hasattr(task.status, 'value') else task.status} · task {_short_id(task.id)}",
            status=task_status,
            kind="runner_task",
            lane="runs",
            output=f"Execution ID: {task.execution_id or task.id}",
            defaultInspector="runtime",
            metadata={
                "task_id": task.id,
                "execution_id": task.execution_id,
                "phase_id": _as_dict(task.execution_context).get("phase_id"),
                "completed_at": task_time(task),
                "plan_id": plan_id,
            },
        ),
        MeetingExecutionGraphNode(
            id=result_node_id,
            eyebrow="Planner result",
            title=_read_string(tool_result.get("status"), "Tool plan pending"),
            detail=(
                f"{len(plan_steps_result)} executed steps"
                if plan_steps_result
                else "Waiting for Task.result from the existing runner path."
            ),
            status=result_status,
            kind="tool_result",
            lane="outputs",
            output=_json_output(tool_result or {"status": result_status}),
            childCount=len(plan_steps_result) if plan_steps_result else None,
            defaultInspector="trace",
            degraded=task.status == TaskStatus.FAILED,
            metadata={
                "task_id": task.id,
                "plan_id": plan_id,
                "result": tool_result,
            },
        ),
    ]
    edges: List[MeetingExecutionGraphEdge] = [
        _edge(plan_node_id, run_node_id, "dispatches"),
        _edge(run_node_id, result_node_id, "produces"),
    ]

    for category in categories:
        category_id = _read_string(category.get("category_id"))
        if not category_id:
            continue
        category_node_id = f"planner-category-{_safe_id(category_id)}"
        nodes.append(
            MeetingExecutionGraphNode(
                id=category_node_id,
                eyebrow="Category",
                title=_read_string(category.get("label"), category_id),
                detail=_read_string(category.get("description")),
                status="ready",
                kind="planner_category",
                lane="context",
                output=_json_output(category),
                defaultInspector="object",
                metadata={
                    "task_id": task.id,
                    "plan_id": plan_id,
                    "category": category,
                },
            )
        )
        edges.append(_edge(plan_node_id, category_node_id, "groups"))

    for step in steps:
        step_id = _read_string(step.get("step_id"))
        if not step_id:
            continue
        step_result = _as_dict(result_by_step_id.get(step_id))
        step_status = _read_string(step_result.get("status"))
        category_id = _read_string(step.get("category_id"))
        category_node_id = f"planner-category-{_safe_id(category_id)}"
        step_node_id = f"planner-tool-step-{_safe_id(step_id)}"
        output_payload = step_result or {
            "tool_name": step.get("tool_name"),
            "arguments": step.get("arguments"),
            "input_bindings": step.get("input_bindings"),
        }
        nodes.append(
            MeetingExecutionGraphNode(
                id=step_node_id,
                eyebrow=_read_string(step.get("role"), "Tool step"),
                title=_read_string(step.get("tool_name"), "planner tool"),
                detail=f"{_read_string(step.get('effect'), 'action')} · {_read_string(step.get('resource_kind'), 'resource')}",
                status=(
                    "error"
                    if step_status == "failed"
                    else "ready"
                    if step_status == "success"
                    else task_status
                ),
                kind="tool_call",
                lane="commands",
                output=_json_output(output_payload),
                defaultInspector="runtime",
                degraded=step_status == "failed",
                metadata={
                    "task_id": task.id,
                    "plan_id": plan_id,
                    "step": step,
                    "step_result": step_result,
                },
            )
        )
        if category_id:
            edges.append(_edge(category_node_id, step_node_id, "uses"))
        else:
            edges.append(_edge(plan_node_id, step_node_id, "uses"))
        edges.append(_edge(step_node_id, run_node_id, "executes"))
        edges.append(_edge(step_node_id, result_node_id, "contributes"))

    return nodes, edges
