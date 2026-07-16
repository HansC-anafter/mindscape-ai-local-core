from datetime import timedelta
import time

import pytest

from backend.app.models.workspace import Task, TaskStatus, _utc_now
from backend.app.runner import reaper


class _FakeRedisClient:
    def __init__(self):
        self.pending_members: list[str] = []
        self.temp_members: list[str] = []
        self.processing_members: list[str] = []
        self.delayed_members: list[str] = []

    async def zrangebyscore(self, queue_name, _minimum, _maximum, start=None, num=None):
        if "delayed" in queue_name:
            return list(self.delayed_members)
        return []

    async def lrange(self, queue_name, _start, _end):
        if "pending" in queue_name:
            return list(self.pending_members)
        if "temp" in queue_name:
            return list(self.temp_members)
        return []

    async def zrange(self, queue_name, _start, _end):
        if "processing" in queue_name:
            return list(self.processing_members)
        if "delayed" in queue_name:
            return list(self.delayed_members)
        return []

    async def llen(self, _queue_name):
        return len(self.pending_members)


class _FakeRedisQueue:
    def __init__(self, client, pack_id="vision_local"):
        self.pack_id = pack_id
        self.q_pending = f"mindscape:queue:pending:{pack_id}"
        self.q_temp = f"mindscape:queue:temp:{pack_id}"
        self.q_processing = f"mindscape:queue:processing:{pack_id}"
        self.q_delayed = f"mindscape:queue:delayed:{pack_id}"
        self._client = client
        self.enqueued: list[tuple[str, dict]] = []

    async def _get_client(self):
        return self._client

    async def enqueue_task(self, task_id, route_identity=None):
        self.enqueued.append((task_id, route_identity or {}))
        self._client.pending_members.insert(0, task_id)
        return True

    def _utc_now_timestamp(self):
        return time.time()


class _FakeTasksStore:
    def __init__(self, tasks):
        self.tasks = list(tasks)
        self.updated: list[tuple[str, dict]] = []
        self.runnable_calls = 0

    def list_runnable_playbook_execution_tasks(
        self,
        workspace_id=None,
        limit=500,
        queue_shard=None,
    ):
        self.runnable_calls += 1
        return [
            task
            for task in self.tasks
            if task.status == TaskStatus.PENDING
            and getattr(task, "frontier_state", None) == "ready"
            and getattr(task, "queue_shard", None) == queue_shard
        ][:limit]

    def update_task(self, task_id, **kwargs):
        self.updated.append((task_id, kwargs))


async def _zero(*_args, **_kwargs):
    return 0


def _ready_task(task_id: str, queue_shard="vision_local") -> Task:
    now = _utc_now()
    return Task(
        id=task_id,
        workspace_id="ws-1",
        message_id="msg-1",
        execution_id="exec-1",
        pack_id="ig_analyze_pinned_reference",
        task_type="playbook_execution",
        status=TaskStatus.PENDING,
        queue_shard=queue_shard,
        concurrency_key="concurrency:playbook:ig_analyze_pinned_reference",
        created_at=now - timedelta(minutes=10),
        next_eligible_at=now - timedelta(minutes=10),
        frontier_state="ready",
        execution_context={
            "playbook_code": "ig_analyze_pinned_reference",
            "queue_shard": queue_shard,
        },
    )


@pytest.mark.asyncio
async def test_ready_db_frontier_refills_before_blocked_release(monkeypatch):
    release_calls: list[str] = []

    async def _blocked_release_called(*_args, **_kwargs):
        release_calls.append("blocked_release")
        return 64

    monkeypatch.setenv("LOCAL_CORE_RUNNER_READY_TARGET", "64")
    monkeypatch.setattr(reaper, "_reconcile_temp_transport_items", _zero)
    monkeypatch.setattr(reaper, "_scrub_processing_terminal_items", _zero)
    monkeypatch.setattr(reaper, "_release_concurrency_locked_tasks", _blocked_release_called)
    monkeypatch.setattr(reaper, "_release_dependency_hold_tasks", _blocked_release_called)
    monkeypatch.setattr(reaper, "_release_resource_wait_tasks", _blocked_release_called)
    monkeypatch.setattr(reaper, "_release_workspace_quota_tasks", _blocked_release_called)
    monkeypatch.setattr(reaper, "_release_admission_deferred_tasks", _blocked_release_called)
    monkeypatch.setattr(reaper, "_release_unblocked_cold_tasks", _blocked_release_called)
    monkeypatch.setattr(reaper, "_refill_browser_peer_frontier", _zero)

    store = _FakeTasksStore([_ready_task("ready-task-1")])
    client = _FakeRedisClient()
    queue = _FakeRedisQueue(client)

    await reaper._reap_redis_queues(store, queue)

    assert [task_id for task_id, _route in queue.enqueued] == ["ready-task-1"]
    assert store.runnable_calls == 1
    assert store.updated[0][0] == "ready-task-1"
    assert release_calls == []


