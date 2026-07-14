from types import SimpleNamespace

import pytest

from backend.app.services.runner_resources.browser_startup_gate import (
    BROWSER_STARTUP_LEASE_KEY,
    acquire_browser_startup_gate,
    browser_startup_slot_lease_key,
    resolve_browser_startup_request_bytes,
    resolve_browser_startup_slot_count,
    resolve_browser_startup_spacing_seconds,
)
from backend.app.services.runner_resources.leases import InMemoryResourceLeaseStore

MIB = 1024 * 1024


def test_unknown_startup_profile_fails_closed_even_with_finite_limit():
    assert (
        resolve_browser_startup_request_bytes(
            SimpleNamespace(browser_startup_memory_mb=0),
            {"cgroup_limit_bytes": 6 * 1024 * MIB},
        )
        is None
    )


def test_unknown_startup_profile_without_limit_fails_closed():
    assert (
        resolve_browser_startup_request_bytes(
            SimpleNamespace(browser_startup_memory_mb=0),
            {"cgroup_limit_bytes": None},
        )
        is None
    )


def test_startup_spacing_precedence_and_bounds():
    assert resolve_browser_startup_spacing_seconds(
        SimpleNamespace(browser_startup_spacing_seconds=45),
        environ={"LOCAL_CORE_RUNNER_BROWSER_STARTUP_SPACING_SECONDS": "20"},
    ) == 45
    assert resolve_browser_startup_spacing_seconds(
        SimpleNamespace(browser_startup_spacing_seconds=0),
        environ={"LOCAL_CORE_RUNNER_BROWSER_STARTUP_SPACING_SECONDS": "2"},
    ) == 5
    assert resolve_browser_startup_spacing_seconds(
        SimpleNamespace(browser_startup_spacing_seconds=0),
        environ={"LOCAL_CORE_RUNNER_BROWSER_STARTUP_SPACING_SECONDS": "999"},
    ) == 300


@pytest.mark.asyncio
async def test_missing_startup_memory_still_acquires_spacing_key():
    store = InMemoryResourceLeaseStore()
    decision = await acquire_browser_startup_gate(
        requirements=SimpleNamespace(
            browser_startup_memory_mb=0,
            browser_startup_spacing_seconds=30,
        ),
        node_snapshot={"available_bytes": 8 * 1024 * MIB},
        lease_store=store,
        owner_id="runner-a:task-a",
    )

    assert decision.allow is True
    assert decision.reason is None
    assert decision.requested_bytes == 0
    assert decision.request_source == "unmeasured_spacing_only"
    assert decision.spacing_seconds == 30
    assert decision.slot_count == 1
    assert decision.slot_index == 0
    assert decision.lease_key == BROWSER_STARTUP_LEASE_KEY
    assert await store.list_expired() == []


def test_measured_startup_slots_are_derived_from_headroom_and_bounded():
    requirements = SimpleNamespace(browser_startup_memory_mb=2048)
    snapshot = {"available_bytes": 8 * 1024 * MIB}

    assert resolve_browser_startup_slot_count(
        requirements,
        snapshot,
        environ={},
    ) == 4
    assert resolve_browser_startup_slot_count(
        SimpleNamespace(browser_startup_memory_mb=192),
        snapshot,
        environ={},
    ) == 7
    assert resolve_browser_startup_slot_count(
        requirements,
        snapshot,
        environ={"LOCAL_CORE_RUNNER_BROWSER_STARTUP_MAX_PARALLEL": "2"},
    ) == 2
    assert resolve_browser_startup_slot_count(
        requirements,
        {"available_bytes": 1024 * MIB},
        environ={},
    ) == 0


@pytest.mark.asyncio
async def test_measured_startup_uses_all_byte_safe_slots_before_spacing_defer():
    store = InMemoryResourceLeaseStore()
    requirements = SimpleNamespace(
        browser_startup_memory_mb=2048,
        browser_startup_spacing_seconds=10,
    )
    snapshot = {"available_bytes": 8 * 1024 * MIB}

    decisions = [
        await acquire_browser_startup_gate(
            requirements=requirements,
            node_snapshot=snapshot,
            lease_store=store,
            owner_id=f"runner-{index}:task-{index}",
        )
        for index in range(5)
    ]

    assert [decision.allow for decision in decisions] == [
        True,
        True,
        True,
        True,
        False,
    ]
    assert [decision.slot_index for decision in decisions[:4]] == [3, 2, 1, 0]
    assert decisions[0].lease_key == browser_startup_slot_lease_key(3)
    assert decisions[-2].lease_key == BROWSER_STARTUP_LEASE_KEY
    assert decisions[-1].reason == "browser_startup_spacing_active"
    assert decisions[-1].slot_count == 4


@pytest.mark.asyncio
async def test_small_startups_preserve_low_index_slots_for_large_startups():
    store = InMemoryResourceLeaseStore()
    snapshot = {"available_bytes": 4 * 1024 * MIB}
    small = SimpleNamespace(
        browser_startup_memory_mb=512,
        browser_startup_spacing_seconds=10,
    )
    large = SimpleNamespace(
        browser_startup_memory_mb=2048,
        browser_startup_spacing_seconds=10,
    )

    small_decisions = [
        await acquire_browser_startup_gate(
            requirements=small,
            node_snapshot=snapshot,
            lease_store=store,
            owner_id=f"small-{index}",
        )
        for index in range(2)
    ]
    large_decision = await acquire_browser_startup_gate(
        requirements=large,
        node_snapshot=snapshot,
        lease_store=store,
        owner_id="large",
    )

    assert [decision.slot_index for decision in small_decisions] == [6, 5]
    assert large_decision.allow is True
    assert large_decision.slot_count == 2
    assert large_decision.slot_index == 1
