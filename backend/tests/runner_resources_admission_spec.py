from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from backend.app.services.runner_resources import (
    BROWSER_STARTUP_LEASE_KEY,
    InMemoryNodeBudgetStore,
    InMemoryResourceLeaseStore,
    ResourceRequirements,
    acquire_task_resource_admission,
    build_resource_wait_task_update,
    release_acquired_resource_leases,
)

MIB = 1024 * 1024


def _capacity(available_slots: int):
    return SimpleNamespace(
        max_inflight=max(available_slots, 0),
        inflight=0,
        available_slots=available_slots,
        poll_batch_limit=1,
        saturated=available_slots <= 0,
    )


def _profile(code: str = "runner-browser"):
    return SimpleNamespace(profile_code=code)


def _task(task_id: str, pack_id: str = "ig-pack"):
    return SimpleNamespace(id=task_id, pack_id=pack_id)


@pytest.mark.asyncio
async def test_browser_context_pressure_parks_without_retry_increment():
    decision = await acquire_task_resource_admission(
        task=_task("task-1"),
        requirements=ResourceRequirements(browser_contexts=1),
        runner_profile=_profile(),
        capacity=_capacity(0),
        lease_store=InMemoryResourceLeaseStore(),
        owner_id="runner-a:task-1",
        ttl_seconds=30,
        now=datetime(2026, 5, 11, tzinfo=timezone.utc),
    )

    update = build_resource_wait_task_update(
        {"retry_count": 7, "runner_id": "runner-a"},
        decision,
        current_queue_shard="browser_local",
    )

    assert decision.allow is False
    assert decision.blocked_reason == "resource_wait"
    assert update["blocked_reason"] == "resource_wait"
    assert update["frontier_state"] == "cold"
    assert update["execution_context"]["retry_count"] == 7
    assert update["execution_context"]["last_runner_id"] == "runner-a"
    assert "runner_resource_leases" not in update["execution_context"]


@pytest.mark.asyncio
async def test_ig_profile_lock_blocks_second_task_until_release():
    store = InMemoryResourceLeaseStore(now_epoch=0.0)
    requirements = ResourceRequirements(
        browser_contexts=0,
        ig_profile_lock="profile-a",
    )

    first = await acquire_task_resource_admission(
        task=_task("task-1"),
        requirements=requirements,
        runner_profile=_profile(),
        capacity=_capacity(0),
        lease_store=store,
        owner_id="runner-a:task-1",
        ttl_seconds=30,
    )
    second = await acquire_task_resource_admission(
        task=_task("task-2"),
        requirements=requirements,
        runner_profile=_profile(),
        capacity=_capacity(0),
        lease_store=store,
        owner_id="runner-b:task-2",
        ttl_seconds=30,
    )

    assert first.allow is True
    assert len(first.acquired_leases) == 1
    assert "runner_resource_leases" in first.execution_context_updates
    assert second.allow is False
    assert second.blocked_payload["reason"] == "ig_profile_lock_leased"

    await release_acquired_resource_leases(
        store,
        first.acquired_leases,
        owner_id="runner-a:task-1",
    )
    third = await acquire_task_resource_admission(
        task=_task("task-2"),
        requirements=requirements,
        runner_profile=_profile(),
        capacity=_capacity(0),
        lease_store=store,
        owner_id="runner-b:task-2",
        ttl_seconds=30,
    )

    assert third.allow is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("pack_id", "requirements"),
    [
        (
            "workspace_planning_thin_task",
            ResourceRequirements(browser_contexts=0, llm_lane="low"),
        ),
        (
            "meeting_engine_thin_task",
            ResourceRequirements(browser_contexts=0, llm_lane="medium"),
        ),
    ],
)
async def test_non_browser_thin_tasks_remain_admissible_under_ig_pressure(
    pack_id,
    requirements,
):
    decision = await acquire_task_resource_admission(
        task=_task("task-thin", pack_id),
        requirements=requirements,
        runner_profile=_profile("runner-default"),
        capacity=_capacity(0),
        lease_store=InMemoryResourceLeaseStore(),
        owner_id="runner-default:task-thin",
        ttl_seconds=30,
    )

    assert decision.allow is True


