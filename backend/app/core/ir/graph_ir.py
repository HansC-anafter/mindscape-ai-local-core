"""
Graph IR Schema

Intermediate representation for graph structures (node/edge/state three-layer).
Used for graph-based workflow representation and variant selection.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Set
from enum import Enum


class NodeType(str, Enum):
    """Node type"""
    START = "start"
    END = "end"
    TASK = "task"
    DECISION = "decision"
    PARALLEL = "parallel"
    MERGE = "merge"
    TOOL_CALL = "tool_call"
    PLAYBOOK = "playbook"


class EdgeType(str, Enum):
    """Edge type"""
    SEQUENTIAL = "sequential"
    CONDITIONAL = "conditional"
    PARALLEL = "parallel"
    ERROR = "error"
    ROLLBACK = "rollback"


class StateType(str, Enum):
    """State type"""
    WORLD = "world"  # Tool results and facts
    PLAN = "plan"  # LLM plans (can have multiple versions)
    DECISION = "decision"  # Scope/publish/important decisions


@dataclass
class GraphNode:
    """
    Graph node

    Represents a node in the graph IR.
    """
    node_id: str
    node_type: NodeType
    label: str  # Human-readable label
    description: Optional[str] = None

    # Node-specific data
    task_slot: Optional[str] = None  # Tool slot (for tool_call nodes)
    playbook_code: Optional[str] = None  # Playbook code (for playbook nodes)
    condition: Optional[str] = None  # Condition expression (for decision nodes)

    # Node metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        result = {
            "node_id": self.node_id,
            "node_type": self.node_type.value,
            "label": self.label,
            "metadata": self.metadata,
        }
        if self.description:
            result["description"] = self.description
        if self.task_slot:
            result["task_slot"] = self.task_slot
        if self.playbook_code:
            result["playbook_code"] = self.playbook_code
        if self.condition:
            result["condition"] = self.condition
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GraphNode":
        """Create GraphNode from dictionary"""
        return cls(
            node_id=data["node_id"],
            node_type=NodeType(data["node_type"]),
            label=data["label"],
            description=data.get("description"),
            task_slot=data.get("task_slot"),
            playbook_code=data.get("playbook_code"),
            condition=data.get("condition"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class GraphEdge:
    """
    Graph edge

    Represents an edge in the graph IR.
    """
    edge_id: str
    from_node_id: str
    to_node_id: str
    edge_type: EdgeType
    label: Optional[str] = None  # Human-readable label

    # Edge-specific data
    condition: Optional[str] = None  # Condition expression (for conditional edges)
    weight: Optional[float] = None  # Edge weight (for variant selection)

    # Edge metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        result = {
            "edge_id": self.edge_id,
            "from_node_id": self.from_node_id,
            "to_node_id": self.to_node_id,
            "edge_type": self.edge_type.value,
            "metadata": self.metadata,
        }
        if self.label:
            result["label"] = self.label
        if self.condition:
            result["condition"] = self.condition
        if self.weight is not None:
            result["weight"] = self.weight
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GraphEdge":
        """Create GraphEdge from dictionary"""
        return cls(
            edge_id=data["edge_id"],
            from_node_id=data["from_node_id"],
            to_node_id=data["to_node_id"],
            edge_type=EdgeType(data["edge_type"]),
            label=data.get("label"),
            condition=data.get("condition"),
            weight=data.get("weight"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class GraphState:
    """
    Graph state

    Represents state associated with nodes/edges in the graph IR.
    Three-layer state model:
    - World: Tool results and facts (read-only from tools)
    - Plan: LLM plans (can have multiple versions, can be overwritten)
    - Decision: Scope/publish/important decisions (only policy can write)
    """
    state_id: str
    state_type: StateType
    node_id: Optional[str] = None  # Associated node ID
    edge_id: Optional[str] = None  # Associated edge ID

    # State data
    data: Dict[str, Any] = field(default_factory=dict)

    # State versioning (for Plan state)
    version: Optional[int] = None

    # State metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        result = {
            "state_id": self.state_id,
            "state_type": self.state_type.value,
            "data": self.data,
            "metadata": self.metadata,
        }
        if self.node_id:
            result["node_id"] = self.node_id
        if self.edge_id:
            result["edge_id"] = self.edge_id
        if self.version is not None:
            result["version"] = self.version
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GraphState":
        """Create GraphState from dictionary"""
        return cls(
            state_id=data["state_id"],
            state_type=StateType(data["state_type"]),
            node_id=data.get("node_id"),
            edge_id=data.get("edge_id"),
            data=data.get("data", {}),
            version=data.get("version"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class GraphIR:
    """
    Graph IR Schema

    Structured intermediate representation for graph structures.
    Three-layer model: nodes, edges, and states.

    Used for:
    - Graph-based workflow representation
    - Variant selection (fast path vs safe path)
    - Graph execution and state management
    """
    # Graph identification
    graph_id: str
    graph_name: str
    description: Optional[str] = None

    # Graph structure (three-layer)
    nodes: List[GraphNode] = field(default_factory=list)
    edges: List[GraphEdge] = field(default_factory=list)
    states: List[GraphState] = field(default_factory=list)

    # Graph metadata
    variant_name: Optional[str] = None  # Variant name (e.g., "fast_path", "safe_path")
    tags: List[str] = field(default_factory=list)  # Tags for variant selection

    # Version for backward compatibility
    version: str = "1.0"

    # Additional metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "version": self.version,
            "graph_id": self.graph_id,
            "graph_name": self.graph_name,
            "description": self.description,
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
            "states": [state.to_dict() for state in self.states],
            "variant_name": self.variant_name,
            "tags": self.tags,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GraphIR":
        """Create GraphIR from dictionary"""
        nodes = [GraphNode.from_dict(n) for n in data.get("nodes", [])]
        edges = [GraphEdge.from_dict(e) for e in data.get("edges", [])]
        states = [GraphState.from_dict(s) for s in data.get("states", [])]

        return cls(
            graph_id=data["graph_id"],
            graph_name=data["graph_name"],
            description=data.get("description"),
            nodes=nodes,
            edges=edges,
            states=states,
            variant_name=data.get("variant_name"),
            tags=data.get("tags", []),
            version=data.get("version", "1.0"),
            metadata=data.get("metadata", {}),
        )

    def get_node(self, node_id: str) -> Optional[GraphNode]:
        """Get node by ID"""
        for node in self.nodes:
            if node.node_id == node_id:
                return node
        return None

    def get_edges_from(self, node_id: str) -> List[GraphEdge]:
        """Get all edges from a node"""
        return [edge for edge in self.edges if edge.from_node_id == node_id]

    def get_edges_to(self, node_id: str) -> List[GraphEdge]:
        """Get all edges to a node"""
        return [edge for edge in self.edges if edge.to_node_id == node_id]

    def get_state(self, state_id: str) -> Optional[GraphState]:
        """Get state by ID"""
        for state in self.states:
            if state.state_id == state_id:
                return state
        return None

    def get_states_by_node(self, node_id: str) -> List[GraphState]:
        """Get all states associated with a node"""
        return [state for state in self.states if state.node_id == node_id]

    def get_states_by_type(self, state_type: StateType) -> List[GraphState]:
        """Get all states of a specific type"""
        return [state for state in self.states if state.state_type == state_type]










