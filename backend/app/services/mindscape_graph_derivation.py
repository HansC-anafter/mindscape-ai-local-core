"""Derived graph helpers for MindscapeGraphService."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from backend.app.services.mindscape_graph_models import (
    EdgeOrigin,
    EdgeType,
    MindscapeEdge,
    MindscapeGraph,
    MindscapeNode,
    NodeIdPrefix,
    NodeStatus,
    _normalize_datetime,
    generate_edge_id,
    generate_node_id,
)


async def derive_graph(service: Any, scope_type: str, scope_id: str) -> MindscapeGraph:
    """
    Derive graph from existing data sources.

    This generates the derived layer from timeline items, tasks, and artifacts.
    """
    graph = MindscapeGraph(scope_type=scope_type, scope_id=scope_id)

    from app.services.stores.postgres.timeline_items_store import (
        PostgresTimelineItemsStore,
    )
    from app.services.stores.tasks_store import TasksStore

    timeline_store = PostgresTimelineItemsStore()
    tasks_store = TasksStore()

    workspace_ids = await get_workspace_ids(scope_type, scope_id)

    for workspace_id in workspace_ids:
        await derive_from_timeline(graph, workspace_id, timeline_store, tasks_store)
        await derive_from_executions(graph, workspace_id, tasks_store)
        await derive_from_artifacts(graph, workspace_id)

    derive_edges(graph)
    graph.derived_at = datetime.now(timezone.utc)
    return graph


async def get_workspace_ids(scope_type: str, scope_id: str) -> List[str]:
    """Get workspace IDs for the given scope."""
    if scope_type == "workspace":
        return [scope_id]

    from app.services.stores.postgres.workspace_group_store import (
        PostgresWorkspaceGroupStore,
    )

    store = PostgresWorkspaceGroupStore()
    group = store.get(scope_id)
    return group.workspace_ids if group else []


async def derive_from_timeline(
    graph: MindscapeGraph, workspace_id: str, timeline_store: Any, tasks_store: Any
) -> None:
    """Derive intent nodes from timeline items with playbook associations."""
    items = timeline_store.list_timeline_items_by_workspace(
        workspace_id=workspace_id, limit=500
    )
    task_cache: Dict[str, Any] = {}

    for item in items:
        linked_playbook_codes: List[str] = []

        if item.task_id:
            if item.task_id not in task_cache:
                task = tasks_store.get_task(item.task_id)
                task_cache[item.task_id] = task
            else:
                task = task_cache[item.task_id]

            if task:
                if task.execution_context:
                    playbook_code = task.execution_context.get("playbook_code")
                    if playbook_code:
                        linked_playbook_codes.append(playbook_code)

                if task.params and not linked_playbook_codes:
                    playbook_code = task.params.get("playbook_code")
                    if playbook_code:
                        linked_playbook_codes.append(playbook_code)

        if item.data:
            intent_analysis = item.data.get("intent_analysis", {})
            if isinstance(intent_analysis, dict):
                playbook_code = intent_analysis.get("playbook_code")
                if playbook_code and playbook_code not in linked_playbook_codes:
                    linked_playbook_codes.append(playbook_code)

        project_id = None
        if item.task_id and task_cache.get(item.task_id):
            cached_task = task_cache[item.task_id]
            project_id = getattr(cached_task, "project_id", None)

        thread_id = None
        if item.data and isinstance(item.data, dict):
            thread_id = item.data.get("thread_id")

        node = MindscapeNode(
            id=generate_node_id(NodeIdPrefix.INTENT, item.id),
            type="intent",
            label=item.title or item.summary or "Untitled",
            status=NodeStatus.SUGGESTED,
            metadata={
                "timeline_item_id": item.id,
                "timeline_type": item.type.value if item.type else None,
                "message_id": item.message_id,
                "task_id": item.task_id,
                "project_id": project_id,
                "thread_id": thread_id,
                "linked_playbook_codes": linked_playbook_codes,
            },
            created_at=item.created_at,
        )
        graph.nodes.append(node)


async def derive_from_executions(
    graph: MindscapeGraph, workspace_id: str, tasks_store: Any
) -> None:
    """Derive execution nodes from tasks with execution summary."""
    tasks = tasks_store.list_tasks_by_workspace(workspace_id=workspace_id, limit=500)

    for task in tasks:
        if not task.execution_id:
            continue

        run_number = 1
        result_summary = None
        artifact_count = 0
        if task.result and isinstance(task.result, dict):
            result_summary = task.result.get("summary") or task.result.get("message")
            artifacts = task.result.get("artifacts", [])
            artifact_count = len(artifacts) if isinstance(artifacts, list) else 0

        playbook_code = None
        if task.execution_context:
            playbook_code = task.execution_context.get("playbook_code")
        if not playbook_code and task.params:
            playbook_code = task.params.get("playbook_code")

        node = MindscapeNode(
            id=generate_node_id(NodeIdPrefix.EXECUTION, task.execution_id),
            type="execution",
            label=f"{task.pack_id}:{task.task_type}" if task.pack_id else task.task_type,
            status=(
                NodeStatus.ACCEPTED
                if task.status.value == "succeeded"
                else NodeStatus.SUGGESTED
            ),
            metadata={
                "task_id": task.id,
                "execution_id": task.execution_id,
                "project_id": getattr(task, "project_id", None),
                "pack_id": task.pack_id,
                "task_type": task.task_type,
                "status": task.status.value,
                "run_number": run_number,
                "playbook_code": playbook_code,
                "result_summary": result_summary,
                "artifact_count": artifact_count,
                "completed_at": task.completed_at.isoformat()
                if task.completed_at
                else None,
                "error": task.error,
            },
            created_at=task.created_at,
        )
        graph.nodes.append(node)


async def derive_from_artifacts(graph: MindscapeGraph, workspace_id: str) -> None:
    """Keep artifact derivation disabled until a stable registry source is available."""
    return None


def derive_from_reasoning_graph(
    graph: MindscapeGraph,
    trace_id: str,
    reasoning_graph: Dict[str, Any],
) -> None:
    """Derive reasoning nodes and edges from an SGR reasoning graph."""
    sgr_nodes = reasoning_graph.get("nodes", [])
    sgr_edges = reasoning_graph.get("edges", [])
    sgr_to_ms_id: Dict[str, str] = {}

    for sgr_node in sgr_nodes:
        sgr_id = sgr_node.get("id", "")
        ms_node_id = generate_node_id(NodeIdPrefix.REASONING, trace_id, sgr_id)
        sgr_to_ms_id[sgr_id] = ms_node_id
        graph.nodes.append(
            MindscapeNode(
                id=ms_node_id,
                type=f"reasoning_{sgr_node.get('type', 'unknown')}",
                label=sgr_node.get("content", "")[:100],
                status=NodeStatus.ACCEPTED,
                metadata={
                    "reasoning_trace_id": trace_id,
                    "sgr_node_id": sgr_id,
                    "sgr_node_type": sgr_node.get("type", "unknown"),
                    "full_content": sgr_node.get("content", ""),
                    **sgr_node.get("metadata", {}),
                },
            )
        )

    relation_map = {
        "supports": EdgeType.SUPPORTS,
        "contradicts": EdgeType.CONTRADICTS,
        "derived_from": EdgeType.DERIVED_FROM,
    }

    for sgr_edge in sgr_edges:
        source_sgr = sgr_edge.get("source", sgr_edge.get("from", ""))
        target_sgr = sgr_edge.get("target", sgr_edge.get("to", ""))
        relation = sgr_edge.get("relation", "supports")

        from_id = sgr_to_ms_id.get(source_sgr)
        to_id = sgr_to_ms_id.get(target_sgr)
        if not from_id or not to_id:
            continue

        edge_type = relation_map.get(relation, EdgeType.SUPPORTS)
        confidence = 0.8 if edge_type != EdgeType.DERIVED_FROM else 1.0
        graph.edges.append(
            MindscapeEdge(
                id=generate_edge_id(from_id, to_id, edge_type.value),
                from_id=from_id,
                to_id=to_id,
                type=edge_type,
                origin=EdgeOrigin.SGR,
                confidence=confidence,
                status=NodeStatus.ACCEPTED,
                metadata={
                    "reasoning_trace_id": trace_id,
                    "original_relation": relation,
                },
            )
        )


def derive_edges(graph: MindscapeGraph) -> None:
    """Derive edges based on derivation rules."""
    sorted_nodes = sorted(graph.nodes, key=lambda node: _normalize_datetime(node.created_at))

    for index in range(len(sorted_nodes) - 1):
        current = sorted_nodes[index]
        next_node = sorted_nodes[index + 1]
        if current.type == next_node.type == "intent":
            graph.edges.append(
                MindscapeEdge(
                    id=generate_edge_id(
                        current.id, next_node.id, EdgeType.TEMPORAL.value
                    ),
                    from_id=current.id,
                    to_id=next_node.id,
                    type=EdgeType.TEMPORAL,
                    origin=EdgeOrigin.DERIVED,
                    confidence=0.9,
                )
            )

    for node in graph.nodes:
        if node.type != "intent" or not node.metadata.get("task_id"):
            continue
        task_id = node.metadata["task_id"]
        for execution_node in graph.nodes:
            if (
                execution_node.type == "execution"
                and execution_node.metadata.get("task_id") == task_id
            ):
                graph.edges.append(
                    MindscapeEdge(
                        id=generate_edge_id(
                            node.id, execution_node.id, EdgeType.SPAWNS.value
                        ),
                        from_id=node.id,
                        to_id=execution_node.id,
                        type=EdgeType.SPAWNS,
                        origin=EdgeOrigin.DERIVED,
                        confidence=1.0,
                    )
                )
