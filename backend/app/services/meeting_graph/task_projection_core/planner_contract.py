"""Planner contract task graph projection builder."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from backend.app.models.meeting_graph import (
    MeetingExecutionGraphEdge,
    MeetingExecutionGraphNode,
)
from backend.app.models.workspace import Task, TaskStatus
from backend.app.services.meeting_graph.projection_utils import (
    _as_dict,
    _edge,
    _json_output,
    _read_string,
    _safe_id,
    _short_id,
)
from backend.app.services.meeting_graph.task_projection_core.common import (
    planner_effect,
    planner_resource_kind,
    planner_result_status,
    planner_tool_name,
    status_for_task,
    task_result,
    task_time,
)


def build_planner_contract_tool_nodes(
    task: Task,
    binding: Dict[str, Any],
) -> tuple[List[MeetingExecutionGraphNode], List[MeetingExecutionGraphEdge]]:
    effect = planner_effect(binding)
    resource_kind = planner_resource_kind(binding)
    tool_name = planner_tool_name(task, binding)
    result = task_result(task)
    task_status = status_for_task(task)
    result_status = planner_result_status(task)
    binding_id = _read_string(binding.get("binding_id"), task.id)
    run_node_id = f"runner-task-{_safe_id(task.id)}"
    binding_node_id = f"planner-binding-{_safe_id(binding_id)}"
    tool_node_id = f"tool-call-{_safe_id(task.id)}"
    result_node_id = f"tool-result-{_safe_id(task.id)}"
    object_node_id = f"planner-object-{_safe_id(task.id)}"
    approval_required = bool(binding.get("approval_required"))
    approval_node_id: Optional[str] = (
        f"approval-{_safe_id(task.id)}" if approval_required else None
    )

    nodes: List[MeetingExecutionGraphNode] = [
        MeetingExecutionGraphNode(
            id=binding_node_id,
            eyebrow="Planner contract",
            title=tool_name,
            detail=f"{effect} · {resource_kind}",
            status="ready",
            kind="planner_contract_binding",
            lane="commands",
            output=_json_output(binding),
            defaultInspector="graph",
            metadata={
                "task_id": task.id,
                "binding": binding,
            },
        ),
        MeetingExecutionGraphNode(
            id=tool_node_id,
            eyebrow="Tool call",
            title=tool_name,
            detail=_read_string(
                _as_dict(task.params).get("description")
                or _as_dict(task.params).get("title"),
                f"task {_short_id(task.id)}",
            ),
            status=task_status,
            kind="tool_call",
            lane="commands",
            output=_json_output(_as_dict(task.params)),
            defaultInspector="runtime",
            metadata={
                "task_id": task.id,
                "tool_name": tool_name,
                "input_params": _as_dict(_as_dict(task.params).get("input_params")),
                "planner_contract_binding": binding,
            },
        ),
        MeetingExecutionGraphNode(
            id=run_node_id,
            eyebrow="Runner task",
            title=_read_string(task.pack_id, tool_name),
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
                "planner_contract_binding": binding,
            },
        ),
        MeetingExecutionGraphNode(
            id=result_node_id,
            eyebrow="Tool result",
            title=f"{resource_kind} result" if result else "Tool result pending",
            detail=(
                f"{len(result)} result fields"
                if result
                else "Waiting for Task.result from the existing runner path."
            ),
            status=result_status,
            kind="tool_result",
            lane="outputs",
            output=_json_output(result or {"status": result_status}),
            childCount=len(result) if result else None,
            defaultInspector="trace",
            degraded=task.status == TaskStatus.FAILED,
            metadata={
                "task_id": task.id,
                "result": result,
                "planner_contract_binding": binding,
            },
        ),
        MeetingExecutionGraphNode(
            id=object_node_id,
            eyebrow="Object read" if effect == "read" else "Object write",
            title=resource_kind,
            detail=f"{effect} via {tool_name}",
            status=result_status,
            kind="object_read" if effect == "read" else "object_write",
            lane="outputs" if effect != "read" else "context",
            output=_json_output(result or binding),
            defaultInspector="object",
            metadata={
                "task_id": task.id,
                "resource_kind": resource_kind,
                "effect": effect,
                "planner_contract_binding": binding,
                "result": result,
            },
        ),
    ]

    edges: List[MeetingExecutionGraphEdge] = [
        _edge(binding_node_id, tool_node_id, "binds"),
        _edge(tool_node_id, run_node_id, "dispatches"),
        _edge(run_node_id, result_node_id, "produces"),
        _edge(result_node_id, object_node_id, "materializes"),
    ]
    if approval_node_id:
        nodes.insert(
            2,
            MeetingExecutionGraphNode(
                id=approval_node_id,
                eyebrow="Approval gate",
                title="Write contract approval",
                detail=f"{effect} · idempotency={_read_string(binding.get('idempotency'), 'none')}",
                status="pending" if task.status == TaskStatus.PENDING else "ready",
                kind="approval_gate",
                lane="commands",
                output=_json_output(binding),
                defaultInspector="graph",
                metadata={
                    "task_id": task.id,
                    "planner_contract_binding": binding,
                },
            ),
        )
        edges = [
            _edge(binding_node_id, tool_node_id, "binds"),
            _edge(tool_node_id, approval_node_id, "requires_approval"),
            _edge(approval_node_id, run_node_id, "releases"),
            _edge(run_node_id, result_node_id, "produces"),
            _edge(result_node_id, object_node_id, "materializes"),
        ]
    return nodes, edges
