from types import SimpleNamespace

import pytest

from backend.app.models.workspace import TaskStatus
from backend.app.runner import worker_startup
from backend.app.runner.worker_dispatch import _dispatch_claimed_task


class _FakeTasksStore:
    def __init__(self, task=None):
        self.task = task

    def get_task(self, task_id):
        return self.task

    def list_runner_heartbeats(self, *, max_age_seconds, limit):
        return [{"runner_id": "runner-from-postgres"}]


class _FakeQueue:
    def __init__(self):
        self.touched = []
        self.acked = []
        self.delayed = []

    async def touch_visibility_timeout(self, task_id, *, added_time_sec):
        self.touched.append((task_id, added_time_sec))

    async def ack_task(self, task_id):
        self.acked.append(task_id)

    async def nack_task_to_delayed(self, task_id, *, delay_sec):
        self.delayed.append((task_id, delay_sec))


class _FakeBackoff:
    delay_seconds = 30

    def note_failure(self, exc):
        return False

    def is_active(self):
        return False


@pytest.mark.asyncio
async def test_load_active_runner_ids_falls_back_after_redis_heartbeat_failure(
    monkeypatch,
):
    async def failing_redis_heartbeats(_redis_queue):
        raise RuntimeError("redis unavailable")

    monkeypatch.setattr(
        worker_startup,
        "list_active_runner_resource_heartbeats",
        failing_redis_heartbeats,
    )

    active_runner_ids = await worker_startup._load_active_runner_ids(
        object(),
        _FakeTasksStore(),
        max_age_seconds=120,
    )

    assert active_runner_ids == {"runner-from-postgres"}


@pytest.mark.asyncio
async def test_dispatch_touches_running_duplicate_visibility_timeout():
    task = SimpleNamespace(
        id="task-running",
        status=TaskStatus.RUNNING,
        pack_id="ig_analyze_following",
    )
    queue = _FakeQueue()

    dispatch_task = await _dispatch_claimed_task(
        "task-running",
        queue,
        tasks_store=_FakeTasksStore(task),
        runner_id="runner-a",
        redis_queue=queue,
        runner_profile=object(),
        db_budget=object(),
        resource_snapshot=None,
        capacity=object(),
        dep_checker=object(),
        visibility_timeout_sec=240,
        lock_ttl_seconds=120,
        db_recovery_backoff=_FakeBackoff(),
    )

    assert dispatch_task is None
    assert queue.touched == [("task-running", 240)]
    assert queue.acked == []
    assert queue.delayed == []
