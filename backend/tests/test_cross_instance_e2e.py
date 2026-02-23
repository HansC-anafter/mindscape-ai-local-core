"""
Phase 5.1 — Cross-Instance E2E Test.

Simulates two local-core devices (A and B) communicating through
an in-memory Registry (simulating site-hub). Covers:
  - Full handoff lifecycle with trace_context propagation
  - Signed bundle roundtrip (create + verify)
  - Offline queue replay
  - Concurrent claim conflict (only one succeeds)
  - DAG integrity after cross-instance lifecycle
"""

import hashlib
import json
import os
import sys
import uuid
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pytest

# --- Direct import to avoid app-level import chain ---

import importlib.util

_test_dir = os.path.dirname(os.path.abspath(__file__))
_backend_root = os.path.dirname(_test_dir)
_handoff_dir = os.path.join(_backend_root, "app", "services", "handoff")

_client_spec = importlib.util.spec_from_file_location(
    "registry_client",
    os.path.join(_handoff_dir, "registry_client.py"),
)
_client_mod = importlib.util.module_from_spec(_client_spec)
_client_spec.loader.exec_module(_client_mod)

HandoffRegistryClient = _client_mod.HandoffRegistryClient
RegistryUnavailable = _client_mod.RegistryUnavailable


# --- Extended In-Memory Registry with trace_context ---


