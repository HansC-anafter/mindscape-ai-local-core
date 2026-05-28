from pathlib import Path

import pytest

from backend.app.services.host_resources import queue_utilization
from backend.app.services.host_resources.queue_utilization import (
    build_live_queue_utilization,
    write_queue_utilization_snapshot_if_leader,
)
from backend.app.services.host_resources.route_identity_projection import (
    serialize_route_identity_projection,
)


class _FakeRedisClient:
    def __init__(self, pending_ids):
        self.pending_ids = list(pending_ids)
        self.projections = {}
        self.llen_values = {}
        self.zcard_values = {}
        self.lrange_calls = []
        self.lease_available = True
        self.set_calls = []

    async def lrange(self, key, start, end):
        self.lrange_calls.append((key, start, end))
        return self.pending_ids[start : end + 1]

    async def mget(self, keys):
        return [self.projections.get(key) for key in keys]

    async def llen(self, key):
        return self.llen_values.get(key, 0)

    async def zcard(self, key):
        return self.zcard_values.get(key, 0)

    async def set(self, key, value, nx=False, ex=None):
        self.set_calls.append((key, value, nx, ex))
        if not self.lease_available:
            return False
        self.lease_available = False
        return True


class _FakeQueue:
    def __init__(self, pack_id, pending_ids):
        self.pack_id = pack_id
        self.q_pending = f"pending:{pack_id}"
        self.q_processing = f"processing:{pack_id}"
        self.q_delayed = f"delayed:{pack_id}"
        self.q_deadletter = f"deadletter:{pack_id}"
        self.client = _FakeRedisClient(pending_ids)
        self.client.llen_values[self.q_pending] = len(pending_ids)
        self.client.llen_values[self.q_deadletter] = 0
        self.client.zcard_values[self.q_processing] = 2
        self.client.zcard_values[self.q_delayed] = 1

    async def _get_client(self):
        return self.client


class _FakeSnapshotStore:
    def __init__(self):
        self.saved = []
        self.deleted = False

    def save_snapshot_batch(self, snapshot):
        self.saved.append(snapshot)
        return len(snapshot["queue_depths"])

    def delete_old_snapshots(self):
        self.deleted = True
        return 0


def _projection(task_id, pack_id, concurrency_key):
    return serialize_route_identity_projection(
        task_id,
        {
            "task_id": task_id,
            "pack_id": pack_id,
            "playbook_code": pack_id,
            "queue_shard": "browser_local",
            "concurrency_key": concurrency_key,
            "route_identity": {
                "lane_id": "runner:browser_local",
                "resource_groups": ["browser_local"],
                "priority_class": "default",
                "pack_id": pack_id,
                "playbook_code": pack_id,
            },
        },
    )


@pytest.mark.asyncio
async def test_live_queue_utilization_uses_bounded_redis_data(monkeypatch):
    queue = _FakeQueue(
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
        ] = _projection(task_id, "ig_pin_post_detail", lock_key)

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


@pytest.mark.asyncio
async def test_snapshot_writer_uses_single_redis_lease(monkeypatch):
    queue = _FakeQueue("browser_local", ["task-a"])
    queue.client.projections[
        "mindscape:host_resources:route_identity:task-a"
    ] = _projection("task-a", "ig_pin_post_detail", "ig_profile:a")
    store = _FakeSnapshotStore()

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
