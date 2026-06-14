from backend.app.core.trace.trace_schema import TraceNodeType
from backend.app.services.run_harness.trace_mapping import map_run_harness_event


def test_trace_mapping_reuses_existing_node_types() -> None:
    assert map_run_harness_event("composition_graph") == TraceNodeType.GRAPH
    assert map_run_harness_event("deterministic_tool") == TraceNodeType.TOOL
    assert map_run_harness_event("approval") == TraceNodeType.HUMAN
    assert map_run_harness_event("unknown") == TraceNodeType.STATE

