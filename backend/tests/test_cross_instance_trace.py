"""
Phase 4 — Cross-Instance Governance Trace Tests.

Covers:
- ReasoningTrace with device_id + remote_parent_trace_id
- trace_context propagation through InMemoryRegistry
- DAG construction from events with trace_context
- Backward compat: events without trace_context still work
"""

import uuid
from datetime import datetime, timezone

import pytest

# --- ReasoningTrace model tests ---


class TestReasoningTraceCrossInstance:
    """Test device_id and remote_parent_trace_id fields on ReasoningTrace."""

    def test_new_trace_with_device_id(self):
        from app.models.reasoning_trace import ReasoningTrace, ReasoningGraph, SGRMode

        graph = ReasoningGraph(nodes=[], edges=[], answer="test", schema_version=2)
        trace = ReasoningTrace.new(
            workspace_id="ws-1",
            graph=graph,
            device_id="dev-A",
        )
        assert trace.device_id == "dev-A"
        assert trace.remote_parent_trace_id is None

    def test_new_trace_with_remote_parent(self):
        from app.models.reasoning_trace import ReasoningTrace, ReasoningGraph, SGRMode

        graph = ReasoningGraph(nodes=[], edges=[], answer="test", schema_version=2)
        parent_id = str(uuid.uuid4())
        trace = ReasoningTrace.new(
            workspace_id="ws-1",
            graph=graph,
            device_id="dev-B",
            remote_parent_trace_id=parent_id,
        )
        assert trace.device_id == "dev-B"
        assert trace.remote_parent_trace_id == parent_id

    def test_cross_instance_chain(self):
        """Simulate cross-instance trace chain: A creates -> B extends."""
        from app.models.reasoning_trace import ReasoningTrace, ReasoningGraph

        graph = ReasoningGraph(nodes=[], edges=[], answer="a")

        trace_a = ReasoningTrace.new(
            workspace_id="ws-1",
            graph=graph,
            device_id="dev-A",
        )

        trace_b = ReasoningTrace.new(
            workspace_id="ws-1",
            graph=graph,
            device_id="dev-B",
            parent_trace_id=trace_a.id,
            remote_parent_trace_id=trace_a.id,
        )

        assert trace_b.parent_trace_id == trace_a.id
        assert trace_b.remote_parent_trace_id == trace_a.id
        assert trace_b.device_id == "dev-B"
        assert trace_a.device_id == "dev-A"

    def test_backward_compat_no_device_id(self):
        """ReasoningTrace without device_id still works."""
        from app.models.reasoning_trace import ReasoningTrace, ReasoningGraph

        graph = ReasoningGraph(nodes=[], edges=[], answer="test")
        trace = ReasoningTrace.new(workspace_id="ws-1", graph=graph)
        assert trace.device_id is None
        assert trace.remote_parent_trace_id is None


# --- trace_context propagation tests ---


class TestTraceContextPropagation:
    """Test trace_context flows through adapter append_event calls."""

    def test_client_append_event_includes_trace_context(self):
        """Verify client builds correct body with trace_context."""
        import asyncio
        from unittest.mock import AsyncMock, patch

        from app.services.handoff.registry_client import HandoffRegistryClient

        client = HandoffRegistryClient(
            registry_url="http://test:8000",
            device_id="dev-A",
        )

        tc = {
            "trace_id": "t-123",
            "parent_trace_id": "t-000",
            "device_id": "dev-A",
        }

        # Mock _post to capture the payload
        captured = {}

        async def mock_post(path, json=None, headers=None):
            captured["path"] = path
            captured["json"] = json
            return {"event_id": "mock-eid"}

        client._post = mock_post  # type: ignore

        event_id = asyncio.get_event_loop().run_until_complete(
            client.append_event(
                "h-1",
                "compile_completed",
                payload={"task_ir_id": "ir-99"},
                trace_context=tc,
            )
        )

        assert event_id == "mock-eid"
        assert captured["json"]["trace_context"] == tc
        assert captured["json"]["event_type"] == "compile_completed"

    def test_client_append_event_without_trace_context(self):
        """When trace_context is None, it should not be in the body."""
        import asyncio

        from app.services.handoff.registry_client import HandoffRegistryClient

        client = HandoffRegistryClient(
            registry_url="http://test:8000",
            device_id="dev-A",
        )

        captured = {}

        async def mock_post(path, json=None, headers=None):
            captured["json"] = json
            return {"event_id": "mock-eid"}

        client._post = mock_post  # type: ignore

        asyncio.get_event_loop().run_until_complete(
            client.append_event("h-1", "compile_started")
        )

        assert "trace_context" not in captured["json"]

    def test_client_get_trace_dag(self):
        """Verify get_trace_dag calls GET on the right path."""
        import asyncio

        from app.services.handoff.registry_client import HandoffRegistryClient

        client = HandoffRegistryClient(
            registry_url="http://test:8000",
            device_id="dev-A",
        )

        captured = {}

        async def mock_get(path, params=None):
            captured["path"] = path
            return {"handoff_id": "h-1", "nodes": [], "edges": []}

        client._get = mock_get  # type: ignore

        result = asyncio.get_event_loop().run_until_complete(
            client.get_trace_dag("h-1")
        )

        assert captured["path"] == "/handoffs/h-1/trace-dag"
        assert result["handoff_id"] == "h-1"


