from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend.app.services.host_resources import queue_utilization
from backend.app.services.host_resources.queue_utilization import (
    build_live_queue_utilization,
    write_queue_utilization_snapshot_if_leader,
)
from backend.app.services.host_resources.queue_utilization_snapshot_store import (
    QueueUtilizationSnapshotStore,
)
from host_resources_queue_utilization_test_support import (
    FakeConnection,
    FakeConnectionContext,
    FakeQueue,
    FakeSnapshotStore,
    projection,
)


@pytest.mark.asyncio
async def test_live_queue_utilization_excludes_drain_runner_available_slots(monkeypatch):
    queue = FakeQueue("browser_local", ["task-a"])
    queue.client.projections[
        "mindscape:host_resources:route_identity:task-a"
    ] = projection("task-a", "ig_pin_post_detail", "ig_profile:a")

    async def _heartbeats(_queue_store):
        return [
            {
                "runner_id": "runner-browser-1",
                "queue_shards": ["browser_local"],
                "capacity": {
                    "max_inflight": 3,
                    "inflight": 2,
                    "available_slots": 1,
                },
                "claim_control": {
                    "mode": "drain",
                    "claim_enabled": False,
                },
            }
        ]

    monkeypatch.setattr(
        queue_utilization,
        "list_active_runner_resource_heartbeats",
        _heartbeats,
    )

    snapshot = await build_live_queue_utilization(
        queue_stores=[queue],
        scan_limit=1,
        now_epoch=1000,
    )

    capacity = snapshot["capacity_by_queue_shard"]["browser_local"]
    assert capacity["active_runner_count"] == 1
    assert capacity["claimable_runner_count"] == 0
    assert capacity["claim_blocked_runner_count"] == 1
    assert capacity["max_inflight_total"] == 3
    assert capacity["inflight_total"] == 2
    assert capacity["available_slots_total"] == 0
    assert capacity["claimable_available_slots_total"] == 0


@pytest.mark.asyncio
async def test_live_queue_utilization_marks_resource_admission_cooldown_unclaimable(
    monkeypatch,
):
    queue = FakeQueue("default_local_browser", ["task-a"])
    queue.client.projections[
        "mindscape:host_resources:route_identity:task-a"
    ] = projection(
        "task-a",
        "ig_batch_pin_references",
        "concurrency:playbook:ig_batch_pin_references:/app/data/ig...",
    )

    async def _heartbeats(_queue_store):
        return [
            {
                "runner_id": "runner-browser-1",
                "profile_code": "default_local_browser",
                "queue_shards": ["default_local_browser"],
                "capacity": {
                    "max_inflight": 3,
                    "inflight": 1,
                    "available_slots": 2,
                },
                "claim_control": {
                    "mode": "active",
                    "claim_enabled": True,
                },
                "resource_snapshot": {
                    "admission": {
                        "state": "cooldown",
                        "should_defer": True,
                        "reasons": [],
                        "cooldown_until_epoch": 1234.0,
                    },
                },
            }
        ]

    monkeypatch.setattr(
        queue_utilization,
        "list_active_runner_resource_heartbeats",
        _heartbeats,
    )

    snapshot = await build_live_queue_utilization(
        queue_stores=[queue],
        scan_limit=1,
        now_epoch=1000,
    )

    capacity = snapshot["capacity_by_queue_shard"]["default_local_browser"]
    assert capacity["active_runner_count"] == 1
    assert capacity["claimable_runner_count"] == 0
    assert capacity["claim_blocked_runner_count"] == 1
    assert capacity["max_inflight_total"] == 3
    assert capacity["inflight_total"] == 1
    assert capacity["available_slots_total"] == 2
    assert capacity["claimable_available_slots_total"] == 0
    assert capacity["claim_blocked_reasons"] == ["resource_admission:cooldown"]
    assert capacity["resource_admission"] == [
        {
            "runner_id": "runner-browser-1",
            "state": "cooldown",
            "reasons": [],
            "cooldown_until_epoch": 1234.0,
        }
    ]


@pytest.mark.asyncio
async def test_live_queue_utilization_does_not_apply_browser_admission_to_compute(
    monkeypatch,
):
    queue = FakeQueue("vision_local", ["task-a"])

    async def _heartbeats(_queue_store):
        return [
            {
                "runner_id": "runner-vision-1",
                "profile_code": "vision_local",
                "queue_shards": ["vision_local"],
                "accepted_resource_classes": ["compute"],
                "capacity": {
                    "max_inflight": 3,
                    "inflight": 1,
                    "available_slots": 2,
                },
                "claim_control": {
                    "mode": "active",
                    "claim_enabled": True,
                },
                "resource_snapshot": {
                    "admission": {
                        "state": "soft_defer",
                        "should_defer": True,
                        "reasons": ["browser_session_slots"],
                    },
                },
            }
        ]

    monkeypatch.setattr(
        queue_utilization,
        "list_active_runner_resource_heartbeats",
        _heartbeats,
    )
    snapshot = await build_live_queue_utilization(
        queue_stores=[queue],
        scan_limit=1,
        now_epoch=1000,
    )

    capacity = snapshot["capacity_by_queue_shard"]["vision_local"]
    assert capacity["active_runner_count"] == 1
    assert capacity["claimable_runner_count"] == 1
    assert capacity["claim_blocked_runner_count"] == 0
    assert capacity["claimable_available_slots_total"] == 2
    assert capacity["claim_blocked_reasons"] == []


