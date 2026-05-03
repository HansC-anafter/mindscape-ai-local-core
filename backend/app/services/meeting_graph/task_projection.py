"""Task projection helpers for meeting execution graphs."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List

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


def _task_time(task: Task) -> str:
    dt = task.completed_at or task.started_at or task.created_at
    if not dt:
        return ""
    try:
        return dt.isoformat()
    except Exception:
        return str(dt)


def _status_for_task(task: Task) -> str:
    if task.status == TaskStatus.RUNNING:
        return "running"
    if task.status == TaskStatus.PENDING:
        return "pending"
    if task.status == TaskStatus.FAILED:
        return "error"
    if task.status in {TaskStatus.CANCELLED_BY_USER, TaskStatus.EXPIRED}:
        return "blocked"
    return "ready"


def _plan_payload_from_inputs(inputs: Dict[str, Any]) -> Dict[str, Any]:
    raw_plan = _as_dict(inputs.get("object_action_plan"))
    return _as_dict(raw_plan.get("request_plan")) or raw_plan


def _role_entries_from_inputs(inputs: Dict[str, Any]) -> List[Dict[str, Any]]:
    entries = _as_list(inputs.get("object_action_entries"))
    if entries:
        return [entry for entry in entries if isinstance(entry, dict)]
    plan = _as_dict(inputs.get("object_action_plan"))
    return [entry for entry in _as_list(plan.get("role_assignments")) if isinstance(entry, dict)]


def _task_inputs(task: Task) -> Dict[str, Any]:
    ctx = _as_dict(task.execution_context)
    inputs = _as_dict(ctx.get("inputs"))
    if inputs:
        return inputs
    return _as_dict(task.params)


def _task_command_id(inputs: Dict[str, Any], plan_payload: Dict[str, Any]) -> str:
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


def _task_closure(task: Task) -> Dict[str, Any]:
    return _as_dict(_as_dict(task.execution_context).get("object_action_closure"))


def _build_role_nodes(
    *,
    task: Task,
    command_node_id: str,
    entries: Iterable[Dict[str, Any]],
) -> tuple[List[MeetingExecutionGraphNode], List[MeetingExecutionGraphEdge]]:
    nodes: List[MeetingExecutionGraphNode] = []
    edges: List[MeetingExecutionGraphEdge] = []
    seen: set[str] = set()
    for entry in entries:
        role = _read_string(entry.get("role"), "object")
        ref = _as_dict(entry.get("ref"))
        uri = _read_string(ref.get("uri"))
        object_kind = _read_string(ref.get("object_kind"), "object")
        object_id = _read_string(ref.get("object_id"), uri)
        node_id = f"role-{_safe_id(role)}-{_safe_id(uri or object_id)}"
        if node_id not in seen:
            seen.add(node_id)
            nodes.append(
                MeetingExecutionGraphNode(
                    id=node_id,
                    eyebrow=role,
                    title=f"{object_kind} {_short_id(object_id)}",
                    detail=uri or object_id,
                    status="context",
                    kind="object",
                    lane="context",
                    defaultInspector="object",
                    metadata={
                        "task_id": task.id,
                        "role": role,
                        "ref": ref,
                    },
                )
            )
        edges.append(_edge(node_id, command_node_id, "used_as", role))
    return nodes, edges


def build_task_graph_nodes(
    task: Task,
) -> tuple[List[MeetingExecutionGraphNode], List[MeetingExecutionGraphEdge]]:
    inputs = _task_inputs(task)
    plan_payload = _plan_payload_from_inputs(inputs)
    action_plan_id = _read_string(
        inputs.get("object_action_plan_id") or plan_payload.get("action_plan_id")
    )
    if not action_plan_id:
        return [], []
    command_id = _task_command_id(inputs, plan_payload)

    command = _read_string(
        inputs.get("meeting_command")
        or inputs.get("instruction")
        or inputs.get("message"),
        f"Object action {_short_id(action_plan_id)}",
    )
    affordance_verb = _read_string(
        plan_payload.get("affordance_verb")
        or _as_dict(_as_dict(inputs.get("object_action_plan")).get("selected_affordance")).get("verb"),
        _read_string(task.pack_id, "object_action"),
    )
    command_node_id = f"command-{_safe_id(command_id or action_plan_id)}"
    run_node_id = f"run-{_safe_id(task.id)}"
    nodes: List[MeetingExecutionGraphNode] = [
        MeetingExecutionGraphNode(
            id=command_node_id,
            eyebrow="Command",
            title=command,
            detail=f"{affordance_verb} · plan {_short_id(action_plan_id)}",
            status="ready",
            kind="command",
            lane="commands",
            defaultInspector="trace",
            metadata={
                "task_id": task.id,
                "command_id": command_id or None,
                "action_plan_id": action_plan_id,
                "affordance_verb": affordance_verb,
                "inputs": inputs,
            },
        ),
        MeetingExecutionGraphNode(
            id=run_node_id,
            eyebrow="Run",
            title=_read_string(task.pack_id, "workspace runtime"),
            detail=f"{task.status.value if hasattr(task.status, 'value') else task.status} · task {_short_id(task.id)}",
            status=_status_for_task(task),
            kind="run",
            lane="runs",
            output=f"Execution ID: {task.execution_id or task.id}",
            defaultInspector="runtime",
            metadata={
                "task_id": task.id,
                "execution_id": task.execution_id,
                "action_plan_id": action_plan_id,
                "completed_at": _task_time(task),
            },
        ),
    ]
    edges: List[MeetingExecutionGraphEdge] = [
        _edge(command_node_id, run_node_id, "dispatches"),
    ]
    role_nodes, role_edges = _build_role_nodes(
        task=task,
        command_node_id=command_node_id,
        entries=_role_entries_from_inputs(inputs),
    )
    nodes.extend(role_nodes)
    edges.extend(role_edges)

    closure = _task_closure(task)
    output_node_id = f"closure-{_safe_id(action_plan_id)}"
    if closure:
        closure_status = _read_string(closure.get("status"), "pending")
        skipped = closure_status == "skipped"
        failed = closure_status == "failed"
        nodes.append(
            MeetingExecutionGraphNode(
                id=output_node_id,
                eyebrow="Closure",
                title=(
                    "No addressable output emitted"
                    if skipped
                    else "Object action closed"
                    if not failed
                    else "Object action closure failed"
                ),
                detail=(
                    _read_string(closure.get("reason"), "Runtime completed without output records.")
                    if skipped or failed
                    else f"{closure.get('indexed_output_count', 0)} outputs · {closure.get('indexed_relation_count', 0)} relations"
                ),
                status="blocked" if skipped else "error" if failed else "ready",
                kind="result",
                lane="outputs",
                output=_json_output(closure),
                childCount=len(_as_list(closure.get("output_refs"))) or None,
                defaultInspector="trace",
                degraded=skipped or failed,
                metadata={
                    "task_id": task.id,
                    "action_plan_id": action_plan_id,
                    "closure": closure,
                },
            )
        )
        edges.append(_edge(run_node_id, output_node_id, "closes"))
        for output_ref in _as_list(closure.get("output_refs")):
            if not isinstance(output_ref, dict):
                continue
            object_kind = _read_string(output_ref.get("object_kind"), "output")
            object_id = _read_string(output_ref.get("object_id"), output_ref.get("uri"))
            output_ref_node_id = f"output-object-{_safe_id(output_ref.get('uri') or object_id)}"
            nodes.append(
                MeetingExecutionGraphNode(
                    id=output_ref_node_id,
                    eyebrow="Output object",
                    title=f"{object_kind} {_short_id(object_id)}",
                    detail=_read_string(output_ref.get("uri"), object_id),
                    status="ready",
                    kind="artifact",
                    lane="artifacts",
                    defaultInspector="object",
                    metadata={
                        "task_id": task.id,
                        "action_plan_id": action_plan_id,
                        "ref": output_ref,
                    },
                )
            )
            edges.append(_edge(output_node_id, output_ref_node_id, "produced"))
    else:
        nodes.append(
            MeetingExecutionGraphNode(
                id=output_node_id,
                eyebrow="Closure",
                title="Closure pending",
                detail="Waiting for runtime output records or terminal closure status.",
                status="pending" if task.status in {TaskStatus.PENDING, TaskStatus.RUNNING} else "blocked",
                kind="result",
                lane="outputs",
                defaultInspector="trace",
                degraded=task.status not in {TaskStatus.PENDING, TaskStatus.RUNNING},
                metadata={
                    "task_id": task.id,
                    "action_plan_id": action_plan_id,
                },
            )
        )
        edges.append(_edge(run_node_id, output_node_id, "awaits_closure"))
    return nodes, edges
