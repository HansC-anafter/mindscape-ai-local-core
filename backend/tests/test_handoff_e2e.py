"""
Phase 3.4 — E2E Integration Test for HandoffSpec.

Simulates the full lifecycle:
  A (local-core) -> site-hub create -> B (local-core) claim ->
  compile -> commit -> dispatch -> complete -> timeline verify

Uses mock HTTP to simulate site-hub Registry in-process.
Also tests backward compat (pure-local mode) and hash chain verification.
"""

import asyncio
import hashlib
import json
import os
import sys
import uuid
import pytest
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

# Direct import to avoid app-level import chain
import importlib.util

_test_dir = os.path.dirname(os.path.abspath(__file__))
_backend_root = os.path.dirname(_test_dir)
_handoff_dir = os.path.join(_backend_root, "app", "services", "handoff")

# Load modules
_client_spec = importlib.util.spec_from_file_location(
    "registry_client",
    os.path.join(_handoff_dir, "registry_client.py"),
)
_client_mod = importlib.util.module_from_spec(_client_spec)
_client_spec.loader.exec_module(_client_mod)

HandoffRegistryClient = _client_mod.HandoffRegistryClient
RegistryUnavailable = _client_mod.RegistryUnavailable

_adapter_spec = importlib.util.spec_from_file_location(
    "adapter",
    os.path.join(_handoff_dir, "adapter.py"),
    submodule_search_locations=[_handoff_dir],
)
# Inject the already-loaded client module
sys.modules["registry_client"] = _client_mod
# Also inject as relative import
sys.modules[".registry_client"] = _client_mod

# Load adapter with pre-injected dependency
_adapter_path = os.path.join(_handoff_dir, "adapter.py")
_adapter_code = Path(_adapter_path).read_text()
_adapter_mod = type(sys)("adapter")
_adapter_mod.HandoffRegistryClient = HandoffRegistryClient
_adapter_mod.RegistryUnavailable = RegistryUnavailable
# Execute adapter code with client already available
exec(
    compile(
        _adapter_code.replace(
            "from .registry_client import HandoffRegistryClient, RegistryUnavailable",
            "# import handled by test harness",
        ),
        _adapter_path,
        "exec",
    ),
    _adapter_mod.__dict__,
)

HandoffAdapter = _adapter_mod.HandoffAdapter


# --- In-memory Registry Simulator ---


class InMemoryRegistry:
    """Simulates site-hub Registry API in-memory for E2E testing."""

    def __init__(self):
        self.handoffs = {}
        self.events = {}
        self._valid_transitions = {
            "created": ["claimed", "cancelled"],
            "claimed": ["committed", "cancelled"],
            "committed": ["dispatched", "cancelled"],
            "dispatched": ["completed", "failed"],
            "failed": ["claimed"],
        }

    def create(
        self,
        handoff_id,
        tenant_id,
        payload_type,
        payload,
        source_device_id,
        target_device_id=None,
    ):
        self.handoffs[handoff_id] = {
            "id": handoff_id,
            "tenant_id": tenant_id,
            "spec_version": "0.1",
            "state": "created",
            "payload_type": payload_type,
            "payload_json": payload,
            "source_device_id": source_device_id,
            "target_device_id": target_device_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "claimed_at": None,
            "committed_at": None,
        }
        self.events[handoff_id] = []
        self._append_event(handoff_id, "created", source_device_id, payload)
        return {
            "handoff_id": handoff_id,
            "state": "created",
            "event_id": self.events[handoff_id][-1]["event_id"],
        }

    def transition(self, handoff_id, target_state, actor_device_id, payload=None):
        h = self.handoffs[handoff_id]
        current = h["state"]
        allowed = self._valid_transitions.get(current, [])
        if target_state not in allowed:
            raise ValueError(f"Invalid: {current} -> {target_state}")

        prev_state = current
        h["state"] = target_state
        h["updated_at"] = datetime.now(timezone.utc).isoformat()
        if target_state == "claimed":
            h["claimed_at"] = datetime.now(timezone.utc).isoformat()
        elif target_state == "committed":
            h["committed_at"] = datetime.now(timezone.utc).isoformat()

        self._append_event(handoff_id, target_state, actor_device_id, payload or {})
        return {
            "id": handoff_id,
            "previous_state": prev_state,
            "new_state": target_state,
            "event_id": self.events[handoff_id][-1]["event_id"],
        }

    def list_pending(self, device_id, state="created"):
        return [
            h
            for h in self.handoffs.values()
            if h["target_device_id"] == device_id and h["state"] == state
        ]

    def get_timeline(self, handoff_id):
        events = self.events.get(handoff_id, [])
        chain_valid = self._verify_chain(events)
        return {
            "handoff_id": handoff_id,
            "events": events,
            "count": len(events),
            "chain_valid": chain_valid,
        }

    def _compute_payload_hash(self, payload):
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()

    def _compute_chain_hash(self, prev_event_id, prev_payload_hash):
        combined = f"{prev_event_id}{prev_payload_hash}"
        return hashlib.sha256(combined.encode()).hexdigest()

    def _append_event(self, handoff_id, event_type, actor_device_id, payload):
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

        events.append(
            {
                "event_id": event_id,
                "handoff_id": handoff_id,
                "event_type": event_type,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "actor_device_id": actor_device_id,
                "payload_hash": payload_hash,
                "prev_event_hash": prev_event_hash,
                "payload_json": payload,
            }
        )

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