class InMemoryRegistryV2:
    """In-memory Registry with trace_context support for cross-instance E2E."""

    def __init__(self):
        self.handoffs: Dict[str, Dict] = {}
        self.events: Dict[str, List[Dict]] = {}
        self._lock = threading.Lock()
        self._valid_transitions = {
            "created": ["claimed", "cancelled"],
            "claimed": ["committed", "cancelled"],
            "committed": ["dispatched", "cancelled"],
            "dispatched": ["completed", "failed"],
            "failed": ["claimed"],
        }

    def create(
        self,
        handoff_id: str,
        tenant_id: str,
        payload: Dict,
        source_device_id: str,
        target_device_id: Optional[str] = None,
    ) -> Dict:
        self.handoffs[handoff_id] = {
            "id": handoff_id,
            "tenant_id": tenant_id,
            "spec_version": "0.1",
            "state": "created",
            "payload_json": payload,
            "source_device_id": source_device_id,
            "target_device_id": target_device_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self.events[handoff_id] = []
        self._append_event(handoff_id, "created", source_device_id, payload)
        return {"handoff_id": handoff_id, "state": "created"}

    def transition(
        self,
        handoff_id: str,
        target_state: str,
        actor_device_id: str,
        payload: Optional[Dict] = None,
    ) -> Dict:
        with self._lock:
            h = self.handoffs[handoff_id]
            current = h["state"]
            allowed = self._valid_transitions.get(current, [])
            if target_state not in allowed:
                raise ValueError(f"Invalid: {current} -> {target_state}")
            prev_state = current
            h["state"] = target_state
            self._append_event(handoff_id, target_state, actor_device_id, payload or {})
        return {"previous_state": prev_state, "new_state": target_state}

    def append_event(
        self,
        handoff_id: str,
        event_type: str,
        actor_device_id: str,
        payload: Optional[Dict] = None,
        trace_context: Optional[Dict] = None,
    ) -> str:
        event_id = self._append_event(
            handoff_id,
            event_type,
            actor_device_id,
            payload or {},
            trace_context=trace_context,
        )
        return event_id

    def get_timeline(self, handoff_id: str) -> Dict:
        events = self.events.get(handoff_id, [])
        return {
            "handoff_id": handoff_id,
            "events": events,
            "count": len(events),
            "chain_valid": self._verify_chain(events),
        }

    def get_trace_dag(self, handoff_id: str) -> Dict:
        events = self.events.get(handoff_id, [])
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

        return {
            "handoff_id": handoff_id,
            "nodes": nodes,
            "edges": edges,
            "node_count": len(nodes),
            "edge_count": len(edges),
        }

    def list_pending(self, device_id: str) -> List[Dict]:
        return [
            h
            for h in self.handoffs.values()
            if h.get("target_device_id") == device_id and h["state"] == "created"
        ]

    # --- internals ---

    def _compute_payload_hash(self, payload):
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()

    def _compute_chain_hash(self, prev_event_id, prev_payload_hash):
        combined = f"{prev_event_id}{prev_payload_hash}"
        return hashlib.sha256(combined.encode()).hexdigest()

    def _append_event(
        self,
        handoff_id,
        event_type,
        actor_device_id,
        payload,
        trace_context=None,
    ) -> str:
        events = self.events[handoff_id]
        event_id = str(uuid.uuid4())
        payload_hash = self._compute_payload_hash(payload)

        if events:
            prev = events[-1]
            prev_event_hash = self._compute_chain_hash(
                prev["event_id"], prev["payload_hash"]
            )
        else:
            prev_event_hash = "0" * 64

        evt = {
            "event_id": event_id,
            "handoff_id": handoff_id,
            "event_type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "actor_device_id": actor_device_id,
            "payload_hash": payload_hash,
            "prev_event_hash": prev_event_hash,
            "payload_json": payload,
        }
        if trace_context:
            evt["trace_context"] = trace_context
        events.append(evt)
        return event_id

    def _verify_chain(self, events):
        for i, evt in enumerate(events):
            if i == 0:
                if evt["prev_event_hash"] != "0" * 64:
                    return False
            else:
                prev = events[i - 1]
                expected = self._compute_chain_hash(
                    prev["event_id"], prev["payload_hash"]
                )
                if evt["prev_event_hash"] != expected:
                    return False
        return True


# =================================================================
#  Test 1: Full cross-instance lifecycle with trace_context
# =================================================================


class TestCrossInstanceLifecycle:
    """A creates -> B claims -> compiles -> commits -> completes.
    Each step carries trace_context. Verifies DAG has cross-instance edges."""

    def setup_method(self):
        self.registry = InMemoryRegistryV2()
        self.handoff_id = str(uuid.uuid4())
        self.device_a = "dev-A"
        self.device_b = "dev-B"

    def test_full_lifecycle_with_trace(self):
        # A creates handoff
        self.registry.create(
            self.handoff_id,
            "tenant-1",
            {"intent": "build landing page", "goals": ["responsive", "dark mode"]},
            self.device_a,
            self.device_b,
        )

        # A appends an event with trace_context
        trace_a = str(uuid.uuid4())
        self.registry.append_event(
            self.handoff_id,
            "handoff_published",
            self.device_a,
            payload={"source": "meeting engine"},
            trace_context={"trace_id": trace_a, "device_id": self.device_a},
        )

        # B claims
        self.registry.transition(self.handoff_id, "claimed", self.device_b)

        # B compiles and appends with trace_context linking to A
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

        # B commits
        self.registry.transition(
            self.handoff_id,
            "committed",
            self.device_b,
            {"accepted": True, "task_ir_id": "ir-001"},
        )

        # B dispatches and completes
        self.registry.transition(self.handoff_id, "dispatched", self.device_b)
        self.registry.transition(
            self.handoff_id,
            "completed",
            self.device_b,
            {"output": "done"},
        )

        # Verify timeline integrity
        timeline = self.registry.get_timeline(self.handoff_id)
        assert timeline["chain_valid"] is True
        # created + handoff_published + claimed + compile_started +
        # compile_completed + committed + dispatched + completed = 8
        assert timeline["count"] == 8

        # Verify DAG
        dag = self.registry.get_trace_dag(self.handoff_id)
        assert dag["node_count"] == 8

        cross_edges = [e for e in dag["edges"] if e["relation"] == "cross_instance"]
        assert len(cross_edges) >= 1, "Expected at least 1 cross-instance edge"

        # The cross-instance edge should link A's event to B's event
        for edge in cross_edges:
            from_node = next(n for n in dag["nodes"] if n["event_id"] == edge["from"])
            to_node = next(n for n in dag["nodes"] if n["event_id"] == edge["to"])
            assert from_node["device_id"] == self.device_a
            assert to_node["device_id"] == self.device_b


# =================================================================
#  Test 2: Signed bundle roundtrip
# =================================================================


class TestSignedBundleRoundtrip:
    """Create, sign, transport, verify, extract — full bundle lifecycle."""

    def test_handoff_bundle_create_verify(self):
        from app.models.handoff import HandoffIn
        from app.models.signed_bundle import SignedHandoffBundle

        handoff_in = HandoffIn(
            handoff_id=str(uuid.uuid4()),
            workspace_id="ws-1",
            intent_summary="Build landing page",
            goals=["responsive design", "dark mode"],
            source_device_id="dev-A",
            target_device_id="dev-B",
        )

        # A creates signed bundle
        secret = "test-shared-secret-key"
        bundle = SignedHandoffBundle.create(
            payload_type="handoff_in",
            payload=handoff_in.model_dump(mode="json"),
            source_device_id="dev-A",
            secret_key=secret,
            target_device_id="dev-B",
        )

        # Verify integrity fields
        assert bundle.payload_type == "handoff_in"
        assert bundle.source_device_id == "dev-A"
        assert bundle.target_device_id == "dev-B"
        assert len(bundle.content_hash) == 64
        assert len(bundle.signature) == 64

        # B verifies
        assert bundle.verify(secret) is True

        # Tamper detection
        bundle_copy = bundle.model_copy(deep=True)
        bundle_copy.payload["intent_summary"] = "TAMPERED"
        assert bundle_copy.verify(secret) is False

        # Wrong secret detection
        assert bundle.verify("wrong-secret") is False

    def test_commitment_bundle_roundtrip(self):
        from app.models.handoff import Commitment
        from app.models.signed_bundle import SignedHandoffBundle

        commitment = Commitment(
            commitment_id=str(uuid.uuid4()),
            handoff_id=str(uuid.uuid4()),
            accepted=True,
            scope_summary="Will deliver responsive landing page",
            task_ir_id="ir-001",
        )

        secret = "test-secret"
        bundle = SignedHandoffBundle.create(
            payload_type="commitment",
            payload=commitment.model_dump(mode="json"),
            source_device_id="dev-B",
            secret_key=secret,
            target_device_id="dev-A",
        )

        assert bundle.verify(secret) is True
        assert bundle.payload_type == "commitment"
        assert bundle.payload["accepted"] is True


# =================================================================
#  Test 3: Offline queue replay
# =================================================================


class TestOfflineQueueReplay:
    """Events queued offline are replayed in order when back online."""

    def test_offline_events_preserved_order(self):
        registry = InMemoryRegistryV2()
        hid = str(uuid.uuid4())
        registry.create(hid, "t1", {"intent": "offline test"}, "d-A", "d-B")
        registry.transition(hid, "claimed", "d-B")

        # Simulate offline: queue events locally
        offline_queue = []
        for i in range(5):
            offline_queue.append(
                {
                    "event_type": f"checkpoint_{i}",
                    "actor_device_id": "d-B",
                    "payload": {"step": i},
                    "trace_context": {"trace_id": f"t-{i}", "device_id": "d-B"},
                }
            )

        # Reconnect: flush queue to registry
        for evt in offline_queue:
            registry.append_event(
                hid,
                evt["event_type"],
                evt["actor_device_id"],
                payload=evt["payload"],
                trace_context=evt["trace_context"],
            )

        timeline = registry.get_timeline(hid)
        # created + claimed + 5 checkpoints = 7
        assert timeline["count"] == 7
        assert timeline["chain_valid"] is True

        # Verify order preserved
        event_types = [e["event_type"] for e in timeline["events"]]
        assert event_types[2:] == [f"checkpoint_{i}" for i in range(5)]


# =================================================================
#  Test 4: Concurrent claims (only one succeeds)
# =================================================================


class TestConcurrentClaims:
    """Two devices try to claim the same handoff. Only one succeeds."""

    def test_only_first_claim_succeeds(self):
        registry = InMemoryRegistryV2()
        hid = str(uuid.uuid4())
        registry.create(hid, "t1", {"intent": "contested"}, "d-A")

        # First claim succeeds
        result = registry.transition(hid, "claimed", "d-B")
        assert result["new_state"] == "claimed"

        # Second claim fails (already claimed, not in valid transitions)
        with pytest.raises(ValueError, match="Invalid"):
            registry.transition(hid, "claimed", "d-C")

    def test_claim_after_fail_allows_different_device(self):
        """After failure, a different device can re-claim."""
        registry = InMemoryRegistryV2()
        hid = str(uuid.uuid4())
        registry.create(hid, "t1", {}, "d-A")

        # B claims, commits, dispatches, fails
        registry.transition(hid, "claimed", "d-B")
        registry.transition(hid, "committed", "d-B")
        registry.transition(hid, "dispatched", "d-B")
        registry.transition(hid, "failed", "d-B", {"reason": "runtime error"})

        # C re-claims
        result = registry.transition(hid, "claimed", "d-C")
        assert result["previous_state"] == "failed"
        assert result["new_state"] == "claimed"


# =================================================================
#  Test 5: DAG integrity after full cross-instance lifecycle
# =================================================================


class TestDAGIntegrity:
    """Hash chain + DAG edges are consistent after multi-device lifecycle."""

    def test_dag_edges_correct_after_full_lifecycle(self):
        registry = InMemoryRegistryV2()
        hid = str(uuid.uuid4())
        trace_a = str(uuid.uuid4())
        trace_b = str(uuid.uuid4())

        # A creates
        registry.create(hid, "t1", {"intent": "dag test"}, "d-A", "d-B")

        # A publishes with trace
        registry.append_event(
            hid,
            "published",
            "d-A",
            trace_context={"trace_id": trace_a, "device_id": "d-A"},
        )

        # B claims + compiles with cross-instance link
        registry.transition(hid, "claimed", "d-B")
        registry.append_event(
            hid,
            "compile_completed",
            "d-B",
            payload={"task_ir_id": "ir-1"},
            trace_context={
                "trace_id": trace_b,
                "parent_trace_id": trace_a,
                "device_id": "d-B",
            },
        )

        # B commits and completes
        registry.transition(hid, "committed", "d-B")
        registry.transition(hid, "dispatched", "d-B")
        registry.transition(hid, "completed", "d-B", {"output": "done"})

        # Verify hash chain
        timeline = registry.get_timeline(hid)
        assert timeline["chain_valid"] is True

        # Verify DAG structure
        dag = registry.get_trace_dag(hid)
        hash_edges = [e for e in dag["edges"] if e["relation"] == "hash_chain"]
        cross_edges = [e for e in dag["edges"] if e["relation"] == "cross_instance"]

        # 7 events → 6 hash_chain edges
        assert len(hash_edges) == dag["node_count"] - 1
        # At least 1 cross-instance edge (A→B via trace)
        assert len(cross_edges) >= 1

        # Verify no duplicate edges
        edge_keys = [(e["from"], e["to"], e["relation"]) for e in dag["edges"]]
        assert len(edge_keys) == len(set(edge_keys)), "Duplicate edges found"

    def test_tampered_chain_detected_in_cross_instance(self):
        """Tampering with any event in the chain is detected."""
        registry = InMemoryRegistryV2()
        hid = str(uuid.uuid4())
        registry.create(hid, "t1", {}, "d-A", "d-B")
        registry.transition(hid, "claimed", "d-B")
        registry.append_event(
            hid,
            "compile_completed",
            "d-B",
            trace_context={"trace_id": "t-B", "device_id": "d-B"},
        )
        registry.transition(hid, "committed", "d-B")

        # Tamper with middle event
        registry.events[hid][1]["payload_hash"] = "tampered"

        timeline = registry.get_timeline(hid)
        assert timeline["chain_valid"] is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
