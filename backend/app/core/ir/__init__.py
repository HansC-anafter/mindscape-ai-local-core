"""
Intermediate Representation (IR) Schemas

Structured data formats for inter-stage communication in staged model switching.
All IR schemas are designed to be:
- Fixed JSON schema (no semantic drift)
- Versioned (for backward compatibility)
- Validated (type-safe)
"""

from .intent import IntentIR, ToolSlotAnalysisResult, ToolRelevanceResult
from .tool_slot_call import ToolSlotCallIR, ToolSlotCallStatus
from .scope_ref import ScopeRefIR, ScopeType
from .changeset import ChangeSetIR, ChangeSetStatus, ChangePatch, ChangeType
from .graph_ir import GraphIR, GraphNode, GraphEdge, GraphState, NodeType, EdgeType, StateType

__all__ = [
    # Intent IR
    "IntentIR",
    "ToolSlotAnalysisResult",
    "ToolRelevanceResult",
    # ToolSlotCall IR
    "ToolSlotCallIR",
    "ToolSlotCallStatus",
    # ScopeRef IR
    "ScopeRefIR",
    "ScopeType",
    # ChangeSet IR
    "ChangeSetIR",
    "ChangeSetStatus",
    "ChangePatch",
    "ChangeType",
    # Graph IR
    "GraphIR",
    "GraphNode",
    "GraphEdge",
    "GraphState",
    "NodeType",
    "EdgeType",
    "StateType",
]

