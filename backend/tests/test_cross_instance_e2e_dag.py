"""DAG and hash-chain integrity tests for cross-instance handoffs."""

import uuid

from cross_instance_e2e_test_support import InMemoryRegistryV2


class TestDAGIntegrity:
    """Hash chain and DAG edges stay consistent after multi-device lifecycles."""

    def test_dag_edges_correct_after_full_lifecycle(self) -> None:
        registry = InMemoryRegistryV2()
        handoff_id = str(uuid.uuid4())
        trace_a = str(uuid.uuid4())
        trace_b = str(uuid.uuid4())

        registry.create(handoff_id, "t1", {"intent": "dag test"}, "d-A", "d-B")
        registry.append_event(
            handoff_id,
            "published",
            "d-A",
            trace_context={"trace_id": trace_a, "device_id": "d-A"},
        )

        registry.transition(handoff_id, "claimed", "d-B")
        registry.append_event(
            handoff_id,
            "compile_completed",
            "d-B",
            payload={"task_ir_id": "ir-1"},
            trace_context={
                "trace_id": trace_b,
                "parent_trace_id": trace_a,
                "device_id": "d-B",
            },
        )

        registry.transition(handoff_id, "committed", "d-B")
        registry.transition(handoff_id, "dispatched", "d-B")
        registry.transition(handoff_id, "completed", "d-B", {"output": "done"})

        timeline = registry.get_timeline(handoff_id)
        assert timeline["chain_valid"] is True

        dag = registry.get_trace_dag(handoff_id)
        hash_edges = [edge for edge in dag["edges"] if edge["relation"] == "hash_chain"]
        cross_edges = [edge for edge in dag["edges"] if edge["relation"] == "cross_instance"]

        assert len(hash_edges) == dag["node_count"] - 1
        assert len(cross_edges) >= 1

        edge_keys = [(edge["from"], edge["to"], edge["relation"]) for edge in dag["edges"]]
        assert len(edge_keys) == len(set(edge_keys)), "Duplicate edges found"

    def test_tampered_chain_detected_in_cross_instance(self) -> None:
        registry = InMemoryRegistryV2()
        handoff_id = str(uuid.uuid4())
        registry.create(handoff_id, "t1", {}, "d-A", "d-B")
        registry.transition(handoff_id, "claimed", "d-B")
        registry.append_event(
            handoff_id,
            "compile_completed",
            "d-B",
            trace_context={"trace_id": "t-B", "device_id": "d-B"},
        )
        registry.transition(handoff_id, "committed", "d-B")

        registry.events[handoff_id][1]["payload_hash"] = "tampered"

        timeline = registry.get_timeline(handoff_id)
        assert timeline["chain_valid"] is False
