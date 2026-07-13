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
            "LOCAL_CORE_RUNNER_NODE_BROWSER_IDLE_PEAK_MB": "1024",
        },
    )
    assert calibrated.mode == "calibrated"
    assert calibrated.allocatable_bytes == (16384 - 2048 - 3072 - 1024) * MIB
    assert calibrated.browser_idle_peak_bytes == 1024 * MIB

    partial = resolve_node_budget_policy(
        _snapshot(),
        environ={
            "LOCAL_CORE_RUNNER_NODE_VM_OVERHEAD_PEAK_MB": "2048",
            "LOCAL_CORE_RUNNER_NODE_NON_BROWSER_PEAK_MB": "3072",
        },
    )
    assert partial.mode == "bootstrap_full_cgroup"
    assert partial.browser_idle_peak_bytes == 0

    bootstrap = resolve_node_budget_policy(_snapshot(), environ={})
    assert bootstrap.mode == "bootstrap_full_cgroup"
    assert bootstrap.allocatable_bytes == 6144 * MIB


def test_unknown_browser_request_fails_closed_even_with_finite_limit():
    requirements = SimpleNamespace(memory_mb=0, browser_startup_memory_mb=0)
    assert (
        resolve_browser_request_bytes(requirements, _snapshot(), environ={})
        is None
    )
    assert (
        resolve_browser_request_bytes(
            requirements,
            _snapshot(limit_mb=None),
            environ={},
        )
        is None
    )


def test_browser_request_reserves_playbook_peak_for_full_task_lifetime():
    requirements = SimpleNamespace(
        memory_mb=1920,
        browser_startup_memory_mb=3520,
    )
    assert resolve_browser_request_bytes(
        requirements,
        _snapshot(limit_mb=None),
        environ={},
    ) == (3520 * MIB, "playbook_peak_profile")


def test_unmeasured_browser_request_uses_observed_floor_when_configured():
    requirements = SimpleNamespace(memory_mb=0, browser_startup_memory_mb=0)
    assert resolve_browser_request_bytes(
        requirements,
        _snapshot(limit_mb=None),
        environ={
            "LOCAL_CORE_RUNNER_BROWSER_UNMEASURED_RESERVATION_MB": "2304"
        },
    ) == (2304 * MIB, "observed_unmeasured_floor")


@pytest.mark.asyncio
async def test_budget_derives_active_count_from_bytes_and_is_idempotent():
    policy = resolve_node_budget_policy(
        _snapshot(),
        environ={
            "LOCAL_CORE_RUNNER_NODE_VM_OVERHEAD_PEAK_MB": "2048",
            "LOCAL_CORE_RUNNER_NODE_NON_BROWSER_PEAK_MB": "2048",
            "LOCAL_CORE_RUNNER_NODE_BROWSER_IDLE_PEAK_MB": "0",
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
async def test_reconcile_down_preserves_revision_renewal_and_release_accounting():
    policy = resolve_node_budget_policy(_snapshot(), environ={})
    store = InMemoryNodeBudgetStore(now_epoch=100)
    acquired = await store.acquire(
        owner_id="runner-a:task-1",
        request_bytes=6144 * MIB,
        policy=policy,
        profile_fingerprint="profile-a",
        ttl_seconds=30,
    )
    reservation = acquired.reservation
    assert reservation is not None

    assert await store.reconcile_down(
        reservation,
        request_bytes=2432 * MIB,
        evidence_fingerprint="a" * 64,
    )
    snapshot = await store.snapshot()
    reconciled = snapshot["reservations"][0]
    assert snapshot["reserved_bytes"] == 2432 * MIB
    assert reconciled["revision"] == reservation.revision
    assert reconciled["reconciled_from_bytes"] == 6144 * MIB
    assert reconciled["reconciliation_evidence_fingerprint"] == "a" * 64

    assert await store.renew(reservation, ttl_seconds=30)
    assert not await store.reconcile_down(
        reservation,
        request_bytes=7000 * MIB,
        evidence_fingerprint="b" * 64,
    )
    wrong_revision = type(reservation)(
        **{**reservation.to_context(), "revision": reservation.revision + 1}
    )
    assert not await store.reconcile_down(
        wrong_revision,
        request_bytes=1024 * MIB,
        evidence_fingerprint="c" * 64,
    )
    assert await store.release(reservation)
    assert (await store.snapshot())["reserved_bytes"] == 0


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
