"""Models and identifiers for the mindscape graph service."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class NodeIdPrefix(str, Enum):
    """Stable node ID prefixes for different node types."""

    INTENT = "intent"
    EXECUTION = "execution"
    PLAYBOOK = "playbook"
    STEP = "step"
    ARTIFACT = "artifact"
    MANUAL = "manual"
    REASONING = "reasoning"


def generate_node_id(prefix: NodeIdPrefix, *parts: str) -> str:
    """
    Generate stable node ID from prefix and parts.

    Examples:
        - intent:ti_abc123
        - execution:exec_xyz789
        - playbook:ig_analyze@v1.2.3
        - step:exec_xyz789:s1
        - artifact:art_def456
        - manual:uuid
    """
    return f"{prefix.value}:{':'.join(parts)}"


def generate_edge_id(from_id: str, to_id: str, edge_type: str) -> str:
    """
    Generate edge ID using hash to avoid overly long IDs.

    Format: edge:<sha1(from|to|type).slice(0,12)>
    """
    content = f"{from_id}|{to_id}|{edge_type}"
    hash_value = hashlib.sha1(content.encode()).hexdigest()[:12]
    return f"edge:{hash_value}"


class EdgeType(str, Enum):
    """Edge types with confidence levels defined in derivation rules."""

    TEMPORAL = "temporal"
    SPAWNS = "spawns"
    PRODUCES = "produces"
    DEPENDENCY = "dependency"
    CAUSAL = "causal"
    REFERS_TO = "refers_to"
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    DERIVED_FROM = "derived_from"


class EdgeOrigin(str, Enum):
    """Origin of edge."""

    DERIVED = "derived"
    USER = "user"
    SGR = "sgr"


class NodeStatus(str, Enum):
    """Node status for suggested and confirmed graph items."""

    SUGGESTED = "suggested"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


@dataclass
class MindscapeNode:
    """Base node in the mindscape graph."""

    id: str
    type: str
    label: str
    status: NodeStatus = NodeStatus.SUGGESTED
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class MindscapeEdge:
    """Edge in the mindscape graph."""

    id: str
    from_id: str
    to_id: str
    type: EdgeType
    origin: EdgeOrigin = EdgeOrigin.DERIVED
    confidence: float = 1.0
    status: NodeStatus = NodeStatus.SUGGESTED
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OverlayNode:
    """Manually created node in the overlay."""

    id: str
    type: str
    label: str
    position: Dict[str, float]
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphOverlay:
    """Overlay layer storing user modifications."""

    node_positions: Dict[str, Dict[str, float]] = field(default_factory=dict)
    collapsed_state: Dict[str, bool] = field(default_factory=dict)
    viewport: Optional[Dict[str, float]] = None
    renames: Dict[str, str] = field(default_factory=dict)
    merge_redirects: Dict[str, str] = field(default_factory=dict)
    manual_nodes: List[OverlayNode] = field(default_factory=list)
    manual_edges: List[MindscapeEdge] = field(default_factory=list)
    node_status_overrides: Dict[str, str] = field(default_factory=dict)
    edge_status_overrides: Dict[str, str] = field(default_factory=dict)
    version: int = 0


@dataclass
class MindscapeGraph:
    """Complete mindscape graph combining derived data and overlay."""

    nodes: List[MindscapeNode] = field(default_factory=list)
    edges: List[MindscapeEdge] = field(default_factory=list)
    overlay: GraphOverlay = field(default_factory=GraphOverlay)
    scope_type: str = "workspace"
    scope_id: str = ""
    last_event_seq: int = 0
    derived_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class DerivationRule:
    """Rule for deriving edges from existing data."""

    edge_type: EdgeType
    source: str
    confidence: float
    description: str


DERIVATION_RULES: List[DerivationRule] = [
    DerivationRule(
        edge_type=EdgeType.TEMPORAL,
        source="timeline_items",
        confidence=0.9,
        description="Connect timeline items by created_at order",
    ),
    DerivationRule(
        edge_type=EdgeType.SPAWNS,
        source="intent_to_execution",
        confidence=1.0,
        description="Intent -> Execution when linkedExecutionId exists",
    ),
    DerivationRule(
        edge_type=EdgeType.PRODUCES,
        source="artifact_registry",
        confidence=1.0,
        description="Execution/Step -> Artifact via source_ref",
    ),
    DerivationRule(
        edge_type=EdgeType.DEPENDENCY,
        source="playbook_steps",
        confidence=1.0,
        description="Step A -> Step B via PlaybookJson.steps dependencies",
    ),
    DerivationRule(
        edge_type=EdgeType.CAUSAL,
        source="conversation_window",
        confidence=0.7,
        description="Decision/Constraint -> Intent in same conversation window",
    ),
    DerivationRule(
        edge_type=EdgeType.REFERS_TO,
        source="nlp_extraction",
        confidence=0.6,
        description="References to other Intent/Artifact via NLP",
    ),
]


def _normalize_datetime(dt: Optional[datetime]) -> datetime:
    """Normalize datetime for comparison."""
    if dt is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt
