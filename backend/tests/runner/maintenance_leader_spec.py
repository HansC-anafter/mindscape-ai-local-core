import pytest

from backend.app.runner.maintenance_leader import (
    MAINTENANCE_LEADER_KEY,
    maintenance_owner_id,
    resolve_maintenance_lease_seconds,
    try_hold_maintenance_leadership,
)


class _FakeQueue:
    def __init__(self, owner=None, *, fail=False):
        self.owner = owner
        self.fail = fail
        self.acquire_calls = []
        self.renew_calls = []

    async def acquire_lock(self, key, owner_id, ttl_seconds):
        self.acquire_calls.append((key, owner_id, ttl_seconds))
        if self.fail:
            raise RuntimeError("redis unavailable")
        if self.owner is None:
            self.owner = owner_id
            return True
        return False

    async def get_lock_owner(self, key):
        assert key == MAINTENANCE_LEADER_KEY
        return self.owner

    async def renew_lock(self, key, owner_id, ttl_seconds):
        self.renew_calls.append((key, owner_id, ttl_seconds))
        current = (
            self.owner.decode("utf-8")
            if isinstance(self.owner, bytes)
            else self.owner
        )
        return current == owner_id


def test_maintenance_lease_has_three_interval_and_floor_contract():
    assert resolve_maintenance_lease_seconds(1) == 180
    assert resolve_maintenance_lease_seconds(60) == 180
    assert resolve_maintenance_lease_seconds(120) == 360


@pytest.mark.asyncio
async def test_first_runner_acquires_maintenance_leadership():
    queue = _FakeQueue()

    held = await try_hold_maintenance_leadership(
        queue,
        runner_id="runner-a",
        ttl_seconds=180,
    )

    assert held is True
    assert queue.owner == maintenance_owner_id("runner-a")
    assert queue.renew_calls == []


@pytest.mark.asyncio
async def test_same_runner_renews_and_foreign_runner_skips():
    owner = maintenance_owner_id("runner-a")
    queue = _FakeQueue(owner.encode("utf-8"))

    assert await try_hold_maintenance_leadership(
        queue,
        runner_id="runner-a",
        ttl_seconds=180,
    )
    assert queue.renew_calls == [(MAINTENANCE_LEADER_KEY, owner, 180)]

    queue.renew_calls.clear()
    assert not await try_hold_maintenance_leadership(
        queue,
        runner_id="runner-b",
        ttl_seconds=180,
    )
    assert queue.renew_calls == []


@pytest.mark.asyncio
async def test_redis_uncertainty_fails_closed():
    queue = _FakeQueue(fail=True)

    assert not await try_hold_maintenance_leadership(
        queue,
        runner_id="runner-a",
        ttl_seconds=1,
    )
    assert queue.acquire_calls[0][2] == 180
