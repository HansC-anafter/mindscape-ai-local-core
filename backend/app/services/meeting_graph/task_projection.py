"""Task projection helpers for meeting execution graphs."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

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


def _planner_binding_from_task(task: Task) -> Dict[str, Any]:
    ctx = _as_dict(task.execution_context)
    binding = _as_dict(ctx.get("planner_contract_binding"))
    if binding:
        return binding
    return _as_dict(_as_dict(task.params).get("planner_contract_binding"))


def _planner_tool_plan_from_task(task: Task) -> Dict[str, Any]:
    inputs = _task_inputs(task)
    plan = _as_dict(inputs.get("planner_tool_plan"))
    if plan:
        return plan
    params = _as_dict(task.params)
    input_params = _as_dict(params.get("input_params"))
    return _as_dict(input_params.get("planner_tool_plan"))


def _task_result(task: Task) -> Dict[str, Any]:
    return _as_dict(task.result)


def _planner_result_status(task: Task) -> str:
    if task.status in {TaskStatus.PENDING, TaskStatus.RUNNING}:
        return "pending"
    if task.status == TaskStatus.FAILED:
        return "error"
    return "ready"


def _planner_resource_kind(binding: Dict[str, Any]) -> str:
    return _read_string(binding.get("resource_kind"), "resource")


def _planner_effect(binding: Dict[str, Any]) -> str:
    return _read_string(binding.get("effect"), "action").lower()


def _planner_tool_name(task: Task, binding: Dict[str, Any]) -> str:
    return _read_string(
        binding.get("tool_name")
        or _as_dict(task.execution_context).get("tool_name")
        or _as_dict(task.params).get("tool_name"),
        "planner tool",
    )


def _build_planner_contract_tool_nodes(
    task: Task,
    binding: Dict[str, Any],
) -> tuple[List[MeetingExecutionGraphNode], List[MeetingExecutionGraphEdge]]:
    effect = _planner_effect(binding)
    resource_kind = _planner_resource_kind(binding)
    tool_name = _planner_tool_name(task, binding)
    result = _task_result(task)
    task_status = _status_for_task(task)
    result_status = _planner_result_status(task)
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
                "completed_at": _task_time(task),
                "planner_contract_binding": binding,
            },
        ),
        MeetingExecutionGraphNode(
            id=result_node_id,
            eyebrow="Tool result",
            title=(
                f"{resource_kind} result"
                if result
                else "Tool result pending"
            ),
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


def _build_planner_tool_plan_nodes(
    task: Task,
    plan: Dict[str, Any],
) -> tuple[List[MeetingExecutionGraphNode], List[MeetingExecutionGraphEdge]]:
    task_result = _task_result(task)
    tool_result = _as_dict(task_result.get("result"))
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
    task_status = _status_for_task(task)
    result_status = _planner_result_status(task)
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
                "completed_at": _task_time(task),
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
    planner_binding = _planner_binding_from_task(task)
    if task.task_type == "tool_execution" and planner_binding:
        return _build_planner_contract_tool_nodes(task, planner_binding)
    planner_tool_plan = _planner_tool_plan_from_task(task)
    if task.task_type == "tool_execution" and planner_tool_plan:
        return _build_planner_tool_plan_nodes(task, planner_tool_plan)

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
