from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from backend.app.models.workspace import Task, TaskStatus
from backend.app.runner import task_executor
from backend.app.runner import worker_startup
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


class _FakeLiveStateStore:
    def __init__(self, payloads=None):
        self.payloads = dict(payloads or {})

    def get_task_heartbeat(self, task_id):
        return self.payloads.get(task_id)


class _FakeNodeBudgetStore:
    def __init__(self):
        self.released = []

    async def release(self, reservation):
        self.released.append(reservation)
        return True


class _FakeResourceLeaseStore:
    def __init__(self):
        self.released = []

    async def release(self, lease_key, owner_id):
        self.released.append((lease_key, owner_id))
        return True


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
    task = _task(
        "browser-task",
        runner_id="stale-browser-runner",
        queue_shard=BROWSER_LOCAL_QUEUE_PARTITION,
        resource_class=RESOURCE_CLASS_BROWSER,
    )
    task.execution_context.update(
        resource_admission={"state": "admitted"},
        runner_resource_leases=[{"lease_key": "lease-1"}],
        runner_node_budget_reservation={"owner_id": "stale"},
    )
    store = _FakeTasksStore([task], [])
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
    updated_context = store.updated[0][1]["execution_context"]
    assert "resource_admission" not in updated_context
    assert "runner_resource_leases" not in updated_context
    assert "runner_node_budget_reservation" not in updated_context


@pytest.mark.asyncio
async def test_startup_reset_releases_exact_dead_runner_resource_ownership(monkeypatch):
    task = SimpleNamespace(
        id="browser-task",
        execution_context={
            "runner_node_budget_reservation": {
                "owner_id": "stale-browser-runner:browser-task",
                "bytes": 123,
                "revision": 7,
                "expires_at_epoch": 1000.0,
                "policy_fingerprint": "policy",
                "resource_profile_fingerprint": "profile",
                "allocatable_bytes": 999,
                "policy_mode": "calibrated",
            },
            "runner_resource_leases": [
                {"lease_key": "mindscape:runner_resources:lease:v1:profile:one"}
            ],
        },
    )
    node_store = _FakeNodeBudgetStore()
    lease_store = _FakeResourceLeaseStore()
    monkeypatch.setattr(
        worker_startup,
        "RedisNodeBudgetStore",
        lambda _queue: node_store,
    )
    monkeypatch.setattr(
        worker_startup,
        "RedisResourceLeaseStore",
        lambda _queue: lease_store,
    )

    await worker_startup._release_orphaned_resource_admission(
        task,
        old_runner_id="stale-browser-runner",
        redis_queue=SimpleNamespace(),
    )

    assert [item.owner_id for item in node_store.released] == [
        "stale-browser-runner:browser-task"
    ]
    assert lease_store.released == [
        (
            "mindscape:runner_resources:lease:v1:profile:one",
            "stale-browser-runner:browser-task",
        )
    ]


@pytest.mark.asyncio
async def test_startup_reset_skips_exact_fresh_peer_task_owner(monkeypatch):
    store = _FakeTasksStore(
        [
            _task(
                "browser-task",
                runner_id="peer-browser-runner",
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

    async def _no_runner_heartbeats(_redis_queue):
        return []

    monkeypatch.setattr(
        worker_startup,
        "list_active_runner_resource_heartbeats",
        _no_runner_heartbeats,
    )
    monkeypatch.setattr(
        worker_startup,
        "_env_int",
        lambda name, default: (
            0
            if name == "LOCAL_CORE_RUNNER_ORPHAN_DISCOVERY_GRACE_SECONDS"
            else default
        ),
    )

    reset = await worker_startup._reset_orphaned_running_tasks(
        store,
        "browser-runner",
        profile,
        redis_queue=SimpleNamespace(),
        live_state_store=_FakeLiveStateStore(
            {
                "browser-task": {
                    "task_id": "browser-task",
                    "runner_id": "peer-browser-runner",
                }
            }
        ),
    )

    assert reset == set()
    assert store.updated == []


@pytest.mark.asyncio
async def test_startup_reset_rescans_peer_heartbeats_after_grace(monkeypatch):
    store = _FakeTasksStore(
        [
            _task(
                "browser-task",
                runner_id="peer-browser-runner",
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
    reads = iter((set(), {"peer-browser-runner"}))
    slept = []

    async def _load(*args, **kwargs):
        return next(reads)

    async def _sleep(seconds):
        slept.append(seconds)

    monkeypatch.setattr(worker_startup, "_load_active_runner_ids", _load)
    monkeypatch.setattr(worker_startup.asyncio, "sleep", _sleep)
    monkeypatch.setattr(
        worker_startup,
        "_env_int",
        lambda name, default: (
            2
            if name == "LOCAL_CORE_RUNNER_ORPHAN_DISCOVERY_GRACE_SECONDS"
            else default
        ),
    )

    reset = await worker_startup._reset_orphaned_running_tasks(
        store,
        "browser-runner",
        profile,
        redis_queue=SimpleNamespace(),
        live_state_store=_FakeLiveStateStore(),
    )

    assert slept == [2]
    assert reset == set()
    assert store.updated == []


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
