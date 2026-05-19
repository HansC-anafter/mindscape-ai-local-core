from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from backend.app.models.workspace import Task, TaskStatus
from backend.app.runner import task_executor
from backend.app.runner.worker import _cleanup_stale_locks, _reset_orphaned_running_tasks
from backend.app.services.runner_topology.partitions import (
    BROWSER_LOCAL_QUEUE_PARTITION,
    VISION_LOCAL_QUEUE_PARTITION,
)
from backend.app.services.runner_topology.profile_registry import (
    RESOURCE_CLASS_BROWSER,
    RESOURCE_CLASS_COMPUTE,
    RunnerProfile,
)


def _task(task_id: str, *, runner_id: str, queue_shard: str, resource_class: str) -> Task:
    return Task(
        id=task_id,
        workspace_id="workspace-1",
        message_id=f"msg-{task_id}",
        execution_id=task_id,
        pack_id="ig_analyze_pinned_reference",
        task_type="playbook_execution",
        status=TaskStatus.RUNNING,
        queue_shard=queue_shard,
        execution_context={
            "playbook_code": "ig_analyze_pinned_reference",
            "queue_shard": queue_shard,
            "resource_class": resource_class,
            "runner_id": runner_id,
        },
        created_at=datetime.now(timezone.utc),
    )


class _FakeTasksStore:
    def __init__(self, tasks, heartbeats):
        self._tasks = tasks
        self._heartbeats = heartbeats
        self.updated = []

    def list_runner_heartbeats(self, *, max_age_seconds=None, limit=50):
        return self._heartbeats

    def list_running_playbook_execution_tasks(self, workspace_id=None, limit=500):
        return self._tasks

    def update_task(self, task_id, **updates):
        self.updated.append((task_id, updates))


class _FakeRedisQueue:
    def __init__(self):
        self.released = []

    async def release_lock(self, lock_key, owner_id):
        self.released.append((lock_key, owner_id))
        return True


class _FakeRedisClient:
    def __init__(self, locks):
        self.locks = dict(locks)
        self.deleted = []

    async def scan_iter(self, match):
        prefix = match.removesuffix("*")
        for key in list(self.locks):
            if key.startswith(prefix):
                yield key

    async def get(self, key):
        return self.locks.get(key)

    async def delete(self, key):
        self.deleted.append(key)
        return 1 if self.locks.pop(key, None) is not None else 0


class _FakeRedisQueueWithClient:
    def __init__(self, client):
        self.client = client

    async def _get_client(self):
        return self.client


@pytest.mark.asyncio
async def test_startup_reset_skips_running_task_owned_by_active_runner():
    store = _FakeTasksStore(
        [
            _task(
                "vision-task",
                runner_id="vision-runner",
                queue_shard=VISION_LOCAL_QUEUE_PARTITION,
                resource_class=RESOURCE_CLASS_COMPUTE,
            )
        ],
        [{"runner_id": "vision-runner"}],
    )
    profile = RunnerProfile(
        profile_code="browser_local",
        display_name="Browser Local Runner",
        dispatch_mode="docker_local",
        accepted_queue_partitions=(BROWSER_LOCAL_QUEUE_PARTITION,),
        accepted_resource_classes=(RESOURCE_CLASS_BROWSER,),
    )

    reset = await _reset_orphaned_running_tasks(store, "browser-runner", profile)

    assert reset == set()
    assert store.updated == []


@pytest.mark.asyncio
async def test_startup_reset_skips_task_for_another_runner_profile():
    store = _FakeTasksStore(
        [
            _task(
                "vision-task",
                runner_id="stale-vision-runner",
                queue_shard=VISION_LOCAL_QUEUE_PARTITION,
                resource_class=RESOURCE_CLASS_COMPUTE,
            )
        ],
        [],
    )
    profile = RunnerProfile(
        profile_code="browser_local",
        display_name="Browser Local Runner",
        dispatch_mode="docker_local",
        accepted_queue_partitions=(BROWSER_LOCAL_QUEUE_PARTITION,),
        accepted_resource_classes=(RESOURCE_CLASS_BROWSER,),
    )

    reset = await _reset_orphaned_running_tasks(store, "browser-runner", profile)

    assert reset == set()
    assert store.updated == []


