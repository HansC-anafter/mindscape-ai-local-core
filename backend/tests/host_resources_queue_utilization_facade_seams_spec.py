import pytest

from backend.app.services.host_resources import queue_utilization


class _Queue:
    pack_id = "browser_local"


class _Store:
    def __init__(self):
        self.saved = []
        self.deleted = False

    def save_snapshot_batch(self, snapshot):
        self.saved.append(snapshot)
        return 1

    def delete_old_snapshots(self):
        self.deleted = True
        return 0


def test_default_queue_stores_uses_facade_dynamic_lane_hook(monkeypatch):
    observed = {}

    class _QueueStore:
        def __init__(self, pack_id):
            self.pack_id = pack_id

    def _dynamic_lanes():
        observed["called"] = True
        return ["extra_lane", "browser_local"]

    monkeypatch.setattr(queue_utilization, "RedisRunnerQueueStore", _QueueStore)
    monkeypatch.setattr(queue_utilization, "list_dynamic_queue_shards", _dynamic_lanes)

    stores = queue_utilization._default_queue_stores()

    assert observed["called"] is True
    assert [store.pack_id for store in stores] == [
        "vision_local",
        "browser_local",
        "default_local",
        "extra_lane",
    ]


@pytest.mark.asyncio
async def test_live_builder_uses_facade_heartbeat_hook(monkeypatch):
    async def _heartbeats(queue_store):
        return [
            {
                "runner_id": "runner-a",
                "queue_shards": [queue_store.pack_id],
                "capacity": {
                    "max_inflight": 4,
                    "inflight": 1,
                    "available_slots": 3,
                },
            }
        ]

    monkeypatch.setattr(
        queue_utilization,
        "list_active_runner_resource_heartbeats",
        _heartbeats,
    )

    snapshot = await queue_utilization.build_live_queue_utilization(
        queue_stores=[_Queue()],
        scan_limit=1,
        now_epoch=1000,
    )

    assert snapshot["capacity_by_queue_shard"]["browser_local"][
        "max_inflight_total"
    ] == 4


@pytest.mark.asyncio
async def test_writer_uses_facade_lease_build_and_store_hooks(monkeypatch):
    observed = {}
    store = _Store()

    async def _lease(queue_store):
        observed["lease_store"] = queue_store
        return True

    async def _build(**kwargs):
        observed["build_kwargs"] = kwargs
        return {
            "queue_depths": {"browser_local": {"pending": 1}},
            "capacity_by_queue_shard": {},
            "visible_lanes": {},
        }

    monkeypatch.setattr(queue_utilization, "_acquire_snapshot_writer_lease", _lease)
    monkeypatch.setattr(queue_utilization, "build_live_queue_utilization", _build)
    monkeypatch.setattr(queue_utilization, "QueueUtilizationSnapshotStore", lambda: store)

    queue = _Queue()
    result = await queue_utilization.write_queue_utilization_snapshot_if_leader(
        queue_stores=[queue],
        scan_limit=7,
    )

    assert observed["lease_store"] is queue
    assert observed["build_kwargs"] == {"queue_stores": [queue], "scan_limit": 7}
    assert store.saved == [
        {
            "queue_depths": {"browser_local": {"pending": 1}},
            "capacity_by_queue_shard": {},
            "visible_lanes": {},
        }
    ]
    assert store.deleted is True
    assert result["written"] is True
    assert result["inserted"] == 1