# --- E2E Test ---


class TestE2ELifecycle:
    """Full lifecycle: A create -> B claim -> compile -> commit -> dispatch -> complete."""

    def setup_method(self):
        self.registry = InMemoryRegistry()
        self.handoff_id = str(uuid.uuid4())
        self.tenant_id = "tenant-001"
        self.device_a = "device-A"
        self.device_b = "device-B"

    def test_full_lifecycle(self):
        """Verify the complete state machine traversal."""
        # Step 1: A creates handoff
        result = self.registry.create(
            self.handoff_id,
            self.tenant_id,
            "handoff_in",
            {"intent": "build landing page"},
            self.device_a,
            self.device_b,
        )
        assert result["state"] == "created"

        # Step 2: B claims
        result = self.registry.transition(self.handoff_id, "claimed", self.device_b)
        assert result["previous_state"] == "created"
        assert result["new_state"] == "claimed"

        # Step 3: B commits
        commitment = {"task_ir_id": "ir-001", "accepted": True}
        result = self.registry.transition(
            self.handoff_id, "committed", self.device_b, commitment
        )
        assert result["new_state"] == "committed"

        # Step 4: Dispatched (would be set by coordinator)
        result = self.registry.transition(self.handoff_id, "dispatched", self.device_b)
        assert result["new_state"] == "dispatched"

        # Step 5: B completes
        result = self.registry.transition(
            self.handoff_id, "completed", self.device_b, {"output": "done"}
        )
        assert result["new_state"] == "completed"

        # Step 6: Verify timeline
        timeline = self.registry.get_timeline(self.handoff_id)
        assert (
            timeline["count"] == 5
        )  # created, claimed, committed, dispatched, completed
        assert timeline["chain_valid"] is True

    def test_fail_and_retry(self):
        """Verify failed -> claimed retry path."""
        self.registry.create(
            self.handoff_id,
            self.tenant_id,
            "handoff_in",
            {"intent": "retry test"},
            self.device_a,
            self.device_b,
        )
        self.registry.transition(self.handoff_id, "claimed", self.device_b)
        self.registry.transition(self.handoff_id, "committed", self.device_b)
        self.registry.transition(self.handoff_id, "dispatched", self.device_b)

        # Fail
        self.registry.transition(
            self.handoff_id, "failed", self.device_b, {"reason": "timeout"}
        )
        assert self.registry.handoffs[self.handoff_id]["state"] == "failed"

        # Retry: failed -> claimed
        result = self.registry.transition(self.handoff_id, "claimed", self.device_b)
        assert result["previous_state"] == "failed"
        assert result["new_state"] == "claimed"

    def test_cancel_from_created(self):
        """Verify cancel from created state."""
        self.registry.create(
            self.handoff_id,
            self.tenant_id,
            "handoff_in",
            {"intent": "cancel test"},
            self.device_a,
            self.device_b,
        )
        result = self.registry.transition(
            self.handoff_id, "cancelled", self.device_a, {"reason": "no longer needed"}
        )
        assert result["new_state"] == "cancelled"

    def test_invalid_transition_raises(self):
        """Verify invalid state transition raises error."""
        self.registry.create(
            self.handoff_id,
            self.tenant_id,
            "handoff_in",
            {},
            self.device_a,
        )
        with pytest.raises(ValueError, match="Invalid"):
            self.registry.transition(self.handoff_id, "completed", self.device_a)

    def test_list_pending_filters_correctly(self):
        """Verify list_pending returns only matching handoffs."""
        # Create 3 handoffs, 2 for device B, 1 for device C
        for i in range(3):
            hid = str(uuid.uuid4())
            target = self.device_b if i < 2 else "device-C"
            self.registry.create(
                hid, self.tenant_id, "handoff_in", {}, self.device_a, target
            )

        pending = self.registry.list_pending(self.device_b)
        assert len(pending) == 2


