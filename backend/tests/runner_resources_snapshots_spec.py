from types import SimpleNamespace

import pytest

from backend.app.services.runner_resources import (
    InMemoryTtlSnapshotStore,
    PROGRESS_SNAPSHOT_TTL_SECONDS,
    RUN_LOG_COUNT_SNAPSHOT_TTL_SECONDS,
    build_progress_snapshot_key,
    build_run_log_count_snapshot_key,
    build_runner_resource_heartbeat,
    get_ttl_snapshot,
    set_ttl_snapshot,
)


@pytest.mark.asyncio
async def test_ttl_snapshot_store_expires_hot_state():
    store = InMemoryTtlSnapshotStore(now_epoch=100.0)

    assert await set_ttl_snapshot(
        store,
        "progress:task-1",
        {"status": "running"},
        ttl_seconds=5,
    )
    assert await get_ttl_snapshot(store, "progress:task-1") == {"status": "running"}

    store.advance(5)
    assert await get_ttl_snapshot(store, "progress:task-1") is None


def test_runner_resource_heartbeat_captures_capacity_snapshot():
    heartbeat = build_runner_resource_heartbeat(
        runner_id="runner-a",
        profile_code="runner-browser",
        queue_shards=("browser_local",),
        capacity=SimpleNamespace(
            max_inflight=2,
            inflight=1,
            available_slots=1,
            poll_batch_limit=1,
            saturated=False,
        ),
        resource_snapshot={"memory": {"working_set_ratio": 0.5}},
        now_epoch=100.0,
    )

    assert heartbeat["runner_id"] == "runner-a"
    assert heartbeat["profile_code"] == "runner-browser"
    assert heartbeat["queue_shards"] == ["browser_local"]
    assert heartbeat["captured_at_epoch"] == 100.0
    assert heartbeat["capacity"]["available_slots"] == 1
    assert heartbeat["resource_snapshot"]["memory"]["working_set_ratio"] == 0.5


def test_hot_snapshot_ttls_match_track01_gate():
    assert PROGRESS_SNAPSHOT_TTL_SECONDS == 5
    assert RUN_LOG_COUNT_SNAPSHOT_TTL_SECONDS == 5


def test_hot_snapshot_keys_are_namespaced_and_stable():
    progress_key = build_progress_snapshot_key("ws/1", "exec 1")
    count_key = build_run_log_count_snapshot_key("ws/1", "exec 1")

    assert progress_key == build_progress_snapshot_key("ws/1", "exec 1")
    assert progress_key.startswith("mindscape:runner_resources:snapshot:v1:progress:")
    assert count_key.startswith(
        "mindscape:runner_resources:snapshot:v1:run_log_counts:"
    )
    assert "/" not in progress_key
    assert " " not in progress_key
