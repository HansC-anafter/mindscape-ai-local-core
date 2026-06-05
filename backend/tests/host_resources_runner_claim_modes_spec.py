import pytest

from backend.app.services.host_resources.runner_claim_modes import (
    get_runner_claim_control_sync,
    runner_claim_mode_key,
    runner_claims_enabled,
    set_runner_claim_mode_sync,
)


class _FakeCache:
    def __init__(self):
        self.values = {}
        self.deleted = []

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value, ttl=None):
        self.values[key] = value
        return True

    def delete(self, key):
        self.deleted.append(key)
        self.values.pop(key, None)
        return True


def test_runner_claim_mode_drain_payload_blocks_claims():
    cache = _FakeCache()

    control = set_runner_claim_mode_sync(
        "runner-a",
        "drain",
        reason="test_drain",
        updated_by="operator",
        ttl_seconds=10,
        cache_service=cache,
    )

    assert control.mode == "drain"
    assert control.claim_enabled is False
    assert runner_claims_enabled(control) is False
    assert control.ttl_seconds == 30
    assert runner_claim_mode_key("runner-a") in cache.values

    loaded = get_runner_claim_control_sync("runner-a", cache_service=cache)
    assert loaded.mode == "drain"
    assert loaded.reason == "test_drain"


def test_runner_claim_mode_active_clears_override():
    cache = _FakeCache()
    set_runner_claim_mode_sync("runner-a", "drain", cache_service=cache)

    control = set_runner_claim_mode_sync(
        "runner-a",
        "active",
        cache_service=cache,
    )

    assert control.mode == "active"
    assert control.claim_enabled is True
    assert runner_claims_enabled(control) is True
    assert runner_claim_mode_key("runner-a") not in cache.values
    assert cache.deleted == [runner_claim_mode_key("runner-a")]


def test_runner_claim_mode_rejects_invalid_mode():
    with pytest.raises(ValueError):
        set_runner_claim_mode_sync("runner-a", "unknown", cache_service=_FakeCache())
