"""Cross-instance lifecycle and trace propagation tests."""

import uuid

from cross_instance_e2e_test_support import InMemoryRegistryV2


class TestCrossInstanceLifecycle:
    """A creates, B claims, compiles, commits, and completes a handoff."""

    def setup_method(self) -> None:
        self.registry = InMemoryRegistryV2()
        self.handoff_id = str(uuid.uuid4())
        self.device_a = "dev-A"
        self.device_b = "dev-B"

    def test_full_lifecycle_with_trace(self) -> None:
        self.registry.create(
            self.handoff_id,
            "tenant-1",
            {"intent": "build landing page", "goals": ["responsive", "dark mode"]},
            self.device_a,
            self.device_b,
        )

        trace_a = str(uuid.uuid4())
        self.registry.append_event(
            self.handoff_id,
            "handoff_published",
            self.device_a,
            payload={"source": "meeting engine"},
            trace_context={"trace_id": trace_a, "device_id": self.device_a},
        )

        self.registry.transition(self.handoff_id, "claimed", self.device_b)

        trace_b = str(uuid.uuid4())
        self.registry.append_event(
            self.handoff_id,
            "compile_started",
            self.device_b,
            trace_context={
                "trace_id": trace_b,
                "parent_trace_id": trace_a,
                "device_id": self.device_b,
            },
        )
        self.registry.append_event(
            self.handoff_id,
            "compile_completed",
            self.device_b,
            payload={"task_ir_id": "ir-001"},
            trace_context={
                "trace_id": trace_b,
                "parent_trace_id": trace_a,
                "device_id": self.device_b,
            },
        )

        self.registry.transition(
            self.handoff_id,
            "committed",
            self.device_b,
            {"accepted": True, "task_ir_id": "ir-001"},
        )
        self.registry.transition(self.handoff_id, "dispatched", self.device_b)
        self.registry.transition(
            self.handoff_id,
            "completed",
            self.device_b,
            {"output": "done"},
        )

        timeline = self.registry.get_timeline(self.handoff_id)
        assert timeline["chain_valid"] is True
        assert timeline["count"] == 8

        dag = self.registry.get_trace_dag(self.handoff_id)
        assert dag["node_count"] == 8

        cross_edges = [edge for edge in dag["edges"] if edge["relation"] == "cross_instance"]
        assert len(cross_edges) >= 1, "Expected at least 1 cross-instance edge"

        for edge in cross_edges:
            from_node = next(node for node in dag["nodes"] if node["event_id"] == edge["from"])
            to_node = next(node for node in dag["nodes"] if node["event_id"] == edge["to"])
            assert from_node["device_id"] == self.device_a
            assert to_node["device_id"] == self.device_b