@pytest.mark.asyncio
async def test_host_resource_advisor_blocks_declared_memory_pressure(monkeypatch):
    from backend.app import services as _services  # noqa: F401
    import backend.app.services.host_resources as host_resources

    monkeypatch.setattr(
        host_resources,
        "evaluate_runner_requirements",
        lambda _requirements: SimpleNamespace(
            allow=False,
            decision="defer",
            reason="insufficient_memory_headroom",
            payload={
                "lane_id": "comfyui_runtime:flux2_klein_true_v2_q6_local",
                "required": {"memory_mb": 12288},
                "available": {"memory_mb": 8192},
                "blocking_consumers": ["mlx:qwen9b_4bit_vision"],
            },
        ),
    )

    decision = await acquire_task_resource_admission(
        task=_task("task-heavy", "comfyui_runtime"),
        requirements=ResourceRequirements(
            memory_mb=12288,
            vision_lane="comfyui_runtime:flux2_klein_true_v2_q6_local",
        ),
        runner_profile=_profile("runner-vision"),
        capacity=_capacity(4),
        lease_store=InMemoryResourceLeaseStore(),
        owner_id="runner-vision:task-heavy",
        ttl_seconds=30,
    )

    assert decision.allow is False
    assert decision.blocked_reason == "resource_wait"
    assert decision.blocked_payload["reason"] == "insufficient_memory_headroom"
    assert decision.blocked_payload["blocked_resource"] == "host_resource"
    assert decision.blocked_payload["host_advisor"]["blocking_consumers"] == [
        "mlx:qwen9b_4bit_vision"
    ]


@pytest.mark.asyncio
async def test_browser_admission_uses_vm_bytes_and_not_host_advisor(monkeypatch):
    from backend.app import services as _services  # noqa: F401
    import backend.app.services.host_resources as host_resources

    monkeypatch.setattr(
        host_resources,
        "evaluate_runner_requirements",
        lambda _requirements: (_ for _ in ()).throw(
            AssertionError("browser path must not use physical-host advisor")
        ),
    )
    monkeypatch.setenv("LOCAL_CORE_RUNNER_NODE_VM_OVERHEAD_PEAK_MB", "1024")
    monkeypatch.setenv("LOCAL_CORE_RUNNER_NODE_NON_BROWSER_PEAK_MB", "1024")
    monkeypatch.setenv("LOCAL_CORE_RUNNER_NODE_BROWSER_IDLE_PEAK_MB", "0")
    snapshot = {
        "total_bytes": 10 * 1024 * MIB,
        "available_bytes": 8 * 1024 * MIB,
        "cgroup_limit_bytes": 6 * 1024 * MIB,
    }
    store = InMemoryNodeBudgetStore()
    requirements = ResourceRequirements(
        resource_class="browser",
        browser_contexts=1,
        memory_mb=3072,
        browser_startup_memory_mb=3072,
        browser_startup_spacing_seconds=5,
        memory_reservation_source="playbook_profile",
    )

    decisions = []
    for index in range(3):
        decisions.append(
            await acquire_task_resource_admission(
                task=_task(f"task-{index}"),
                requirements=requirements,
                runner_profile=_profile(),
                capacity=_capacity(3),
                lease_store=InMemoryResourceLeaseStore(),
                node_budget_store=store,
                node_memory_snapshot=snapshot,
                owner_id=f"runner-{index}:task-{index}",
                ttl_seconds=30,
            )
        )

    assert [item.allow for item in decisions] == [True, True, False]
    assert decisions[-1].blocked_payload["reason"] == "node_budget_exhausted"


@pytest.mark.asyncio
async def test_browser_hard_guard_requires_current_memavailable():
    store = InMemoryNodeBudgetStore()
    decision = await acquire_task_resource_admission(
        task=_task("task-low-headroom"),
        requirements=ResourceRequirements(
            resource_class="browser",
            browser_contexts=1,
            memory_mb=4096,
        ),
        runner_profile=_profile(),
        capacity=_capacity(3),
        lease_store=InMemoryResourceLeaseStore(),
        node_budget_store=store,
        node_memory_snapshot={
            "total_bytes": 16 * 1024 * MIB,
            "available_bytes": 3 * 1024 * MIB,
            "cgroup_limit_bytes": 6 * 1024 * MIB,
        },
        owner_id="runner-a:task-low-headroom",
        ttl_seconds=30,
    )

    assert decision.allow is False
    assert decision.blocked_payload["reason"] == "node_memory_headroom_unavailable"
    assert (await store.snapshot())["active_reservations"] == 0


