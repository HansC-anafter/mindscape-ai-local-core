from types import SimpleNamespace

import pytest

from backend.app.services.runner_resources import (
    InMemoryNodeBudgetStore,
    RedisNodeBudgetStore,
)
from backend.app.services.runner_resources.node_budget import (
    resolve_browser_request_bytes,
    resolve_node_budget_policy,
)

MIB = 1024 * 1024


def _snapshot(*, total_mb=16384, available_mb=12000, limit_mb=6144):
    return {
        "total_bytes": total_mb * MIB,
        "available_bytes": available_mb * MIB,
        "cgroup_limit_bytes": None if limit_mb is None else limit_mb * MIB,
    }


def test_calibrated_and_bootstrap_policies_deduct_reserve_once():
    calibrated = resolve_node_budget_policy(
        _snapshot(),
        environ={
            "LOCAL_CORE_RUNNER_NODE_VM_OVERHEAD_PEAK_MB": "2048",
            "LOCAL_CORE_RUNNER_NODE_NON_BROWSER_PEAK_MB": "3072",
        },
    )
    assert calibrated.mode == "calibrated"
    assert calibrated.allocatable_bytes == (16384 - 2048 - 3072) * MIB

    bootstrap = resolve_node_budget_policy(_snapshot(), environ={})
    assert bootstrap.mode == "bootstrap_full_cgroup"
    assert bootstrap.allocatable_bytes == 6144 * MIB


def test_unknown_browser_request_uses_finite_limit_and_unlimited_fails_closed():
    requirements = SimpleNamespace(memory_mb=0)
    assert resolve_browser_request_bytes(requirements, _snapshot()) == (
        6144 * MIB,
        "container_limit_fallback",
    )
    assert resolve_browser_request_bytes(
        requirements,
        _snapshot(limit_mb=None),
    ) is None


@pytest.mark.asyncio
async def test_budget_derives_active_count_from_bytes_and_is_idempotent():
    policy = resolve_node_budget_policy(
        _snapshot(),
        environ={
            "LOCAL_CORE_RUNNER_NODE_VM_OVERHEAD_PEAK_MB": "2048",
            "LOCAL_CORE_RUNNER_NODE_NON_BROWSER_PEAK_MB": "2048",
        },
    )
    store = InMemoryNodeBudgetStore(now_epoch=100)

    first = await store.acquire(
        owner_id="runner-a:task-1",
        request_bytes=3000 * MIB,
        policy=policy,
        profile_fingerprint="profile-a",
        ttl_seconds=30,
    )
    repeated = await store.acquire(
        owner_id="runner-a:task-1",
        request_bytes=3000 * MIB,
        policy=policy,
        profile_fingerprint="profile-a",
        ttl_seconds=30,
    )
    additional = []
    for index in range(2, 6):
        additional.append(
            await store.acquire(
                owner_id=f"runner-{index}:task-{index}",
                request_bytes=3000 * MIB,
                policy=policy,
                profile_fingerprint=f"profile-{index}",
                ttl_seconds=30,
            )
        )

    assert first.allow is True
    assert repeated.allow is True
    assert repeated.reservation.revision == first.reservation.revision
    assert [item.allow for item in additional] == [True, True, True, False]
    assert additional[-1].reason == "node_budget_exhausted"
    snapshot = await store.snapshot()
    assert snapshot["active_reservations"] == 4
    assert snapshot["reserved_bytes"] == 12000 * MIB
    assert snapshot["policy_fingerprint"] == policy.fingerprint


@pytest.mark.asyncio
async def test_expiry_releases_bytes_but_keeps_last_policy_projection():
    policy = resolve_node_budget_policy(_snapshot(), environ={})
    store = InMemoryNodeBudgetStore(now_epoch=0)
    acquired = await store.acquire(
        owner_id="runner-a:task-1",
        request_bytes=policy.allocatable_bytes,
        policy=policy,
        profile_fingerprint="profile-a",
        ttl_seconds=5,
    )
    assert acquired.allow is True
    store.advance(6)
    snapshot = await store.snapshot()
    assert snapshot["reserved_bytes"] == 0
    assert snapshot["active_reservations"] == 0
    assert snapshot["policy_fingerprint"] == policy.fingerprint


@pytest.mark.asyncio
async def test_redis_error_fails_closed_without_local_counter_fallback():
    class BrokenClient:
        async def eval(self, *_args):
            raise ConnectionError("redis unavailable")

    class Queue:
        async def _get_client(self):
            return BrokenClient()

    policy = resolve_node_budget_policy(_snapshot(), environ={})
    store = RedisNodeBudgetStore(Queue())
    decision = await store.acquire(
        owner_id="runner-a:task-1",
        request_bytes=policy.allocatable_bytes,
        policy=policy,
        profile_fingerprint="profile-a",
        ttl_seconds=30,
    )

    assert decision.allow is False
    assert decision.reason == "node_budget_unavailable"
    assert (await store.snapshot())["available"] is False
