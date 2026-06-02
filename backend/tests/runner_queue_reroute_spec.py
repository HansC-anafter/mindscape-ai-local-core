import pytest

from backend.app.services.runner_topology import queue_reroute
from backend.app.services.stores.redis import runner_queue_store
from backend.app.services.stores.redis.runner_queue_store import RedisRunnerQueueStore


class _FakeRedisClient:
    def __init__(self, result):
        self.result = result
        self.eval_calls = []

    async def eval(self, *args):
        self.eval_calls.append(args)
        return self.result


@pytest.mark.asyncio
async def test_redis_runner_queue_store_reroute_uses_single_lua_call(monkeypatch):
    client = _FakeRedisClient([2, 1])

    async def _get_client(self):
        return client

    monkeypatch.setattr(RedisRunnerQueueStore, "_get_client", _get_client)
    store = RedisRunnerQueueStore(pack_id="vision_mlx_high")

    result = await store.reroute_pending_task(
        "task-1",
        source_shards=["vision_local", "default_local"],
        route_identity={"route_identity": {"lane_id": "runner:vision_mlx_high"}},
    )

    assert result == {"removed_count": 2, "pushed": True}
    assert len(client.eval_calls) == 1
    call = client.eval_calls[0]
    assert call[0] == runner_queue_store.LUA_REROUTE_PENDING
    assert call[1] == 4
    assert call[3] == "mindscape:queue:pending:vision_mlx_high"
    assert call[-3] == "task-1"


@pytest.mark.asyncio
async def test_queue_reroute_reports_source_miss_without_enqueue(monkeypatch):
    class _Queue:
        def __init__(self, pack_id):
            self.pack_id = pack_id

        async def reroute_pending_task(self, task_id, *, source_shards, route_identity=None):
            return {"removed_count": 0, "pushed": False}

    monkeypatch.setattr(queue_reroute, "RedisRunnerQueueStore", _Queue)
    monkeypatch.setattr(queue_reroute, "registered_pending_queue_shards", lambda: ["vision_local"])

    result = await queue_reroute.reroute_pending_task(
        "task-missing",
        target_shard="vision_mlx_high",
        route_identity={"route_identity": {"lane_id": "runner:vision_mlx_high"}},
    )

    assert result.as_dict() == {
        "task_id": "task-missing",
        "target_shard": "vision_mlx_high",
        "removed_count": 0,
        "pushed": False,
        "reason": "skipped_not_in_pending_queue",
    }