@pytest.mark.asyncio
async def test_live_queue_utilization_uses_bounded_redis_data(monkeypatch):
    queue = FakeQueue(
        "browser_local",
        ["task-a", "task-b", "task-c", "task-d", "task-e"],
    )
    for task_id, lock_key in {
        "task-a": "ig_profile:a",
        "task-b": "ig_profile:a",
        "task-c": "ig_profile:b",
    }.items():
        queue.client.projections[
            f"mindscape:host_resources:route_identity:{task_id}"
        ] = projection(task_id, "ig_pin_post_detail", lock_key)

    async def _heartbeats(_queue_store):
        return [
            {
                "runner_id": "runner-browser-1",
                "queue_shards": ["browser_local"],
                "capacity": {
                    "max_inflight": 3,
                    "inflight": 2,
                    "available_slots": 1,
                },
            }
        ]

    monkeypatch.setattr(
        queue_utilization,
        "list_active_runner_resource_heartbeats",
        _heartbeats,
    )

    snapshot = await build_live_queue_utilization(
        queue_stores=[queue],
        scan_limit=3,
        now_epoch=1000,
    )

    assert snapshot["source"] == "live_redis_bounded"
    assert snapshot["captured_at"] == "1970-01-01T00:16:40+00:00"
    assert snapshot["captured_at_by_queue_shard"] == {
        "browser_local": "1970-01-01T00:16:40+00:00",
    }
    assert snapshot["queue_depths"]["browser_local"] == {
        "pending": 5,
        "processing": 2,
        "delayed": 1,
        "deadletter": 0,
    }
    assert queue.client.lrange_calls == [("pending:browser_local", 0, 2)]
    assert snapshot["visible_lane_count"]["browser_local"] == 2
    assert [
        lane["lane_key"] for lane in snapshot["visible_lanes"]["browser_local"]
    ] == ["concurrency_key:ig_profile:a", "concurrency_key:ig_profile:b"]
    assert snapshot["capacity_by_queue_shard"]["browser_local"][
        "max_inflight_total"
    ] == 3
    assert snapshot["utilization_ratio_by_queue_shard"]["browser_local"] == 2 / 3


def test_latest_snapshot_preserves_last_known_state_per_queue_shard(monkeypatch):
    browser_captured_at = datetime(2026, 6, 20, 4, 40, tzinfo=timezone.utc)
    vision_captured_at = datetime(2026, 6, 20, 4, 37, tzinfo=timezone.utc)
    rows = [
        {
            "captured_at": browser_captured_at,
            "queue_shard": "browser_local",
            "pending_depth": 0,
            "processing_depth": 3,
            "delayed_depth": 0,
            "deadletter_depth": 4,
            "visible_lane_count": 0,
            "visible_lanes_json": [],
            "active_runner_count": 2,
            "max_inflight_total": 6,
            "inflight_total": 3,
            "available_slots_total": 3,
        },
        {
            "captured_at": vision_captured_at,
            "queue_shard": "vision_local",
            "pending_depth": 62,
            "processing_depth": 1,
            "delayed_depth": 0,
            "deadletter_depth": 0,
            "visible_lane_count": 1,
            "visible_lanes_json": [],
            "active_runner_count": 1,
            "max_inflight_total": 3,
            "inflight_total": 0,
            "available_slots_total": 3,
        },
    ]
    connection = FakeConnection(rows)
    store = object.__new__(QueueUtilizationSnapshotStore)
    monkeypatch.setattr(
        store,
        "get_connection",
        lambda: FakeConnectionContext(connection),
    )

    snapshot = store.latest_snapshot()

    statement = connection.statements[0]
    assert "DISTINCT ON (queue_shard)" in statement
    assert "ORDER BY queue_shard, captured_at DESC" in statement
    assert "latest_batch" not in statement
    assert "MAX(captured_at)" not in statement
    assert snapshot is not None
    assert snapshot["captured_at"] == browser_captured_at.isoformat()
    assert snapshot["captured_at_by_queue_shard"] == {
        "browser_local": browser_captured_at.isoformat(),
        "vision_local": vision_captured_at.isoformat(),
    }
    assert list(snapshot["queue_depths"].keys()) == ["browser_local", "vision_local"]


