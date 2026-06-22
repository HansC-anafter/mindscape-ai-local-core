"""Offline replay and concurrent claim tests for cross-instance handoffs."""

import uuid

import pytest

from cross_instance_e2e_test_support import InMemoryRegistryV2


class TestOfflineQueueReplay:
    """Events collected while offline are replayed in order when reconnected."""

    def test_offline_events_preserved_order(self) -> None:
        registry = InMemoryRegistryV2()
        handoff_id = str(uuid.uuid4())
        registry.create(handoff_id, "t1", {"intent": "offline test"}, "d-A", "d-B")
        registry.transition(handoff_id, "claimed", "d-B")

        offline_queue = []
        for index in range(5):
            offline_queue.append(
                {
                    "event_type": f"checkpoint_{index}",
                    "actor_device_id": "d-B",
                    "payload": {"step": index},
                    "trace_context": {"trace_id": f"t-{index}", "device_id": "d-B"},
                }
            )

        for event in offline_queue:
            registry.append_event(
                handoff_id,
                event["event_type"],
                event["actor_device_id"],
                payload=event["payload"],
                trace_context=event["trace_context"],
            )

        timeline = registry.get_timeline(handoff_id)
        assert timeline["count"] == 7
        assert timeline["chain_valid"] is True

        event_types = [event["event_type"] for event in timeline["events"]]
        assert event_types[2:] == [f"checkpoint_{index}" for index in range(5)]


class TestConcurrentClaims:
    """Two devices trying to claim the same handoff leave only one winner."""

    def test_only_first_claim_succeeds(self) -> None:
        registry = InMemoryRegistryV2()
        handoff_id = str(uuid.uuid4())
        registry.create(handoff_id, "t1", {"intent": "contested"}, "d-A")

        result = registry.transition(handoff_id, "claimed", "d-B")
        assert result["new_state"] == "claimed"

        with pytest.raises(ValueError, match="Invalid"):
            registry.transition(handoff_id, "claimed", "d-C")

    def test_claim_after_fail_allows_different_device(self) -> None:
        registry = InMemoryRegistryV2()
        handoff_id = str(uuid.uuid4())
        registry.create(handoff_id, "t1", {}, "d-A")

        registry.transition(handoff_id, "claimed", "d-B")
        registry.transition(handoff_id, "committed", "d-B")
        registry.transition(handoff_id, "dispatched", "d-B")
        registry.transition(handoff_id, "failed", "d-B", {"reason": "runtime error"})

        result = registry.transition(handoff_id, "claimed", "d-C")
        assert result["previous_state"] == "failed"
        assert result["new_state"] == "claimed"
