from datetime import timedelta

import pytest

from backend.app.models.workspace import Task, TaskStatus, _utc_now
from backend.app.runner import reaper
from backend.app.runner.concurrency import (
    _release_lock_keys_safely,
    _runner_lock_ttl_seconds,
)


class _FakePipeline:
    def __init__(self, client):
        self.client = client
        self._pending: list[str] = []

    def lpush(self, _queue_name, task_id):
        self._pending.append(task_id)

    async def execute(self):
        self.client.enqueued.extend(self._pending)


class _FakeRedisClient:
    def __init__(self):
        self.enqueued: list[str] = []

    def pipeline(self):
        return _FakePipeline(self)


class _FakeRedisQueue:
    def __init__(self, pack_id: str, owners: dict[str, str | None] | None = None):
        self.pack_id = pack_id
        self.q_pending = f"{pack_id}:pending"
        self._client = _FakeRedisClient()
        self.owners = dict(owners or {})
        self.released: list[tuple[str, str]] = []
        self.force_released: list[str] = []
        self.release_results: dict[tuple[str, str], bool] = {}

    async def _get_client(self):
        return self._client

    async def get_lock_owner(self, lock_key: str):
        return self.owners.get(lock_key)

    async def release_lock(self, lock_key: str, owner_id: str):
        self.released.append((lock_key, owner_id))
        if (lock_key, owner_id) in self.release_results:
            ok = self.release_results[(lock_key, owner_id)]
            if ok:
                self.owners.pop(lock_key, None)
            return ok
        current = self.owners.get(lock_key)
        if current == owner_id:
            self.owners.pop(lock_key, None)
            return True
        return False

    async def force_release_lock(self, lock_key: str):
        self.force_released.append(lock_key)
        return self.owners.pop(lock_key, None) is not None


class _FakeTasksStore:
    def __init__(self, blocked_tasks, running_tasks=None):
        self._blocked_tasks = list(blocked_tasks)
        self._running_tasks = list(running_tasks or [])
        self.updated: list[tuple[str, dict]] = []

    def list_due_blocked_tasks(self, *, blocked_reason, queue_shard=None, limit=200):
        assert blocked_reason == "concurrency_locked"
        return self._blocked_tasks[:limit]

    def list_running_playbook_execution_tasks(self, workspace_id=None, limit=200):
        return self._running_tasks[:limit]

    def update_task(self, task_id, **kwargs):
        self.updated.append((task_id, kwargs))


def _build_blocked_task(lock_key: str) -> Task:
    now = _utc_now()
    return Task(
        id="task-blocked-1",
        workspace_id="ws-1",
        message_id="msg-1",
        execution_id="exec-1",
        pack_id="ig_analyze_pinned_reference",
        task_type="playbook_execution",
        status=TaskStatus.PENDING,
        queue_shard="ig_analysis",
        created_at=now,
        next_eligible_at=now,
        blocked_reason="concurrency_locked",
        frontier_state="cold",
        execution_context={
            "playbook_code": "ig_analyze_pinned_reference",
            "runner_skip_reason": "concurrency_locked",
            "runner_skip_lock_key": lock_key,
            "runner_skip_conflict_lock_key": lock_key,
            "runner_skip_owner": "runner-1",
            "resume_after": now.isoformat(),
        },
    )


def _build_running_task(lock_key: str, *, runner_id: str = "runner-live") -> Task:
    now = _utc_now()
    return Task(
        id="task-running-1",
        workspace_id="ws-1",
        message_id="msg-1",
        execution_id="exec-running-1",
        pack_id="ig_analyze_pinned_reference",
        task_type="playbook_execution",
        status=TaskStatus.RUNNING,
        queue_shard="ig_analysis",
        created_at=now - timedelta(seconds=5),
        started_at=now - timedelta(seconds=5),
        execution_context={
            "playbook_code": "ig_analyze_pinned_reference",
            "runner_id": runner_id,
            "concurrency": {"lock_scope": "playbook"},
        },
    )


@pytest.mark.asyncio
async def test_release_lock_keys_safely_force_releases_when_release_misses_same_owner():
    lock_key = "concurrency:playbook:ig_analyze_pinned_reference"
    queue = _FakeRedisQueue("ig_analysis", owners={lock_key: "runner-1"})
    queue.release_results[(lock_key, "runner-1")] = False

    await _release_lock_keys_safely(
        queue,
        [lock_key],
        "runner-1",
        release_context="test",
    )

    assert queue.force_released == [lock_key]
    assert queue.owners == {}


@pytest.mark.asyncio
async def test_release_lock_keys_safely_does_not_delete_another_owners_lock():
    lock_key = "concurrency:playbook:ig_analyze_pinned_reference"
    queue = _FakeRedisQueue("ig_analysis", owners={lock_key: "runner-live"})
    queue.release_results[(lock_key, "runner-stale")] = False

    await _release_lock_keys_safely(
        queue,
        [lock_key],
        "runner-stale",
        release_context="test",
    )

    assert queue.force_released == []
    assert queue.owners == {lock_key: "runner-live"}


def test_runner_lock_ttl_seconds_reads_env(monkeypatch):
    monkeypatch.setenv("LOCAL_CORE_RUNNER_LOCK_TTL_SECONDS", "3600")
    assert _runner_lock_ttl_seconds() == 3600


@pytest.mark.asyncio
async def test_release_concurrency_locked_task_clears_stale_terminal_lock():
    lock_key = "concurrency:playbook:ig_analyze_pinned_reference"
    store = _FakeTasksStore([_build_blocked_task(lock_key)], running_tasks=[])
    queue = _FakeRedisQueue("ig_analysis", owners={lock_key: "runner-stale"})

    released = await reaper._release_concurrency_locked_tasks(
        store,
        queue,
        release_limit=1,
    )

    assert released == 1
    assert queue.force_released == [lock_key]
    assert queue._client.enqueued == ["task-blocked-1"]
    assert store.updated[0][1]["blocked_reason"] is None
    assert store.updated[0][1]["frontier_state"] == "ready"
    assert "runner_skip_reason" not in store.updated[0][1]["execution_context"]


@pytest.mark.asyncio
async def test_release_concurrency_locked_task_keeps_waiting_when_live_owner_exists():
    lock_key = "concurrency:playbook:ig_analyze_pinned_reference"
    store = _FakeTasksStore(
        [_build_blocked_task(lock_key)],
        running_tasks=[_build_running_task(lock_key)],
    )
    queue = _FakeRedisQueue("ig_analysis", owners={lock_key: "runner-live"})

    released = await reaper._release_concurrency_locked_tasks(
        store,
        queue,
        release_limit=1,
    )

    assert released == 0
    assert queue.force_released == []
    assert queue._client.enqueued == []
    assert store.updated[0][1]["blocked_reason"] == "concurrency_locked"
    assert store.updated[0][1]["frontier_state"] == "cold"
    assert store.updated[0][1]["execution_context"]["runner_skip_owner"] == "runner-live"