@pytest.mark.asyncio
async def test_resource_console_marks_snapshot_capacity_unclaimable(monkeypatch):
    snapshot_captured_at = "2026-06-07T14:29:52.072188+00:00"

    def _snapshot(*, store=None):
        return {
            "source": "postgres_snapshot",
            "captured_at": snapshot_captured_at,
            "captured_at_by_queue_shard": {
                "default_local": snapshot_captured_at,
            },
            "queue_depths": {
                "default_local": {
                    "pending": 63,
                    "processing": 1,
                    "delayed": 0,
                    "deadletter": 0,
                },
            },
            "capacity_by_queue_shard": {
                "default_local": {
                    "active_runner_count": 1,
                    "max_inflight_total": 8,
                    "inflight_total": 0,
                    "available_slots_total": 8,
                    "utilization_ratio": 0.0,
                    "runner_ids": [],
                },
            },
            "visible_lanes": {"default_local": []},
            "visible_lane_count": {"default_local": 0},
            "degraded": False,
            "errors": [],
        }

    async def _live_utilization():
        return {
            "source": "live_redis_bounded",
            "captured_at": "2026-06-21T04:26:52.640048+00:00",
            "captured_at_by_queue_shard": {},
            "queue_depths": {},
            "capacity_by_queue_shard": {},
            "visible_lanes": {},
            "visible_lane_count": {},
            "resource_lanes": {},
            "resource_lane_count": {},
            "utilization_ratio_by_queue_shard": {},
            "scan_limit": 128,
            "degraded": False,
            "errors": [],
        }

    def _backlog(**kwargs):
        return {
            "known_queue_shards": [],
            "backlog_summary_by_queue_shard": {},
            "backlog_by_queue_shard": {},
            "active_route_lanes": {},
            "active_route_lane_count": {},
            "errors": [],
        }

    monkeypatch.setattr(queue_utilization, "get_latest_queue_utilization_snapshot", _snapshot)
    monkeypatch.setattr(queue_utilization, "build_live_queue_utilization", _live_utilization)
    monkeypatch.setattr(queue_utilization, "get_queue_backlog_aggregates", _backlog)

    merged = await queue_utilization.get_latest_queue_utilization_snapshot_with_resource_lanes()

    capacity = merged["capacity_by_queue_shard"]["default_local"]
    assert capacity["active_runner_count"] == 0
    assert capacity["max_inflight_total"] == 0
    assert capacity["available_slots_total"] == 0
    assert capacity["claimable_available_slots_total"] == 0
    assert merged["freshness_by_queue_shard"]["default_local"] == {
        "queue_depths_source": "postgres_snapshot",
        "capacity_source": "postgres_snapshot",
        "visible_lanes_source": "postgres_snapshot",
        "resource_lanes_source": "none",
        "backlog_source": "none",
        "live_captured_at": "2026-06-21T04:26:52.640048+00:00",
        "snapshot_captured_at": snapshot_captured_at,
        "stale": True,
    }
    assert (
        merged["snapshot_fallback_by_queue_shard"]["default_local"]["capacity"][
            "max_inflight_total"
        ]
        == 8
    )


@pytest.mark.asyncio
async def test_snapshot_writer_uses_single_redis_lease(monkeypatch):
    queue = FakeQueue("browser_local", ["task-a"])
    queue.client.projections[
        "mindscape:host_resources:route_identity:task-a"
    ] = projection("task-a", "ig_pin_post_detail", "ig_profile:a")
    store = FakeSnapshotStore()

    async def _heartbeats(_queue_store):
        return []

    monkeypatch.setattr(
        queue_utilization,
        "list_active_runner_resource_heartbeats",
        _heartbeats,
    )

    first = await write_queue_utilization_snapshot_if_leader(
        queue_stores=[queue],
        scan_limit=10,
        store=store,
    )
    second = await write_queue_utilization_snapshot_if_leader(
        queue_stores=[queue],
        scan_limit=10,
        store=store,
    )

    assert first["written"] is True
    assert first["inserted"] == 1
    assert second == {"written": False, "reason": "lease_held", "inserted": 0}
    assert len(store.saved) == 1
    assert store.deleted is True


def test_queue_utilization_migration_avoids_task_registry_and_task_indexes():
    repo_root = Path(__file__).resolve().parents[1]
    migration = repo_root / "alembic_migrations" / "versions" / (
        "20260528120000_create_runner_queue_capacity_snapshots.py"
    )
    source = migration.read_text(encoding="utf-8")

    assert "runner_queue_capacity_snapshots" in source
    assert "runner_queue_lock_lanes" not in source
    assert "idx_tasks_live_queue_lock_utilization" not in source
    assert "CREATE INDEX" in source
    assert "ON tasks" not in source


def test_default_queue_stores_include_dynamic_lanes(monkeypatch):
    monkeypatch.setattr(
        queue_utilization,
        "list_dynamic_queue_shards",
        lambda: ["vision_mlx_high", "vision_local"],
    )

    stores = queue_utilization._default_queue_stores()

    assert [store.pack_id for store in stores] == [
        "vision_local",
        "browser_local",
        "default_local_browser",
        "default_local",
        "vision_mlx_high",
    ]
