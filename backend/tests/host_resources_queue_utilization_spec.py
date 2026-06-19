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


class _FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows


class _FakeConnection:
    def __init__(self, rows):
        self.rows = rows
        self.statements = []

    def execute(self, statement, *args, **kwargs):
        self.statements.append(str(statement))
        return _FakeResult(self.rows)


class _FakeConnectionContext:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self.connection

    def __exit__(self, exc_type, exc, tb):
        return False


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
async def test_live_queue_utilization_excludes_drain_runner_available_slots(monkeypatch):
    queue = _FakeQueue("browser_local", ["task-a"])
    queue.client.projections[
        "mindscape:host_resources:route_identity:task-a"
    ] = _projection("task-a", "ig_pin_post_detail", "ig_profile:a")

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


def test_latest_snapshot_reads_one_latest_batch(monkeypatch):
    captured_at = datetime(2026, 6, 20, 4, 40, tzinfo=timezone.utc)
    rows = [
        {
            "captured_at": captured_at,
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
            "captured_at": captured_at,
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
    connection = _FakeConnection(rows)
    store = object.__new__(QueueUtilizationSnapshotStore)
    monkeypatch.setattr(
        store,
        "get_connection",
        lambda: _FakeConnectionContext(connection),
    )

    snapshot = store.latest_snapshot()

    statement = connection.statements[0]
    assert "latest_batch" in statement
    assert "MAX(captured_at)" in statement
    assert "DISTINCT ON" not in statement
    assert snapshot is not None
    assert snapshot["captured_at"] == captured_at.isoformat()
    assert snapshot["captured_at_by_queue_shard"] == {
        "browser_local": captured_at.isoformat(),
        "vision_local": captured_at.isoformat(),
    }
    assert list(snapshot["queue_depths"].keys()) == ["browser_local", "vision_local"]


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
        "default_local",
        "vision_mlx_high",
    ]