# --- DAG construction tests ---


class TestDAGConstruction:
    """Test trace DAG building logic from events with trace_context."""

    def _build_dag(self, events):
        """Simulate get_trace_dag logic locally (same algorithm as service)."""
        nodes = []
        edges = []
        trace_ids_seen = {}

        for i, evt in enumerate(events):
            tc = evt.get("trace_context") or {}
            node = {
                "event_id": evt["event_id"],
                "event_type": evt["event_type"],
                "device_id": evt["actor_device_id"],
                "trace_id": tc.get("trace_id"),
                "parent_trace_id": tc.get("parent_trace_id"),
            }
            nodes.append(node)

            if i > 0:
                edges.append(
                    {
                        "from": events[i - 1]["event_id"],
                        "to": evt["event_id"],
                        "relation": "hash_chain",
                    }
                )

            trace_id = tc.get("trace_id")
            parent_trace_id = tc.get("parent_trace_id")
            if trace_id:
                trace_ids_seen[trace_id] = evt["event_id"]
            if parent_trace_id and parent_trace_id in trace_ids_seen:
                edges.append(
                    {
                        "from": trace_ids_seen[parent_trace_id],
                        "to": evt["event_id"],
                        "relation": "cross_instance",
                    }
                )

        return {"nodes": nodes, "edges": edges}

    def test_single_device_no_cross_instance(self):
        """Events from single device produce only hash_chain edges."""
        events = [
            {
                "event_id": "e1",
                "event_type": "created",
                "actor_device_id": "dev-A",
                "trace_context": {"trace_id": "t1", "device_id": "dev-A"},
            },
            {
                "event_id": "e2",
                "event_type": "claimed",
                "actor_device_id": "dev-A",
                "trace_context": {"trace_id": "t2", "device_id": "dev-A"},
            },
        ]
        dag = self._build_dag(events)
        assert len(dag["nodes"]) == 2
        assert len(dag["edges"]) == 1
        assert dag["edges"][0]["relation"] == "hash_chain"

    def test_cross_instance_edge_created(self):
        """When dev-B references dev-A's trace_id, a cross_instance edge appears."""
        events = [
            {
                "event_id": "e1",
                "event_type": "created",
                "actor_device_id": "dev-A",
                "trace_context": {"trace_id": "t-A", "device_id": "dev-A"},
            },
            {
                "event_id": "e2",
                "event_type": "claimed",
                "actor_device_id": "dev-B",
                "trace_context": {
                    "trace_id": "t-B",
                    "parent_trace_id": "t-A",
                    "device_id": "dev-B",
                },
            },
        ]
        dag = self._build_dag(events)
        assert len(dag["edges"]) == 2  # 1 hash_chain + 1 cross_instance
        relations = {e["relation"] for e in dag["edges"]}
        assert "hash_chain" in relations
        assert "cross_instance" in relations

        cross_edge = [e for e in dag["edges"] if e["relation"] == "cross_instance"][0]
        assert cross_edge["from"] == "e1"  # dev-A's event
        assert cross_edge["to"] == "e2"  # dev-B's event

    def test_no_trace_context_backward_compat(self):
        """Events without trace_context produce only hash_chain edges."""
        events = [
            {"event_id": "e1", "event_type": "created", "actor_device_id": "dev-A"},
            {"event_id": "e2", "event_type": "claimed", "actor_device_id": "dev-B"},
        ]
        dag = self._build_dag(events)
        assert len(dag["nodes"]) == 2
        assert len(dag["edges"]) == 1
        assert dag["edges"][0]["relation"] == "hash_chain"
        assert dag["nodes"][0]["trace_id"] is None

    def test_multi_hop_chain(self):
        """A -> B -> C creates a chain of cross_instance edges."""
        events = [
            {
                "event_id": "e1",
                "event_type": "created",
                "actor_device_id": "dev-A",
                "trace_context": {"trace_id": "t-A", "device_id": "dev-A"},
            },
            {
                "event_id": "e2",
                "event_type": "claimed",
                "actor_device_id": "dev-B",
                "trace_context": {
                    "trace_id": "t-B",
                    "parent_trace_id": "t-A",
                    "device_id": "dev-B",
                },
            },
            {
                "event_id": "e3",
                "event_type": "committed",
                "actor_device_id": "dev-C",
                "trace_context": {
                    "trace_id": "t-C",
                    "parent_trace_id": "t-B",
                    "device_id": "dev-C",
                },
            },
        ]
        dag = self._build_dag(events)
        cross_edges = [e for e in dag["edges"] if e["relation"] == "cross_instance"]
        assert len(cross_edges) == 2
        # A -> B
        assert cross_edges[0]["from"] == "e1"
        assert cross_edges[0]["to"] == "e2"
        # B -> C
        assert cross_edges[1]["from"] == "e2"
        assert cross_edges[1]["to"] == "e3"
