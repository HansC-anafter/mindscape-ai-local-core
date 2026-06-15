from datetime import timedelta
import time

import pytest

from backend.app.models.workspace import Task, TaskStatus, _utc_now
from backend.app.runner import reaper


class _FakeRedisClient:
    def __init__(self, delayed_items):
        self.delayed_items = delayed_items
        self.zremoved: list[tuple[str, bytes]] = []

    async def zrangebyscore(self, queue_name, _minimum, _maximum, start=None, num=None):
        if "delayed" in queue_name:
            return list(self.delayed_items)
        return []

    async def zrem(self, queue_name, task_id):
        self.zremoved.append((queue_name, task_id))
        return 1

    async def llen(self, _queue_name):
        return 0


class _FakeRedisQueue:
    def __init__(self, client):
        self.pack_id = "vision_local"
        self.q_pending = "mindscape:queue:pending:vision_local"
        self.q_processing = "mindscape:queue:processing:vision_local"
        self.q_delayed = "mindscape:queue:delayed:vision_local"
        self.q_temp = "mindscape:queue:temp:vision_local"
        self.enqueued: list[tuple[str, dict]] = []
        self._client = client

    async def _get_client(self):
        return self._client

    async def enqueue_task(self, task_id, route_identity=None):
        self.enqueued.append((task_id, route_identity or {}))
        return True

    def _utc_now_timestamp(self):
        return time.time()


class _FakeTasksStore:
    def __init__(self, task):
        self.task = task
        self.updated: list[tuple[str, dict]] = []

    def get_task(self, task_id):
        if self.task and self.task.id == task_id:
            return self.task
        return None

    def update_task(self, task_id, **kwargs):
        self.updated.append((task_id, kwargs))


class _UnreadableTasksStore(_FakeTasksStore):
    def get_task(self, task_id):
        raise ValueError("'cancelled' is not a valid TaskStatus")


async def _no_reaper_work(*_args, **_kwargs):
    return 0


def _disable_follow_up_work(monkeypatch):
    monkeypatch.setenv("LOCAL_CORE_RUNNER_READY_TARGET", "0")
    for name in (
        "_reconcile_temp_transport_items",
        "_scrub_processing_terminal_items",
        "_release_concurrency_locked_tasks",
        "_release_dependency_hold_tasks",
        "_release_resource_wait_tasks",
        "_release_workspace_quota_tasks",
        "_release_admission_deferred_tasks",
        "_release_unblocked_cold_tasks",
        "_refill_browser_peer_frontier",
    ):
        monkeypatch.setattr(reaper, name, _no_reaper_work)


def _task(status: TaskStatus):
    now = _utc_now()
    return Task(
        id="task-1",
        workspace_id="ws-1",
        message_id="msg-1",
        execution_id="exec-1",
        pack_id="ig_analyze_pinned_reference",
        task_type="playbook_execution",
        status=status,
        queue_shard="vision_local",
        created_at=now,
        next_eligible_at=now - timedelta(seconds=1),
        frontier_state="done" if status != TaskStatus.PENDING else "ready",
        execution_context={"status": "queued"},
    )


@pytest.mark.asyncio
async def test_delayed_queue_mover_scrubs_terminal_task_without_requeue(monkeypatch):
    _disable_follow_up_work(monkeypatch)
    store = _FakeTasksStore(_task(TaskStatus.CANCELLED_BY_USER))
    client = _FakeRedisClient(delayed_items=[b"task-1"])
    queue = _FakeRedisQueue(client)

    await reaper._reap_redis_queues(store, queue)

    assert (queue.q_delayed, b"task-1") in client.zremoved
    assert queue.enqueued == []
    assert store.updated == []


@pytest.mark.asyncio
async def test_delayed_queue_mover_scrubs_unreadable_task_without_requeue(monkeypatch):
    _disable_follow_up_work(monkeypatch)
    store = _UnreadableTasksStore(None)
    client = _FakeRedisClient(delayed_items=[b"legacy-cancelled"])
    queue = _FakeRedisQueue(client)

    await reaper._reap_redis_queues(store, queue)

    assert (queue.q_delayed, b"legacy-cancelled") in client.zremoved
    assert queue.enqueued == []