@pytest.mark.asyncio
async def test_unmeasured_browser_request_does_not_invent_reservation():
    lease_store = InMemoryResourceLeaseStore()
    node_store = InMemoryNodeBudgetStore()
    decision = await acquire_task_resource_admission(
        task=_task("task-unmeasured"),
        requirements=ResourceRequirements(
            resource_class="browser",
            browser_contexts=1,
        ),
        runner_profile=_profile(),
        capacity=_capacity(3),
        lease_store=lease_store,
        node_budget_store=node_store,
        node_memory_snapshot={
            "total_bytes": 16 * 1024 * MIB,
            "available_bytes": 12 * 1024 * MIB,
            "cgroup_limit_bytes": 6 * 1024 * MIB,
        },
        owner_id="runner-a:task-unmeasured",
        ttl_seconds=30,
    )

    assert decision.allow is True
    assert decision.node_budget_reservation is None
    assert decision.execution_context_updates["resource_admission"] == {
        "state": "admitted",
        "task_id": "task-unmeasured",
        "runner_profile": "runner-browser",
        "requirements": ResourceRequirements(
            resource_class="browser",
            browser_contexts=1,
        ).to_dict(),
        "lease_keys": [],
        "requested_memory_bytes": 0,
        "memory_reservation_source": "unmeasured_no_reservation",
        "memory_admission_mode": "unmeasured_no_reservation",
        "node_policy_fingerprint": None,
        "resource_profile_fingerprint": None,
        "browser_startup": None,
        "admitted_at": decision.execution_context_updates[
            "resource_admission"
        ]["admitted_at"],
    }
    assert (await node_store.snapshot())["active_reservations"] == 0
    assert await lease_store.list_expired() == []


@pytest.mark.asyncio
async def test_measured_browser_request_without_startup_measurement_skips_spacing():
    store = InMemoryNodeBudgetStore()
    decision = await acquire_task_resource_admission(
        task=_task("task-runtime-measured"),
        requirements=ResourceRequirements(
            resource_class="browser",
            browser_contexts=1,
            memory_mb=256,
            memory_reservation_source="playbook_profile",
        ),
        runner_profile=_profile(),
        capacity=_capacity(3),
        lease_store=InMemoryResourceLeaseStore(),
        node_budget_store=store,
        node_memory_snapshot={
            "total_bytes": 16 * 1024 * MIB,
            "available_bytes": 12 * 1024 * MIB,
            "cgroup_limit_bytes": 6 * 1024 * MIB,
        },
        owner_id="runner-a:task-runtime-measured",
        ttl_seconds=30,
    )

    assert decision.allow is True
    assert decision.node_budget_reservation is not None
    assert decision.execution_context_updates["resource_admission"][
        "memory_admission_mode"
    ] == "measured_reservation"
    assert decision.execution_context_updates["resource_admission"][
        "browser_startup"
    ] is None


@pytest.mark.asyncio
async def test_browser_startup_spacing_serializes_claims_without_durable_lease():
    lease_store = InMemoryResourceLeaseStore(now_epoch=0.0)
    node_store = InMemoryNodeBudgetStore()
    requirements = ResourceRequirements(
        resource_class="browser",
        browser_contexts=1,
        memory_mb=1024,
        browser_startup_memory_mb=2048,
        browser_startup_spacing_seconds=10,
        memory_reservation_source="playbook_profile",
    )
    snapshot = {
        "total_bytes": 10 * 1024 * MIB,
        "available_bytes": 8 * 1024 * MIB,
        "cgroup_limit_bytes": 6 * 1024 * MIB,
    }

    first = await acquire_task_resource_admission(
        task=_task("task-start-1"),
        requirements=requirements,
        runner_profile=_profile(),
        capacity=_capacity(3),
        lease_store=lease_store,
        node_budget_store=node_store,
        node_memory_snapshot=snapshot,
        owner_id="runner-a:task-start-1",
        ttl_seconds=30,
    )
    second = await acquire_task_resource_admission(
        task=_task("task-start-2"),
        requirements=requirements,
        runner_profile=_profile(),
        capacity=_capacity(3),
        lease_store=lease_store,
        node_budget_store=node_store,
        node_memory_snapshot=snapshot,
        owner_id="runner-b:task-start-2",
        ttl_seconds=30,
    )

    assert first.allow is True
    assert first.acquired_leases == []
    assert first.execution_context_updates["runner_resource_leases"] == []
    assert second.allow is False
    assert second.blocked_payload["reason"] == "browser_startup_spacing_active"
    assert second.blocked_payload["startup_spacing_seconds"] == 10
    assert (await node_store.snapshot())["active_reservations"] == 1

    lease_store.advance(10)
    third = await acquire_task_resource_admission(
        task=_task("task-start-2"),
        requirements=requirements,
        runner_profile=_profile(),
        capacity=_capacity(3),
        lease_store=lease_store,
        node_budget_store=node_store,
        node_memory_snapshot=snapshot,
        owner_id="runner-b:task-start-2",
        ttl_seconds=30,
    )

    assert third.allow is True
    assert BROWSER_STARTUP_LEASE_KEY not in [
        item["lease_key"]
        for item in third.execution_context_updates["runner_resource_leases"]
    ]
    assert (await node_store.snapshot())["active_reservations"] == 2


