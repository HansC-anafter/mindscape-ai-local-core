"""Meeting-owned semantic execution graph for AOL command proof."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from fastapi import APIRouter, Depends, Path, Query
from pydantic import BaseModel, Field

from backend.app.models.workspace import Task, TaskStatus, Workspace
from backend.app.routes.workspace_dependencies import get_artifacts_store, get_workspace
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.stores.object_relation_registry_store import (
    ObjectRelationRegistryStore,
)
from backend.app.services.stores.tasks_store import TasksStore

router = APIRouter()
logger = logging.getLogger(__name__)


class MeetingExecutionGraphNode(BaseModel):
    id: str
    title: str
    eyebrow: str
    detail: str = ""
    status: str = "ready"
    kind: str
    lane: str
    output: Optional[str] = None
    childCount: Optional[int] = None
    defaultInspector: Optional[str] = None
    traceFilter: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    degraded: bool = False


class MeetingExecutionGraphEdge(BaseModel):
    id: str
    from_id: str
    to_id: str
    type: str
    label: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class MeetingExecutionGraphResponse(BaseModel):
    workspace_id: str
    meeting_id: str
    nodes: List[MeetingExecutionGraphNode] = Field(default_factory=list)
    edges: List[MeetingExecutionGraphEdge] = Field(default_factory=list)
    lanes: List[str] = Field(
        default_factory=lambda: [
            "context",
            "commands",
            "runs",
            "outputs",
            "artifacts",
            "next",
        ]
    )
    task_count: int = 0
    relation_count: int = 0
    artifact_count: int = 0
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _read_string(value: Any, fallback: str = "") -> str:
    return value if isinstance(value, str) and value.strip() else fallback


def _short_id(value: Any) -> str:
    raw = str(value or "")
    if len(raw) <= 18:
        return raw or "none"
    return f"{raw[:8]}...{raw[-6:]}"


def _safe_id(value: Any) -> str:
    raw = str(value or "none")
    return "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in raw)[:96]


def _json_output(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, indent=2, default=str)
    except Exception:
        return str(value)


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


def _edge(from_id: str, to_id: str, edge_type: str, label: Optional[str] = None) -> MeetingExecutionGraphEdge:
    return MeetingExecutionGraphEdge(
        id=f"edge-{_safe_id(from_id)}-{_safe_id(edge_type)}-{_safe_id(to_id)}",
        from_id=from_id,
        to_id=to_id,
        type=edge_type,
        label=label,
    )


def _object_ref_payload(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        try:
            return value.model_dump(exclude_none=True)
        except Exception:
            return {}
    return {}


def _relation_payload(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        try:
            return value.model_dump(exclude_none=True)
        except Exception:
            pass
    payload: Dict[str, Any] = {}
    for field in (
        "relation_id",
        "relation_kind",
        "source_ref",
        "target_ref",
        "source_role",
        "target_role",
        "provenance_type",
        "provenance_id",
        "meeting_id",
        "metadata",
    ):
        if hasattr(value, field):
            payload[field] = getattr(value, field)
    if payload:
        payload["source_ref"] = _object_ref_payload(payload.get("source_ref"))
        payload["target_ref"] = _object_ref_payload(payload.get("target_ref"))
        payload["metadata"] = _as_dict(payload.get("metadata"))
    return payload


def _node_ref_uri(node: MeetingExecutionGraphNode) -> str:
    ref = _as_dict(node.metadata.get("ref"))
    return _read_string(ref.get("uri"))


def _object_node_title(ref: Dict[str, Any]) -> str:
    object_kind = _read_string(ref.get("object_kind"), "object")
    object_id = _read_string(ref.get("object_id"), ref.get("uri"))
    return f"{object_kind} {_short_id(object_id)}"


def _object_node_lane(ref: Dict[str, Any], role: str = "") -> str:
    object_kind = _read_string(ref.get("object_kind"))
    if role == "output" or object_kind in {"generated_reels_asset"} or object_kind.endswith("_asset"):
        return "artifacts"
    return "context"


def _fallback_object_node(
    *,
    ref: Dict[str, Any],
    role: str = "",
    relation_id: str = "",
) -> MeetingExecutionGraphNode:
    uri = _read_string(ref.get("uri"), _read_string(ref.get("object_id"), "unknown"))
    lane = _object_node_lane(ref, role)
    return MeetingExecutionGraphNode(
        id=f"object-{_safe_id(uri)}",
        eyebrow=role or _read_string(ref.get("owner_pack"), "Object"),
        title=_object_node_title(ref),
        detail=uri,
        status="context" if lane == "context" else "ready",
        kind="object" if lane == "context" else "artifact",
        lane=lane,
        defaultInspector="object",
        degraded=not bool(_read_string(ref.get("uri"))),
        metadata={
            "ref": ref,
            "role": role or None,
            "relation_id": relation_id or None,
        },
    )


def _relation_node_id(payload: Dict[str, Any]) -> str:
    explicit = _read_string(payload.get("relation_id"))
    if explicit:
        return f"relation-{_safe_id(explicit)}"
    source_uri = _read_string(_as_dict(payload.get("source_ref")).get("uri"))
    target_uri = _read_string(_as_dict(payload.get("target_ref")).get("uri"))
    digest = hashlib.sha256(
        json.dumps(
            {
                "source_uri": source_uri,
                "relation_kind": _read_string(payload.get("relation_kind")),
                "target_uri": target_uri,
                "provenance_id": _read_string(payload.get("provenance_id")),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()[:16]
    return f"relation-{digest}"


def _relation_action_plan_id(relation: Dict[str, Any]) -> str:
    metadata = _as_dict(relation.get("metadata"))
    provenance_type = _read_string(relation.get("provenance_type"))
    provenance_id = _read_string(relation.get("provenance_id"))
    if provenance_type in {"object_action_plan", "object_action_execution"} and provenance_id:
        return provenance_id
    return _read_string(metadata.get("action_plan_id"))


def _merge_plan_summary(summary: Dict[str, Any], relation: Dict[str, Any]) -> None:
    metadata = _as_dict(relation.get("metadata"))
    provenance_type = _read_string(relation.get("provenance_type"))
    status = _read_string(metadata.get("status"))
    instruction = _read_string(
        metadata.get("instruction")
        or metadata.get("meeting_command")
        or metadata.get("command")
    )
    affordance_verb = _read_string(
        metadata.get("affordance_verb")
        or metadata.get("verb")
        or _as_dict(metadata.get("selected_affordance")).get("verb")
    )
    if instruction and not summary.get("instruction"):
        summary["instruction"] = instruction
    if affordance_verb and not summary.get("affordance_verb"):
        summary["affordance_verb"] = affordance_verb
    if status and not summary.get("status"):
        summary["status"] = status
    if provenance_type == "object_action_execution":
        summary["has_execution"] = True
        if status:
            summary["execution_status"] = status
    summary.setdefault("relations", []).append(relation)


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


def _build_task_graph_nodes(task: Task) -> tuple[List[MeetingExecutionGraphNode], List[MeetingExecutionGraphEdge]]:
    inputs = _task_inputs(task)
    plan_payload = _plan_payload_from_inputs(inputs)
    action_plan_id = _read_string(
        inputs.get("object_action_plan_id") or plan_payload.get("action_plan_id")
    )
    if not action_plan_id:
        return [], []

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
    command_node_id = f"command-{_safe_id(action_plan_id)}"
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


def build_meeting_execution_graph(
    *,
    workspace_id: str,
    meeting_id: str,
    tasks: Iterable[Task],
    artifacts: Iterable[Any] = (),
    relations: Iterable[Any] = (),
) -> MeetingExecutionGraphResponse:
    nodes: List[MeetingExecutionGraphNode] = []
    edges: List[MeetingExecutionGraphEdge] = []
    seen_nodes: set[str] = set()
    seen_edges: set[str] = set()
    uri_to_node_id: Dict[str, str] = {}
    action_plan_ids: set[str] = set()
    plan_command_node_ids: Dict[str, str] = {}
    plan_run_node_ids: Dict[str, str] = {}
    task_count = 0

    def add_node(node: MeetingExecutionGraphNode) -> None:
        if node.id in seen_nodes:
            return
        seen_nodes.add(node.id)
        nodes.append(node)
        uri = _node_ref_uri(node)
        if uri and uri not in uri_to_node_id:
            uri_to_node_id[uri] = node.id

    def add_edge(edge: MeetingExecutionGraphEdge) -> None:
        if edge.id in seen_edges:
            return
        seen_edges.add(edge.id)
        edges.append(edge)

    for task in tasks:
        task_nodes, task_edges = _build_task_graph_nodes(task)
        if not task_nodes and not task_edges:
            continue
        task_count += 1
        for node in task_nodes:
            action_plan_id = _read_string(node.metadata.get("action_plan_id"))
            if action_plan_id:
                action_plan_ids.add(action_plan_id)
                if node.kind == "command":
                    plan_command_node_ids[action_plan_id] = node.id
                elif node.kind == "run":
                    plan_run_node_ids[action_plan_id] = node.id
            add_node(node)
        for edge in task_edges:
            add_edge(edge)

    relation_payloads: List[Dict[str, Any]] = []
    relation_plan_summaries: Dict[str, Dict[str, Any]] = {}
    for raw_relation in relations:
        relation = _relation_payload(raw_relation)
        if not relation:
            continue
        relation_payloads.append(relation)
        relation_action_plan_id = _relation_action_plan_id(relation)
        if relation_action_plan_id:
            summary = relation_plan_summaries.setdefault(
                relation_action_plan_id,
                {
                    "action_plan_id": relation_action_plan_id,
                    "has_execution": False,
                },
            )
            _merge_plan_summary(summary, relation)

    for action_plan_id, summary in relation_plan_summaries.items():
        command_node_id = plan_command_node_ids.get(action_plan_id)
        if not command_node_id:
            command_node_id = f"command-{_safe_id(action_plan_id)}"
            add_node(
                MeetingExecutionGraphNode(
                    id=command_node_id,
                    eyebrow="Command",
                    title=_read_string(
                        summary.get("instruction"),
                        f"Object action {_short_id(action_plan_id)}",
                    ),
                    detail=f"{_read_string(summary.get('affordance_verb'), 'object_action')} · plan {_short_id(action_plan_id)}",
                    status="ready",
                    kind="command",
                    lane="commands",
                    defaultInspector="trace",
                    metadata={
                        "action_plan_id": action_plan_id,
                        "affordance_verb": _read_string(summary.get("affordance_verb")),
                        "projection_source": "object_relations",
                        "relation_count": len(_as_list(summary.get("relations"))),
                    },
                )
            )
            plan_command_node_ids[action_plan_id] = command_node_id
        action_plan_ids.add(action_plan_id)

        if summary.get("has_execution") and action_plan_id not in plan_run_node_ids:
            run_node_id = f"run-proof-{_safe_id(action_plan_id)}"
            execution_status = _read_string(summary.get("execution_status"), "succeeded")
            add_node(
                MeetingExecutionGraphNode(
                    id=run_node_id,
                    eyebrow="Run proof",
                    title=_read_string(summary.get("affordance_verb"), "object action execution"),
                    detail=f"{execution_status} · plan {_short_id(action_plan_id)}",
                    status="error" if execution_status == "failed" else "ready",
                    kind="run",
                    lane="runs",
                    defaultInspector="trace",
                    degraded=False,
                    metadata={
                        "action_plan_id": action_plan_id,
                        "projection_source": "object_relations",
                        "execution_status": execution_status,
                    },
                )
            )
            add_edge(_edge(command_node_id, run_node_id, "dispatches", "execution proof"))
            plan_run_node_ids[action_plan_id] = run_node_id

    relation_count = 0
    for relation in relation_payloads:
        relation_count += 1
        source_ref = _object_ref_payload(relation.get("source_ref"))
        target_ref = _object_ref_payload(relation.get("target_ref"))
        relation_kind = _read_string(relation.get("relation_kind"), "related")
        provenance_id = _read_string(relation.get("provenance_id"))
        relation_action_plan_id = _relation_action_plan_id(relation)
        relation_id = _read_string(relation.get("relation_id"))
        source_uri = _read_string(source_ref.get("uri"))
        target_uri = _read_string(target_ref.get("uri"))
        source_role = _read_string(relation.get("source_role"))
        target_role = _read_string(relation.get("target_role"))

        if source_uri and source_uri in uri_to_node_id:
            source_node_id = uri_to_node_id[source_uri]
        else:
            source_node = _fallback_object_node(
                ref=source_ref,
                role=source_role,
                relation_id=relation_id,
            )
            source_node_id = source_node.id
            add_node(source_node)

        if target_uri and target_uri in uri_to_node_id:
            target_node_id = uri_to_node_id[target_uri]
        else:
            target_node = _fallback_object_node(
                ref=target_ref,
                role=target_role,
                relation_id=relation_id,
            )
            target_node_id = target_node.id
            add_node(target_node)

        relation_node_id = _relation_node_id(relation)
        relation_degraded = (
            not source_uri
            or not target_uri
            or (bool(provenance_id) and bool(action_plan_ids) and provenance_id not in action_plan_ids)
        )
        add_node(
            MeetingExecutionGraphNode(
                id=relation_node_id,
                eyebrow="Provenance",
                title=relation_kind,
                detail=(
                    f"{source_role or 'source'} -> {target_role or 'target'}"
                    + (f" · plan {_short_id(provenance_id)}" if provenance_id else "")
                ),
                status="blocked" if relation_degraded else "ready",
                kind="result",
                lane="outputs",
                output=_json_output(relation),
                defaultInspector="trace",
                degraded=relation_degraded,
                metadata={
                    "relation": relation,
                    "relation_id": relation_id,
                    "relation_kind": relation_kind,
                    "provenance_type": _read_string(relation.get("provenance_type")),
                    "provenance_id": provenance_id,
                },
            )
        )
        command_node_id = plan_command_node_ids.get(relation_action_plan_id)
        run_node_id = plan_run_node_ids.get(relation_action_plan_id)
        if run_node_id and _read_string(relation.get("provenance_type")) == "object_action_execution":
            add_edge(_edge(run_node_id, relation_node_id, "proves", "proves"))
        elif command_node_id:
            add_edge(_edge(command_node_id, relation_node_id, "plans", "plans"))
        add_edge(_edge(source_node_id, relation_node_id, relation_kind, relation_kind))
        add_edge(_edge(relation_node_id, target_node_id, "targets", target_role or None))

    artifact_count = 0
    for artifact in artifacts:
        artifact_count += 1
        artifact_id = getattr(artifact, "id", None)
        if not artifact_id:
            continue
        node_id = f"artifact-{_safe_id(artifact_id)}"
        add_node(
            MeetingExecutionGraphNode(
                id=node_id,
                eyebrow="Artifact",
                title=_read_string(getattr(artifact, "title", None), _short_id(artifact_id)),
                detail=_read_string(getattr(artifact, "summary", None), _read_string(getattr(artifact, "artifact_type", None), "")),
                status="ready",
                kind="artifact",
                lane="artifacts",
                metadata={
                    "artifact_id": artifact_id,
                    "task_id": getattr(artifact, "task_id", None),
                    "execution_id": getattr(artifact, "execution_id", None),
                    "storage_ref": getattr(artifact, "storage_ref", None),
                },
            )
        )

    return MeetingExecutionGraphResponse(
        workspace_id=workspace_id,
        meeting_id=meeting_id,
        nodes=nodes,
        edges=edges,
        task_count=task_count,
        relation_count=relation_count,
        artifact_count=artifact_count,
    )


def _event_type_value(event: Any) -> str:
    event_type = getattr(event, "event_type", "")
    return event_type.value if hasattr(event_type, "value") else str(event_type or "")


def _event_actor_value(event: Any) -> str:
    actor = getattr(event, "actor", "")
    return actor.value if hasattr(actor, "value") else str(actor or "")


def _event_payload(event: Any) -> Dict[str, Any]:
    payload = getattr(event, "payload", None)
    return payload if isinstance(payload, dict) else {}


def _event_runtime_node(event: Any) -> MeetingExecutionGraphNode:
    event_id = _read_string(getattr(event, "id", None), "event")
    event_type = _event_type_value(event)
    actor = _event_actor_value(event)
    payload = _event_payload(event)
    stage = _read_string(payload.get("stage"))
    agent_id = _read_string(payload.get("agent_id"))
    message = _read_string(
        payload.get("message")
        or payload.get("meeting_command")
        or payload.get("content")
        or stage
        or event_type,
        event_type or actor or "event",
    )

    if actor == "user":
        lane = "commands"
        kind = "command"
        eyebrow = "Command"
        status = "ready"
    elif stage:
        lane = "runs"
        kind = "run"
        eyebrow = "Runtime"
        status = "ready" if stage in {"agent_completed", "completed"} else "running"
    elif actor == "assistant":
        lane = "outputs"
        kind = "result"
        eyebrow = agent_id or "Assistant"
        status = "ready"
    else:
        lane = "runs"
        kind = "event"
        eyebrow = actor or event_type or "Event"
        status = "ready"

    detail_parts = [part for part in (stage, event_type, agent_id) if part]
    timestamp = getattr(event, "timestamp", None)
    if timestamp:
        try:
            detail_parts.append(timestamp.isoformat())
        except Exception:
            detail_parts.append(str(timestamp))

    return MeetingExecutionGraphNode(
        id=f"event-{_safe_id(event_id)}",
        eyebrow=eyebrow,
        title=message[:120],
        detail=" · ".join(detail_parts),
        status=status,
        kind=kind,
        lane=lane,
        output=_json_output(payload) if payload else None,
        defaultInspector="trace",
        traceFilter=event_id,
        metadata={
            "event_id": event_id,
            "event_type": event_type,
            "actor": actor,
            "payload": payload,
            "projection_source": "mind_events",
        },
    )


def merge_meeting_event_runtime_projection(
    response: MeetingExecutionGraphResponse,
    events: Iterable[Any],
) -> MeetingExecutionGraphResponse:
    """Project meeting-thread MindEvents into the graph runtime lanes."""
    seen_nodes = {node.id for node in response.nodes}
    seen_edges = {edge.id for edge in response.edges}
    previous_node_id = ""

    for event in events:
        node = _event_runtime_node(event)
        if node.id not in seen_nodes:
            response.nodes.append(node)
            seen_nodes.add(node.id)
        if previous_node_id:
            edge = _edge(previous_node_id, node.id, "then")
            if edge.id not in seen_edges:
                response.edges.append(edge)
                seen_edges.add(edge.id)
        previous_node_id = node.id

    return response


async def _bounded_graph_lookup(
    label: str,
    lookup,
    *,
    timeout: float = 2.0,
    fallback: Optional[List[Any]] = None,
) -> List[Any]:
    try:
        value = await asyncio.wait_for(asyncio.to_thread(lookup), timeout=timeout)
        return list(value or [])
    except Exception as exc:
        logger.warning("Meeting execution graph %s lookup degraded: %s", label, exc)
        return list(fallback or [])


@router.get(
    "/{workspace_id}/meetings/{meeting_id}/execution-graph",
    response_model=MeetingExecutionGraphResponse,
)
async def get_meeting_execution_graph(
    workspace_id: str = Path(..., description="Workspace ID"),
    meeting_id: str = Path(..., description="Meeting/session ID"),
    limit: int = Query(200, ge=1, le=500, description="Maximum task count"),
    workspace: Workspace = Depends(get_workspace),
    artifacts_store: Any = Depends(get_artifacts_store),
) -> MeetingExecutionGraphResponse:
    del workspace
    tasks_store = TasksStore()
    relations_store = ObjectRelationRegistryStore()
    event_store = MindscapeStore()

    events_lookup = _bounded_graph_lookup(
        "events",
        lambda: event_store.events.get_events_by_meeting_session(
            meeting_session_id=meeting_id,
            workspace_id=workspace_id,
            limit=limit,
        ),
        timeout=10.0,
    )
    tasks_lookup = _bounded_graph_lookup(
        "tasks",
        lambda: tasks_store.list_tasks_by_meeting_session(
            workspace_id=workspace_id,
            meeting_session_id=meeting_id,
            limit=limit,
        ),
        timeout=2.0,
    )
    artifacts_lookup = _bounded_graph_lookup(
        "artifacts",
        lambda: artifacts_store.get_by_thread(
            workspace_id=workspace_id,
            thread_id=meeting_id,
            limit=100,
        ),
        timeout=2.0,
    )
    relations_lookup = _bounded_graph_lookup(
        "relations",
        lambda: relations_store.search(
            workspace_id=workspace_id,
            meeting_id=meeting_id,
            limit=200,
        ),
        timeout=2.0,
    )
    events, tasks, artifacts, relations = await asyncio.gather(
        events_lookup,
        tasks_lookup,
        artifacts_lookup,
        relations_lookup,
    )
    response = build_meeting_execution_graph(
        workspace_id=workspace_id,
        meeting_id=meeting_id,
        tasks=tasks,
        artifacts=artifacts,
        relations=relations,
    )
    response = merge_meeting_event_runtime_projection(response, events)
    return response
