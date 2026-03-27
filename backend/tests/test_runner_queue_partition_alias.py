from types import SimpleNamespace

import pytest

from backend.app.runner import worker
from backend.app.runner.worker import _build_ready_queue_stores, _resolve_task_queue_shard
from backend.app.services.runner_topology import RUNNER_READY_QUEUE_ORDER
from backend.app.services.stores.tasks_store._base import _resolve_queue_shard


def test_tasks_store_resolves_queue_partition_before_legacy_pack_mapping():
    assert (
        _resolve_queue_shard(
            "ig_analyze_following",
            {"queue_partition": "vision_local"},
        )
        == "vision_local"
    )


def test_worker_resolves_queue_partition_alias_for_ready_queue_selection():
    assert (
        _resolve_task_queue_shard(
            "ig_analyze_following",
            {"queue_partition": "browser_local"},
        )
        == "browser_local"
    )


def test_worker_normalizes_legacy_alias_into_canonical_partition():
    assert (
        _resolve_task_queue_shard(
            "ig_analyze_following",
            {"queue_shard": "ig_browser"},
        )
        == "browser_local"
    )


def test_worker_ready_queues_follow_canonical_partition_order():
    assert tuple(_build_ready_queue_stores().keys()) == RUNNER_READY_QUEUE_ORDER


def test_worker_ready_queues_can_be_scoped_to_profile_partitions():
    assert tuple(_build_ready_queue_stores(("browser_local",)).keys()) == (
        "browser_local",
    )


@pytest.mark.asyncio
async def test_run_maintenance_cycle_uses_profile_ready_queue_keys(monkeypatch):
    ready_queue = SimpleNamespace(pack_id="browser_local")
    called: list[str] = []

    monkeypatch.setattr(worker, "_reap_stale_running_tasks", lambda *args, **kwargs: None)

    async def _fake_reap(_tasks_store, queue_store, *, ready_target_override, all_queues):
        called.append(f"{queue_store.pack_id}:{ready_target_override}:{len(all_queues)}")

    monkeypatch.setattr(worker, "_reap_redis_queues", _fake_reap)

    await worker._run_maintenance_cycle(
        tasks_store=object(),
        runner_id="runner-1",
        redis_queue=ready_queue,
        ready_queues={"browser_local": ready_queue},
        ready_targets={"browser_local": 3},
        queue_cycle=[ready_queue],
    )

    assert called == ["browser_local:3:1"]