@pytest.mark.asyncio
async def test_profile_lock_conflict_does_not_consume_browser_startup_spacing():
    lease_store = InMemoryResourceLeaseStore(now_epoch=0.0)
    node_store = InMemoryNodeBudgetStore()
    snapshot = {
        "total_bytes": 10 * 1024 * MIB,
        "available_bytes": 8 * 1024 * MIB,
        "cgroup_limit_bytes": 6 * 1024 * MIB,
    }

    def requirements(profile: str) -> ResourceRequirements:
        return ResourceRequirements(
            resource_class="browser",
            browser_contexts=1,
            ig_profile_lock=profile,
            memory_mb=1024,
            browser_startup_memory_mb=2048,
            browser_startup_spacing_seconds=10,
            memory_reservation_source="playbook_profile",
        )

    first = await acquire_task_resource_admission(
        task=_task("task-start-profile-1"),
        requirements=requirements("profile-a"),
        runner_profile=_profile(),
        capacity=_capacity(3),
        lease_store=lease_store,
        node_budget_store=node_store,
        node_memory_snapshot=snapshot,
        owner_id="runner-a:task-start-profile-1",
        ttl_seconds=30,
    )
    assert first.allow is True

    lease_store.advance(10)
    blocked = await acquire_task_resource_admission(
        task=_task("task-start-profile-2"),
        requirements=requirements("profile-a"),
        runner_profile=_profile(),
        capacity=_capacity(3),
        lease_store=lease_store,
        node_budget_store=node_store,
        node_memory_snapshot=snapshot,
        owner_id="runner-b:task-start-profile-2",
        ttl_seconds=30,
    )
    assert blocked.allow is False
    assert blocked.blocked_payload["reason"] == "ig_profile_lock_leased"

    different_profile = await acquire_task_resource_admission(
        task=_task("task-start-profile-3"),
        requirements=requirements("profile-b"),
        runner_profile=_profile(),
        capacity=_capacity(3),
        lease_store=lease_store,
        node_budget_store=node_store,
        node_memory_snapshot=snapshot,
        owner_id="runner-c:task-start-profile-3",
        ttl_seconds=30,
    )
    assert different_profile.allow is True


@pytest.mark.asyncio
async def test_browser_startup_headroom_releases_steady_reservation():
    node_store = InMemoryNodeBudgetStore()
    decision = await acquire_task_resource_admission(
        task=_task("task-start-low-headroom"),
        requirements=ResourceRequirements(
            resource_class="browser",
            browser_contexts=1,
            memory_mb=1024,
            browser_startup_memory_mb=4096,
            browser_startup_spacing_seconds=10,
        ),
        runner_profile=_profile(),
        capacity=_capacity(3),
        lease_store=InMemoryResourceLeaseStore(),
        node_budget_store=node_store,
        node_memory_snapshot={
            "total_bytes": 10 * 1024 * MIB,
            "available_bytes": 3 * 1024 * MIB,
            "cgroup_limit_bytes": 6 * 1024 * MIB,
        },
        owner_id="runner-a:task-start-low-headroom",
        ttl_seconds=30,
    )

    assert decision.allow is False
    assert decision.blocked_payload["reason"] == (
        "browser_startup_headroom_unavailable"
    )
    assert decision.blocked_payload["startup_requested_bytes"] == 4096 * MIB
    assert (await node_store.snapshot())["active_reservations"] == 0
