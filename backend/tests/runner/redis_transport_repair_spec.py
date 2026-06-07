from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from backend.app.models.workspace import TaskStatus
from backend.app.runner.redis_transport_repair import (
    reconcile_transport_membership,
    recycle_visibility_timeout_item,
)
from backend.app.services.stores.redis.runner_queue_store import RedisRunnerQueueStore


class _FakePipeline:
    def __init__(self):
        self.calls = []

    def lrem(self, *args):
        self.calls.append(("lrem", args))

    def zrem(self, *args):
        self.calls.append(("zrem", args))

    def lpush(self, *args):
        self.calls.append(("lpush", args))

    async def execute(self):
        return [1] * len(self.calls)


class _FakeClient:
    def __init__(self):
        self.pipeline_instance = _FakePipeline()
        self.zadd_calls = []

    def pipeline(self):
        return self.pipeline_instance

    async def zadd(self, *args):
        self.zadd_calls.append(args)
        return 1


async def _return_client(client):
    return client


@pytest.mark.asyncio
async def test_reconcile_transport_membership_removes_all_transport_lists_and_requeues():
    queue = RedisRunnerQueueStore(pack_id="browser_local")
    client = _FakeClient()
    queue._get_client = lambda: _return_client(client)

    await reconcile_transport_membership(
        queue,
        task_id="task-1",
        reenqueue_pending=True,
    )

    calls = client.pipeline_instance.calls
    assert ("lrem", (queue.q_pending, 0, "task-1")) in calls
    assert ("lrem", (queue.q_temp, 0, "task-1")) in calls
    assert ("zrem", (queue.q_processing, "task-1")) in calls
    assert ("zrem", (queue.q_delayed, "task-1")) in calls
    assert ("lpush", (queue.q_pending, "task-1")) in calls


@pytest.mark.asyncio
async def test_touch_visibility_timeout_writes_processing_deadline_without_existing_score_gate():
    queue = RedisRunnerQueueStore(pack_id="browser_local")
    client = _FakeClient()
    queue._get_client = lambda: _return_client(client)

    touched = await queue.touch_visibility_timeout("task-1", added_time_sec=60)

    assert touched is True
    assert client.zadd_calls
    key, mapping = client.zadd_calls[0]
    assert key == queue.q_processing
    assert "task-1" in mapping


@pytest.mark.asyncio
async def test_recycle_visibility_timeout_requeues_stale_running_task():
    now = datetime.now(timezone.utc)
    task = SimpleNamespace(
        status=TaskStatus.RUNNING,
        execution_context={"status": "running", "heartbeat_at": (now - timedelta(minutes=10)).isoformat()},
        queue_shard="browser_local",
    )
    updates = []
    reconciled = []
    queue = RedisRunnerQueueStore(pack_id="browser_local")
    client = _FakeClient()
    queue._get_client = lambda: _return_client(client)
    store = SimpleNamespace(
        get_task=lambda task_id: task,
        update_task=lambda task_id, **kwargs: updates.append((task_id, kwargs)),
    )

    async def reconcile_membership(*args, **kwargs):
        reconciled.append((args, kwargs))

    result = await recycle_visibility_timeout_item(
        tasks_store=store,
        redis_queue=queue,
        task_id="task-1",
        now_dt=now,
        stale_limit=now - timedelta(minutes=3),
        effective_heartbeat_at=lambda _task, _ctx: now - timedelta(minutes=10),
        reconcile_membership=reconcile_membership,
    )

    assert result == "requeued"
    assert updates[0][0] == "task-1"
    assert updates[0][1]["status"] == TaskStatus.PENDING
    assert updates[0][1]["frontier_state"] == "ready"
    assert reconciled[0][1]["reenqueue_pending"] is True
