"""
Reasoning trace model for SGR (Self-Graph Reasoning) integration.

Stores structured reasoning graphs generated during LLM interactions.
This is the single source of truth for reasoning graph data.
MindEvent.metadata only stores reasoning_graph_id as a reference.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class SGRMode(str, Enum):
    """SGR execution mode."""

    INLINE = "inline"  # Single LLM call: graph + answer together
    TWO_PASS = "two_pass"  # Two calls: graph first, then answer


@dataclass
class EvidenceSource:
    """Structured evidence reference for governance audit trail."""

    source_type: str  # url | commit | artifact | test | log
    ref: str  # The actual reference (URL, commit hash, file path, etc.)
    label: Optional[str] = None  # Human-readable description


@dataclass
class ReasoningNode:
    """A single node in a reasoning graph."""

    id: str
    content: str
    type: str  # premise | inference | conclusion | evidence | risk
    metadata: Dict[str, Any] = field(default_factory=dict)
    # Governance fields (v2)
    intent_ids: List[str] = field(default_factory=list)
    evidence_sources: List[EvidenceSource] = field(default_factory=list)
    decision_status: Optional[str] = (
        None  # proposal | decided | rejected (conclusion nodes only)
    )


@dataclass
class ReasoningEdge:
    """A single edge in a reasoning graph."""

    source: str  # from node id
    target: str  # to node id
    relation: str  # supports | contradicts | derived_from


@dataclass
class ReasoningGraph:
    """Complete reasoning graph structure (supports v1 and v2 schemas)."""

    nodes: List[ReasoningNode]
    edges: List[ReasoningEdge]
    answer: Optional[str] = None
    schema_version: int = 1

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "schema_version": self.schema_version,
            "nodes": [],
            "edges": [
                {"source": e.source, "target": e.target, "relation": e.relation}
                for e in self.edges
            ],
            "answer": self.answer,
        }
        for n in self.nodes:
            node_dict: Dict[str, Any] = {
                "id": n.id,
                "content": n.content,
                "type": n.type,
                "metadata": n.metadata,
            }
            # Include v2 fields only if populated
            if n.intent_ids:
                node_dict["intent_ids"] = n.intent_ids
            if n.evidence_sources:
                node_dict["evidence_sources"] = [
                    {"source_type": es.source_type, "ref": es.ref, "label": es.label}
                    for es in n.evidence_sources
                ]
            if n.decision_status:
                node_dict["decision_status"] = n.decision_status
            result["nodes"].append(node_dict)
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReasoningGraph":
        detected_version = data.get("schema_version", 1)
        nodes = []
        for n in data.get("nodes", []):
            # Parse v2 governance fields (safe for v1: defaults to empty)
            intent_ids = n.get("intent_ids", [])
            # Handle single intent_ref (v2 LLM output) → list
            if not intent_ids and n.get("intent_ref"):
                intent_ids = [n["intent_ref"]]

            evidence_sources = []
            for es in n.get("evidence_sources", []):
                evidence_sources.append(
                    EvidenceSource(
                        source_type=es.get("source_type", "unknown"),
                        ref=es.get("ref", ""),
                        label=es.get("label"),
                    )
                )
            # Handle single evidence_source (v2 LLM output) → list
            if not evidence_sources and n.get("evidence_source"):
                es = n["evidence_source"]
                if isinstance(es, dict):
                    evidence_sources.append(
                        EvidenceSource(
                            source_type=es.get("source_type", "unknown"),
                            ref=es.get("ref", ""),
                            label=es.get("label"),
                        )
                    )

            nodes.append(
                ReasoningNode(
                    id=n["id"],
                    content=n["content"],
                    type=n["type"],
                    metadata=n.get("metadata", {}),
                    intent_ids=intent_ids,
                    evidence_sources=evidence_sources,
                    decision_status=n.get("decision_status"),
                )
            )

        edges = [
            ReasoningEdge(
                source=e.get("source", e.get("from", "")),
                target=e.get("target", e.get("to", "")),
                relation=e["relation"],
            )
            for e in data.get("edges", [])
        ]
        return cls(
            nodes=nodes,
            edges=edges,
            answer=data.get("answer"),
            schema_version=detected_version,
        )


@dataclass
class ReasoningTrace:
    """Persisted reasoning trace record."""

    id: str
    workspace_id: str
    execution_id: Optional[str]
    assistant_event_id: Optional[str]
    graph_json: Dict[str, Any]
    schema_version: int
    sgr_mode: str
    model: Optional[str]
    token_count: Optional[int]
    latency_ms: Optional[int]
    created_at: datetime
    # Governance fields (G4: trace versioning)
    parent_trace_id: Optional[str] = None
    supersedes: Optional[List[str]] = None  # JSON-serialized list of trace IDs
    meeting_session_id: Optional[str] = None
    # Cross-instance fields (Phase 4: governance trace propagation)
    device_id: Optional[str] = None
    remote_parent_trace_id: Optional[str] = None

    @property
    def graph(self) -> ReasoningGraph:
        return ReasoningGraph.from_dict(self.graph_json)

    @staticmethod
    def new(
        workspace_id: str,
        graph: ReasoningGraph,
        sgr_mode: SGRMode = SGRMode.INLINE,
        execution_id: Optional[str] = None,
        assistant_event_id: Optional[str] = None,
        model: Optional[str] = None,
        token_count: Optional[int] = None,
        latency_ms: Optional[int] = None,
        parent_trace_id: Optional[str] = None,
        meeting_session_id: Optional[str] = None,
        device_id: Optional[str] = None,
        remote_parent_trace_id: Optional[str] = None,
    ) -> "ReasoningTrace":
        return ReasoningTrace(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            execution_id=execution_id,
            assistant_event_id=assistant_event_id,
            graph_json=graph.to_dict(),
            schema_version=graph.schema_version,
            sgr_mode=sgr_mode.value,
            model=model,
            token_count=token_count,
            latency_ms=latency_ms,
            created_at=datetime.now(timezone.utc),
            parent_trace_id=parent_trace_id,
            meeting_session_id=meeting_session_id,
            device_id=device_id,
            remote_parent_trace_id=remote_parent_trace_id,
        )