@pytest.mark.asyncio
async def test_browser_ready_refill_continues_bounded_blocked_release(monkeypatch):
    release_calls: list[tuple[str, int]] = []

    async def _record_release(name, *_args, release_limit, **_kwargs):
        release_calls.append((name, release_limit))
        return 0

    async def _concurrency(*args, **kwargs):
        return await _record_release("concurrency", *args, **kwargs)

    async def _dependency(*args, **kwargs):
        return await _record_release("dependency", *args, **kwargs)

    async def _resource(*args, **kwargs):
        return await _record_release("resource", *args, **kwargs)

    monkeypatch.setenv("LOCAL_CORE_RUNNER_READY_TARGET", "1")
    monkeypatch.setenv("LOCAL_CORE_RUNNER_BLOCKED_RELEASE_MINIMUM", "4")
    monkeypatch.setattr(reaper, "_reconcile_temp_transport_items", _zero)
    monkeypatch.setattr(reaper, "_scrub_processing_terminal_items", _zero)
    monkeypatch.setattr(reaper, "_release_concurrency_locked_tasks", _concurrency)
    monkeypatch.setattr(reaper, "_release_dependency_hold_tasks", _dependency)
    monkeypatch.setattr(reaper, "_release_resource_wait_tasks", _resource)
    monkeypatch.setattr(reaper, "_release_workspace_quota_tasks", _zero)
    monkeypatch.setattr(reaper, "_release_admission_deferred_tasks", _zero)
    monkeypatch.setattr(reaper, "_release_unblocked_cold_tasks", _zero)
    monkeypatch.setattr(reaper, "_refill_browser_peer_frontier", _zero)

    store = _FakeTasksStore(
        [_ready_task("ready-browser-1", queue_shard="browser_local")]
    )
    client = _FakeRedisClient()
    queue = _FakeRedisQueue(client, pack_id="browser_local")

    await reaper._reap_redis_queues(store, queue)

    assert [task_id for task_id, _route in queue.enqueued] == ["ready-browser-1"]
    assert release_calls == [
        ("concurrency", 4),
        ("dependency", 4),
        ("resource", 4),
    ]


@pytest.mark.asyncio
async def test_browser_saturated_ready_frontier_still_checks_resource_wait(monkeypatch):
    release_calls: list[tuple[str, int]] = []

    async def _record_release(name, *_args, release_limit, **_kwargs):
        release_calls.append((name, release_limit))
        return 0

    async def _concurrency(*args, **kwargs):
        return await _record_release("concurrency", *args, **kwargs)

    async def _dependency(*args, **kwargs):
        return await _record_release("dependency", *args, **kwargs)

    async def _resource(*args, **kwargs):
        return await _record_release("resource", *args, **kwargs)

    monkeypatch.setenv("LOCAL_CORE_RUNNER_READY_TARGET", "1")
    monkeypatch.setattr(reaper, "_reconcile_temp_transport_items", _zero)
    monkeypatch.setattr(reaper, "_scrub_processing_terminal_items", _zero)
    monkeypatch.setattr(reaper, "_release_concurrency_locked_tasks", _concurrency)
    monkeypatch.setattr(reaper, "_release_dependency_hold_tasks", _dependency)
    monkeypatch.setattr(reaper, "_release_resource_wait_tasks", _resource)
    monkeypatch.setattr(reaper, "_release_workspace_quota_tasks", _zero)
    monkeypatch.setattr(reaper, "_release_admission_deferred_tasks", _zero)
    monkeypatch.setattr(reaper, "_release_unblocked_cold_tasks", _zero)
    monkeypatch.setattr(reaper, "_refill_browser_peer_frontier", _zero)

    store = _FakeTasksStore([])
    client = _FakeRedisClient()
    client.pending_members = [f"ready-{index}" for index in range(20)]
    queue = _FakeRedisQueue(client, pack_id="browser_local")

    await reaper._reap_redis_queues(store, queue)

    assert release_calls == [
        ("concurrency", 0),
        ("dependency", 0),
        ("resource", 4),
    ]
