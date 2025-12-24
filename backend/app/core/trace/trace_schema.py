"""
Trace Schema

Defines the structure for tracing execution steps in staged model switching.
Each trace node represents a single step (LLM call, tool execution, policy decision, human interaction).
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any
import json
import uuid


class TraceNodeType(str, Enum):
    """Type of trace node"""
    LLM = "llm"  # LLM call (intent analysis, plan generation, etc.)
    TOOL = "tool"  # Tool execution
    POLICY = "policy"  # Policy decision
    HUMAN = "human"  # Human interaction (approval, input, etc.)
    STATE = "state"  # State update (WorldState, PlanState, DecisionState)
    CHANGESET = "changeset"  # ChangeSet creation/application
    GRAPH = "graph"  # Graph execution node


class TraceEdgeType(str, Enum):
    """Type of trace edge"""
    SEQUENTIAL = "sequential"  # Sequential execution
    PARALLEL = "parallel"  # Parallel execution
    CONDITIONAL = "conditional"  # Conditional branch
    LOOP = "loop"  # Loop iteration
    ERROR = "error"  # Error propagation


class TraceStatus(str, Enum):
    """Status of a trace node"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


@dataclass
class TraceMetadata:
    """Metadata for trace nodes"""
    workspace_id: str
    execution_id: str
    plan_id: Optional[str] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    model_name: Optional[str] = None
    capability_profile: Optional[str] = None
    cost_tokens: Optional[int] = None
    latency_ms: Optional[int] = None
    error_message: Optional[str] = None
    error_stack: Optional[str] = None
    custom_metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "workspace_id": self.workspace_id,
            "execution_id": self.execution_id,
        }
        if self.plan_id:
            result["plan_id"] = self.plan_id
        if self.user_id:
            result["user_id"] = self.user_id
        if self.session_id:
            result["session_id"] = self.session_id
        if self.model_name:
            result["model_name"] = self.model_name
        if self.capability_profile:
            result["capability_profile"] = self.capability_profile
        if self.cost_tokens:
            result["cost_tokens"] = self.cost_tokens
        if self.latency_ms:
            result["latency_ms"] = self.latency_ms
        if self.error_message:
            result["error_message"] = self.error_message
        if self.error_stack:
            result["error_stack"] = self.error_stack
        if self.custom_metadata:
            result["custom_metadata"] = self.custom_metadata
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TraceMetadata":
        return cls(
            workspace_id=data["workspace_id"],
            execution_id=data["execution_id"],
            plan_id=data.get("plan_id"),
            user_id=data.get("user_id"),
            session_id=data.get("session_id"),
            model_name=data.get("model_name"),
            capability_profile=data.get("capability_profile"),
            cost_tokens=data.get("cost_tokens"),
            latency_ms=data.get("latency_ms"),
            error_message=data.get("error_message"),
            error_stack=data.get("error_stack"),
            custom_metadata=data.get("custom_metadata", {}),
        )


@dataclass
class TraceNode:
    """A single trace node representing one execution step"""
    node_id: str
    node_type: TraceNodeType
    name: str
    status: TraceStatus
    start_time: datetime
    end_time: Optional[datetime] = None
    metadata: Optional[TraceMetadata] = None
    input_data: Optional[Dict[str, Any]] = None
    output_data: Optional[Dict[str, Any]] = None
    version: str = "1.0"

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "node_id": self.node_id,
            "node_type": self.node_type.value,
            "name": self.name,
            "status": self.status.value,
            "start_time": self.start_time.isoformat(),
            "version": self.version,
        }
        if self.end_time:
            result["end_time"] = self.end_time.isoformat()
        if self.metadata:
            result["metadata"] = self.metadata.to_dict()
        if self.input_data:
            result["input_data"] = self.input_data
        if self.output_data:
            result["output_data"] = self.output_data
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TraceNode":
        return cls(
            node_id=data["node_id"],
            node_type=TraceNodeType(data["node_type"]),
            name=data["name"],
            status=TraceStatus(data["status"]),
            start_time=datetime.fromisoformat(data["start_time"]),
            end_time=datetime.fromisoformat(data["end_time"]) if data.get("end_time") else None,
            metadata=TraceMetadata.from_dict(data["metadata"]) if data.get("metadata") else None,
            input_data=data.get("input_data"),
            output_data=data.get("output_data"),
            version=data.get("version", "1.0"),
        )

    def duration_ms(self) -> Optional[int]:
        """Calculate duration in milliseconds"""
        if self.end_time:
            delta = self.end_time - self.start_time
            return int(delta.total_seconds() * 1000)
        return None


@dataclass
class TraceEdge:
    """An edge connecting two trace nodes"""
    edge_id: str
    source_node_id: str
    target_node_id: str
    edge_type: TraceEdgeType
    label: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "edge_id": self.edge_id,
            "source_node_id": self.source_node_id,
            "target_node_id": self.target_node_id,
            "edge_type": self.edge_type.value,
        }
        if self.label:
            result["label"] = self.label
        if self.metadata:
            result["metadata"] = self.metadata
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TraceEdge":
        return cls(
            edge_id=data["edge_id"],
            source_node_id=data["source_node_id"],
            target_node_id=data["target_node_id"],
            edge_type=TraceEdgeType(data["edge_type"]),
            label=data.get("label"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class TraceGraph:
    """Complete trace graph for an execution"""
    trace_id: str
    root_node_id: Optional[str] = None
    nodes: List[TraceNode] = field(default_factory=list)
    edges: List[TraceEdge] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    version: str = "1.0"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "root_node_id": self.root_node_id,
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
            "created_at": self.created_at.isoformat(),
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TraceGraph":
        return cls(
            trace_id=data["trace_id"],
            root_node_id=data.get("root_node_id"),
            nodes=[TraceNode.from_dict(n) for n in data.get("nodes", [])],
            edges=[TraceEdge.from_dict(e) for e in data.get("edges", [])],
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.utcnow(),
            version=data.get("version", "1.0"),
        )

    def get_node(self, node_id: str) -> Optional[TraceNode]:
        """Get a node by ID"""
        for node in self.nodes:
            if node.node_id == node_id:
                return node
        return None

    def get_children(self, node_id: str) -> List[TraceNode]:
        """Get all child nodes of a given node"""
        child_ids = [edge.target_node_id for edge in self.edges if edge.source_node_id == node_id]
        return [node for node in self.nodes if node.node_id in child_ids]

    def get_parents(self, node_id: str) -> List[TraceNode]:
        """Get all parent nodes of a given node"""
        parent_ids = [edge.source_node_id for edge in self.edges if edge.target_node_id == node_id]
        return [node for node in self.nodes if node.node_id in parent_ids]

    def to_json(self) -> str:
        """Export to JSON string"""
        return json.dumps(self.to_dict(), indent=2, default=str)





