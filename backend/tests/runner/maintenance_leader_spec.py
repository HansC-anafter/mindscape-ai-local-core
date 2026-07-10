import pytest

from backend.app.runner.maintenance_leader import (
    MAINTENANCE_LEADER_KEY,
    maintenance_owner_id,
    partition_maintenance_leader_key,
    partition_maintenance_owner_id,
    resolve_maintenance_lease_seconds,
    try_hold_maintenance_leadership,
    try_hold_partition_maintenance_leadership,
)


class _FakeQueue:
    def __init__(self, owner=None, *, fail=False):
        self.owners = {}
        if owner is not None:
            self.owners[MAINTENANCE_LEADER_KEY] = owner
        self.fail = fail
        self.acquire_calls = []
        self.renew_calls = []

    async def acquire_lock(self, key, owner_id, ttl_seconds):
        self.acquire_calls.append((key, owner_id, ttl_seconds))
        if self.fail:
            raise RuntimeError("redis unavailable")
        if key not in self.owners:
            self.owners[key] = owner_id
            return True
        return False

    async def get_lock_owner(self, key):
        return self.owners.get(key)

    async def renew_lock(self, key, owner_id, ttl_seconds):
        self.renew_calls.append((key, owner_id, ttl_seconds))
        current = (
            self.owners[key].decode("utf-8")
            if isinstance(self.owners.get(key), bytes)
            else self.owners.get(key)
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
    assert queue.owners[MAINTENANCE_LEADER_KEY] == maintenance_owner_id("runner-a")
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


def test_partition_maintenance_key_accepts_only_canonical_partition_codes():
    assert partition_maintenance_leader_key("browser_local") == (
        "mindscape:runner:maintenance:partition:browser_local:leader:v1"
    )
    with pytest.raises(ValueError):
        partition_maintenance_leader_key("browser/local")


@pytest.mark.asyncio
async def test_partition_leases_exclude_same_partition_but_not_other_partition():
    queue = _FakeQueue()

    assert await try_hold_partition_maintenance_leadership(
        queue,
        runner_id="runner-a",
        queue_partition="browser_local",
        ttl_seconds=180,
    )
    assert not await try_hold_partition_maintenance_leadership(
        queue,
        runner_id="runner-b",
        queue_partition="browser_local",
        ttl_seconds=180,
    )
    assert await try_hold_partition_maintenance_leadership(
        queue,
        runner_id="runner-b",
        queue_partition="default_local_browser",
        ttl_seconds=180,
    )
    assert queue.owners[
        partition_maintenance_leader_key("browser_local")
    ] == partition_maintenance_owner_id("runner-a", "browser_local")
    assert queue.owners[
        partition_maintenance_leader_key("default_local_browser")
    ] == partition_maintenance_owner_id("runner-b", "default_local_browser")


@pytest.mark.asyncio
async def test_invalid_partition_leadership_fails_closed_without_redis_call():
    queue = _FakeQueue()

    assert not await try_hold_partition_maintenance_leadership(
        queue,
        runner_id="runner-a",
        queue_partition="invalid/partition",
        ttl_seconds=180,
    )
    assert queue.acquire_calls == []
