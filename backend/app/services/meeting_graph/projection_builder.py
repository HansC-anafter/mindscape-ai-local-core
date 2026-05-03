"""Projection builder for meeting execution graph responses."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List

from backend.app.models.meeting_graph import (
    MeetingExecutionGraphEdge,
    MeetingExecutionGraphNode,
    MeetingExecutionGraphResponse,
)
from backend.app.models.workspace import Task
from backend.app.services.meeting_execution_graph_commands import (
    project_command_ledger_graph,
)
from backend.app.services.meeting_graph.projection_utils import (
    _as_list,
    _edge,
    _fallback_object_node,
    _json_output,
    _merge_plan_summary,
    _node_ref_uri,
    _object_ref_payload,
    _read_string,
    _relation_action_plan_id,
    _relation_node_id,
    _relation_payload,
    _safe_id,
    _short_id,
)
from backend.app.services.meeting_graph.task_projection import build_task_graph_nodes


def build_meeting_execution_graph(
    *,
    workspace_id: str,
    meeting_id: str,
    commands: Iterable[Any] = (),
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

    command_projection = project_command_ledger_graph(commands)
    plan_command_node_ids.update(command_projection.plan_command_node_ids)
    action_plan_ids.update(command_projection.action_plan_ids)
    for command_node in command_projection.nodes:
        add_node(MeetingExecutionGraphNode.model_validate(command_node))

    for task in tasks:
        task_nodes, task_edges = build_task_graph_nodes(task)
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

    relation_payloads, relation_plan_summaries = _summarize_relations(relations)
    _add_relation_summary_nodes(
        add_node=add_node,
        add_edge=add_edge,
        action_plan_ids=action_plan_ids,
        plan_command_node_ids=plan_command_node_ids,
        plan_run_node_ids=plan_run_node_ids,
        relation_plan_summaries=relation_plan_summaries,
    )
    relation_count = _add_relation_proof_nodes(
        add_node=add_node,
        add_edge=add_edge,
        action_plan_ids=action_plan_ids,
        plan_command_node_ids=plan_command_node_ids,
        plan_run_node_ids=plan_run_node_ids,
        relation_payloads=relation_payloads,
        uri_to_node_id=uri_to_node_id,
    )
    artifact_count = _add_artifact_nodes(add_node, artifacts)

    return MeetingExecutionGraphResponse(
        workspace_id=workspace_id,
        meeting_id=meeting_id,
        nodes=nodes,
        edges=edges,
        task_count=task_count,
        relation_count=relation_count,
        artifact_count=artifact_count,
    )


def _summarize_relations(
    relations: Iterable[Any],
) -> tuple[List[Dict[str, Any]], Dict[str, Dict[str, Any]]]:
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
    return relation_payloads, relation_plan_summaries


def _add_relation_summary_nodes(
    *,
    add_node,
    add_edge,
    action_plan_ids: set[str],
    plan_command_node_ids: Dict[str, str],
    plan_run_node_ids: Dict[str, str],
    relation_plan_summaries: Dict[str, Dict[str, Any]],
) -> None:
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


def _add_relation_proof_nodes(
    *,
    add_node,
    add_edge,
    action_plan_ids: set[str],
    plan_command_node_ids: Dict[str, str],
    plan_run_node_ids: Dict[str, str],
    relation_payloads: List[Dict[str, Any]],
    uri_to_node_id: Dict[str, str],
) -> int:
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
    return relation_count


def _add_artifact_nodes(add_node, artifacts: Iterable[Any]) -> int:
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
                detail=_read_string(
                    getattr(artifact, "summary", None),
                    _read_string(getattr(artifact, "artifact_type", None), ""),
                ),
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
    return artifact_count
