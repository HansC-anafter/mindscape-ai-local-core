"""Map run harness events onto the existing trace node vocabulary."""

from backend.app.core.trace.trace_schema import TraceNodeType


_EVENT_NODE_TYPES = {
    "composition_graph": TraceNodeType.GRAPH,
    "deterministic_tool": TraceNodeType.TOOL,
    "durable_workflow": TraceNodeType.STATE,
    "policy_eval": TraceNodeType.POLICY,
    "approval": TraceNodeType.HUMAN,
    "wait": TraceNodeType.STATE,
    "artifact": TraceNodeType.CHANGESET,
}


def map_run_harness_event(event_type: str) -> TraceNodeType:
    return _EVENT_NODE_TYPES.get(event_type, TraceNodeType.STATE)

