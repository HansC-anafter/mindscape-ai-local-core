from types import SimpleNamespace

import pytest

from backend.app.services.runner_resources.browser_startup_gate import (
    acquire_browser_startup_gate,
    resolve_browser_startup_request_bytes,
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
async def test_missing_startup_memory_and_limit_does_not_acquire_spacing_key():
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

    assert decision.allow is False
    assert decision.reason == "browser_startup_memory_requirement_unavailable"
    assert await store.list_expired() == []