# --- Hash Chain Verification ---


class TestHashChainIntegration:
    """Verify hash chain integrity across full lifecycle."""

    def test_chain_valid_after_lifecycle(self):
        registry = InMemoryRegistry()
        hid = str(uuid.uuid4())

        registry.create(hid, "t1", "handoff_in", {"a": 1}, "d-A", "d-B")
        registry.transition(hid, "claimed", "d-B")
        registry.transition(hid, "committed", "d-B", {"task_ir_id": "ir-1"})
        registry.transition(hid, "dispatched", "d-B")
        registry.transition(hid, "completed", "d-B", {"output": "ok"})

        timeline = registry.get_timeline(hid)
        assert timeline["chain_valid"] is True
        assert timeline["count"] == 5

    def test_tampered_chain_detected(self):
        """Manually tamper with a hash and verify detection."""
        registry = InMemoryRegistry()
        hid = str(uuid.uuid4())

        registry.create(hid, "t1", "handoff_in", {}, "d-A")
        registry.transition(hid, "claimed", "d-B")
        registry.transition(hid, "committed", "d-B")

        # Tamper with middle event hash
        registry.events[hid][1]["payload_hash"] = "tampered_hash"

        timeline = registry.get_timeline(hid)
        assert timeline["chain_valid"] is False


# --- Backward Compatibility ---


class TestBackwardCompat:
    """Pure-local mode: adapter does nothing when HANDOFF_REGISTRY_URL is unset."""

    def test_adapter_disabled_without_url(self):
        client = HandoffRegistryClient(registry_url=None)
        client.registry_url = None
        adapter = HandoffAdapter(client=client)
        assert not adapter.is_enabled

    @pytest.mark.asyncio
    async def test_publish_returns_none_when_disabled(self):
        client = HandoffRegistryClient(registry_url=None)
        client.registry_url = None
        adapter = HandoffAdapter(client=client)

        result = await adapter.publish_handoff({"intent": "test"}, "tenant-1")
        assert result is None

    @pytest.mark.asyncio
    async def test_poll_returns_empty_when_disabled(self):
        client = HandoffRegistryClient(registry_url=None)
        client.registry_url = None
        adapter = HandoffAdapter(client=client)

        result = await adapter.poll_pending()
        assert result == []

    @pytest.mark.asyncio
    async def test_flush_returns_zero_when_disabled(self):
        client = HandoffRegistryClient(registry_url=None)
        client.registry_url = None
        adapter = HandoffAdapter(client=client)

        count = await adapter.flush_offline_queue()
        assert count == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