@pytest.mark.asyncio
async def test_startup_reset_keeps_same_profile_stale_runner_recovery():
    store = _FakeTasksStore(
        [
            _task(
                "browser-task",
                runner_id="stale-browser-runner",
                queue_shard=BROWSER_LOCAL_QUEUE_PARTITION,
                resource_class=RESOURCE_CLASS_BROWSER,
            )
        ],
        [],
    )
    profile = RunnerProfile(
        profile_code="browser_local",
        display_name="Browser Local Runner",
        dispatch_mode="docker_local",
        accepted_queue_partitions=(BROWSER_LOCAL_QUEUE_PARTITION,),
        accepted_resource_classes=(RESOURCE_CLASS_BROWSER,),
    )

    reset = await _reset_orphaned_running_tasks(store, "browser-runner", profile)

    assert reset == {"browser-task"}
    assert store.updated[0][0] == "browser-task"
    assert store.updated[0][1]["status"] == TaskStatus.PENDING


@pytest.mark.asyncio
async def test_startup_lock_cleanup_keeps_active_peer_runner_task_lock():
    store = _FakeTasksStore([], [{"runner_id": "browser-runner"}])
    client = _FakeRedisClient(
        {
            "concurrency:playbook_input:ig_batch_pin_references:/profile": (
                "browser-runner:browser-task"
            ),
            "concurrency:playbook:ig_analyze_pinned_reference": (
                "vision-runner:vision-task"
            ),
        }
    )

    await _cleanup_stale_locks(
        _FakeRedisQueueWithClient(client),
        "vision-runner",
        store,
    )

    assert client.deleted == []
    assert set(client.locks) == {
        "concurrency:playbook_input:ig_batch_pin_references:/profile",
        "concurrency:playbook:ig_analyze_pinned_reference",
    }


@pytest.mark.asyncio
async def test_startup_lock_cleanup_deletes_stale_runner_lock():
    store = _FakeTasksStore([], [{"runner_id": "vision-runner"}])
    client = _FakeRedisClient(
        {
            "concurrency:playbook_input:ig_batch_pin_references:/profile": (
                "stale-browser-runner:browser-task"
            ),
        }
    )

    await _cleanup_stale_locks(
        _FakeRedisQueueWithClient(client),
        "vision-runner",
        store,
    )

    assert client.deleted == [
        "concurrency:playbook_input:ig_batch_pin_references:/profile"
    ]
    assert client.locks == {}


@pytest.mark.asyncio
async def test_startup_lock_cleanup_deletes_stale_profile_alias_lock():
    store = _FakeTasksStore([], [{"runner_id": "browser-runner"}])
    client = _FakeRedisClient(
        {
            "ig_profile:/app/data/ig-browser-profiles/anafter.300_": (
                "stale-browser-runner:following-task"
            ),
        }
    )

    await _cleanup_stale_locks(
        _FakeRedisQueueWithClient(client),
        "browser-runner",
        store,
    )

    assert client.deleted == [
        "ig_profile:/app/data/ig-browser-profiles/anafter.300_"
    ]
    assert client.locks == {}


@pytest.mark.asyncio
async def test_single_task_releases_lock_with_task_scoped_owner(monkeypatch):
    task = _task(
        "pin-task",
        runner_id="vision-runner",
        queue_shard=VISION_LOCAL_QUEUE_PARTITION,
        resource_class=RESOURCE_CLASS_COMPUTE,
    )
    task.execution_context["concurrency"] = {"lock_scope": "playbook"}
    store = SimpleNamespace(get_task=lambda task_id: task)
    redis_queue = _FakeRedisQueue()

    monkeypatch.setattr(
        task_executor,
        "_resolve_execution_attempt_inputs",
        lambda _task, _ctx: ({}, SimpleNamespace(park_task=True)),
    )

    async def _park_noop(*args, **kwargs):
        return None

    monkeypatch.setattr(
        task_executor,
        "_park_task_after_intent_resolution",
        _park_noop,
    )

    await task_executor._run_single_task(
        store,
        "vision-runner",
        "pin-task",
        redis_queue=redis_queue,
        lock_owner_id="vision-runner:pin-task",
    )

    assert redis_queue.released == [
        ("concurrency:playbook:ig_analyze_pinned_reference", "vision-runner:pin-task")
    ]
