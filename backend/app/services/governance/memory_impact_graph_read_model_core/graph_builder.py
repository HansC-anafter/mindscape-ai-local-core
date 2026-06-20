"""Graph assembly helpers for memory impact graph read models."""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Optional

from backend.app.models.meeting_decision import MeetingDecision
from backend.app.models.meeting_session import MeetingSession
from backend.app.services.governance.memory_impact_graph_contract import (
    MemoryImpactGraphEdge,
    MemoryImpactGraphFocus,
    MemoryImpactGraphNode,
    MemoryImpactGraphResponse,
    MemoryImpactPacketSummary,
)
from backend.app.services.governance.memory_impact_graph_read_model_core.packet_nodes import (
    build_selected_packet_nodes,
)
from backend.app.services.governance.memory_impact_graph_read_model_core.session_nodes import (
    build_action_item_node,
    build_artifact_node,
    build_canonical_memory_node,
    build_decision_node,
    build_digest_node,
    build_execution_node,
    build_session_node,
    collect_artifact_refs,
)


class GraphAccumulator:
    """Collect graph nodes and edges while preserving first-seen ordering."""

    def __init__(self) -> None:
        self.nodes_by_id: Dict[str, MemoryImpactGraphNode] = {}
        self.edges_by_id: Dict[str, MemoryImpactGraphEdge] = {}

    def upsert_node(self, node: MemoryImpactGraphNode) -> None:
        existing = self.nodes_by_id.get(node.id)
        if existing is None:
            self.nodes_by_id[node.id] = node
            return
        if not existing.label and node.label:
            existing.label = node.label
        if not existing.subtitle and node.subtitle:
            existing.subtitle = node.subtitle
        if not existing.status and node.status:
            existing.status = node.status
        if node.metadata:
            existing.metadata.update(node.metadata)

    def add_edge(
        self,
        from_node_id: str,
        to_node_id: str,
        kind: str,
        *,
        provenance: str = "explicit",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        edge_id = f"{kind}:{from_node_id}->{to_node_id}:{provenance}"
        if edge_id in self.edges_by_id:
            return
        self.edges_by_id[edge_id] = MemoryImpactGraphEdge(
            id=edge_id,
            from_node_id=from_node_id,
            to_node_id=to_node_id,
            kind=kind,
            provenance=provenance,
            metadata=dict(metadata or {}),
        )


def build_memory_impact_graph(
    *,
    workspace_id: str,
    session: MeetingSession,
    selected_memory_packet: Dict[str, Any],
    selected_node_ids: List[str],
    explicit_trace: Dict[str, Any],
    canonical_memory: Dict[str, Any],
    requested_execution_id: Optional[str],
    execution_ids: List[str],
    decisions: List[MeetingDecision],
    canonical_memory_item: Optional[Any],
    warnings: List[str],
) -> MemoryImpactGraphResponse:
    accumulator = GraphAccumulator()
    session_node_id = (
        explicit_trace.get("session_node_id") or f"meeting_session:{session.id}"
    )

    if requested_execution_id and requested_execution_id not in execution_ids:
        warnings.append("requested_execution_id_not_linked_to_session")

    accumulator.upsert_node(build_session_node(session, session_node_id))
    for node in build_selected_packet_nodes(
        workspace_id=workspace_id,
        selected_memory_packet=selected_memory_packet,
    ):
        accumulator.upsert_node(node)

    selected_node_ids = _resolve_selected_node_ids(
        selected_node_ids=selected_node_ids,
        session_node_id=session_node_id,
        node_ids=list(accumulator.nodes_by_id),
    )
    _add_selected_nodes(accumulator, session_node_id, selected_node_ids)
    _add_execution_nodes(accumulator, session_node_id, execution_ids)
    _add_decision_nodes(accumulator, session_node_id, decisions, explicit_trace)
    _add_action_item_nodes(accumulator, session_node_id, session, explicit_trace)
    _add_canonical_memory_nodes(
        accumulator=accumulator,
        session_node_id=session_node_id,
        canonical_memory=canonical_memory,
        explicit_trace=explicit_trace,
        canonical_memory_item=canonical_memory_item,
    )

    packet_summary = MemoryImpactPacketSummary(
        selected_node_count=len(selected_node_ids),
        route_sections=list(selected_memory_packet.get("route_plan") or []),
        counts_by_type=dict(Counter(node.type for node in accumulator.nodes_by_id.values())),
        selection=dict(selected_memory_packet.get("selection") or {}),
    )
    focus = MemoryImpactGraphFocus(
        workspace_id=workspace_id,
        session_id=session.id,
        focus_node_id=session_node_id,
        project_id=session.project_id,
        thread_id=session.thread_id,
        execution_id=requested_execution_id,
        execution_ids=execution_ids,
    )
    return MemoryImpactGraphResponse(
        workspace_id=workspace_id,
        session_id=session.id,
        focus=focus,
        packet_summary=packet_summary,
        nodes=list(accumulator.nodes_by_id.values()),
        edges=list(accumulator.edges_by_id.values()),
        warnings=warnings,
    )


def _resolve_selected_node_ids(
    *,
    selected_node_ids: List[str],
    session_node_id: str,
    node_ids: List[str],
) -> List[str]:
    if selected_node_ids:
        return selected_node_ids
    return [
        node_id
        for node_id in node_ids
        if node_id != session_node_id
        and not node_id.startswith("execution:")
        and not node_id.startswith("meeting_decision:")
        and not node_id.startswith("action_item:")
        and not node_id.startswith("session_digest:")
        and not node_id.startswith("artifact:")
    ]


def _add_selected_nodes(
    accumulator: GraphAccumulator,
    session_node_id: str,
    selected_node_ids: List[str],
) -> None:
    for node_id in selected_node_ids:
        if node_id not in accumulator.nodes_by_id:
            accumulator.upsert_node(
                MemoryImpactGraphNode(
                    id=node_id,
                    type="memory_item",
                    label=node_id,
                    metadata={"placeholder": True},
                )
            )
        accumulator.add_edge(session_node_id, node_id, "selected_for_context")


def _add_execution_nodes(
    accumulator: GraphAccumulator,
    session_node_id: str,
    execution_ids: List[str],
) -> None:
    for exec_id in execution_ids:
        execution_node = build_execution_node(exec_id)
        accumulator.upsert_node(execution_node)
        accumulator.add_edge(session_node_id, execution_node.id, "produced")


def _add_decision_nodes(
    accumulator: GraphAccumulator,
    session_node_id: str,
    decisions: List[MeetingDecision],
    explicit_trace: Dict[str, Any],
) -> None:
    decision_ids = list(explicit_trace.get("meeting_decision_node_ids") or [])
    if not decision_ids and decisions:
        decision_ids = [f"meeting_decision:{decision.id}" for decision in decisions]

    for index, decision in enumerate(decisions):
        node_id = (
            decision_ids[index]
            if index < len(decision_ids)
            else f"meeting_decision:{decision.id}"
        )
        accumulator.upsert_node(build_decision_node(decision, node_id=node_id))
        accumulator.add_edge(session_node_id, node_id, "produced")


def _add_action_item_nodes(
    accumulator: GraphAccumulator,
    session_node_id: str,
    session: MeetingSession,
    explicit_trace: Dict[str, Any],
) -> None:
    action_item_node_ids = list(explicit_trace.get("action_item_node_ids") or [])
    for index, action_item in enumerate(list(getattr(session, "action_items", []) or [])):
        node_id = (
            action_item_node_ids[index]
            if index < len(action_item_node_ids)
            else f"action_item:{session.id}:{index}"
        )
        accumulator.upsert_node(
            build_action_item_node(action_item, node_id=node_id, index=index)
        )
        accumulator.add_edge(session_node_id, node_id, "produced")
        _add_action_execution_node(accumulator, node_id, action_item)
        _add_artifact_nodes(accumulator, node_id, action_item)


def _add_action_execution_node(
    accumulator: GraphAccumulator,
    action_node_id: str,
    action_item: Dict[str, Any],
) -> None:
    action_execution_id = str(action_item.get("execution_id") or "").strip()
    if not action_execution_id:
        return
    execution_node = build_execution_node(action_execution_id)
    accumulator.upsert_node(execution_node)
    accumulator.add_edge(action_node_id, execution_node.id, "produced")


def _add_artifact_nodes(
    accumulator: GraphAccumulator,
    action_node_id: str,
    action_item: Dict[str, Any],
) -> None:
    for artifact_ref in collect_artifact_refs(action_item):
        artifact_node = build_artifact_node(artifact_ref)
        accumulator.upsert_node(artifact_node)
        accumulator.add_edge(action_node_id, artifact_node.id, "produced")


def _add_canonical_memory_nodes(
    *,
    accumulator: GraphAccumulator,
    session_node_id: str,
    canonical_memory: Dict[str, Any],
    explicit_trace: Dict[str, Any],
    canonical_memory_item: Optional[Any],
) -> None:
    canonical_memory_item_id = str(canonical_memory.get("memory_item_id") or "").strip()
    canonical_memory_node_id = str(
        explicit_trace.get("canonical_writeback_node_id") or ""
    ).strip()
    if canonical_memory_item_id:
        canonical_memory_node_id = (
            canonical_memory_node_id or f"memory_item:{canonical_memory_item_id}"
        )
        accumulator.upsert_node(
            build_canonical_memory_node(
                node_id=canonical_memory_node_id,
                memory_item_id=canonical_memory_item_id,
                memory_item=canonical_memory_item,
                canonical_memory=canonical_memory,
            )
        )
        accumulator.add_edge(
            session_node_id,
            canonical_memory_node_id,
            "writes_back_to",
            metadata={"writeback_run_id": canonical_memory.get("writeback_run_id")},
        )

    digest_id = str(canonical_memory.get("digest_id") or "").strip()
    digest_node_id = str(explicit_trace.get("digest_node_id") or "").strip()
    if digest_id:
        digest_node_id = digest_node_id or f"session_digest:{digest_id}"
        accumulator.upsert_node(build_digest_node(digest_id, digest_node_id))
        accumulator.add_edge(session_node_id, digest_node_id, "produced")
        if canonical_memory_node_id:
            accumulator.add_edge(canonical_memory_node_id, digest_node_id, "derived_from")
