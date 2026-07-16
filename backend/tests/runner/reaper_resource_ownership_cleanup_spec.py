import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from backend.app.models.workspace import TaskStatus
from backend.app.runner import reaper_resource_ownership, reaper_stale_tasks
from backend.app.services.runner_resources import (
    TaskResourceOwnershipReleaseResult,
)


def _task(*, context, status=TaskStatus.RUNNING):
    return SimpleNamespace(
        id="task-1",
        pack_id="ig_analyze_following",
        concurrency_key="profile:one",
        runner_id="runner-old",
        execution_context=context,
        status=status,
        started_at=datetime.now(timezone.utc) - timedelta(minutes=10),
        heartbeat_at=None,
    )


def _complete_result():
    return TaskResourceOwnershipReleaseResult(
        owner_id="runner-old:task-1",
        requested_lease_keys=("lease-a",),
        released_lease_keys=("lease-a",),
        unreleased_lease_keys=(),
        node_reservation_requested=False,
        node_reservation_released=None,
        node_reservation_owner_mismatch=False,
        errors=(),
    )


@pytest.mark.asyncio
async def test_reaper_adapter_waits_for_exact_resource_release(monkeypatch):
    events = []

    def fake_lock_release(*args, **kwargs):
        events.append(("lock", args[0], kwargs["event_loop"]))

    async def fake_resource_release(redis_queue, **kwargs):
        events.append(("resource", redis_queue, kwargs))
        return _complete_result()

    monkeypatch.setattr(
        reaper_resource_ownership,
        "_force_release_lock",
        fake_lock_release,
    )
    monkeypatch.setattr(
        reaper_resource_ownership,
        "release_task_resource_ownership_from_context",
        fake_resource_release,
    )
    loop = asyncio.get_running_loop()
    task = _task(context={"runner_resource_leases": [{"lease_key": "lease-a"}]})

    result = await asyncio.to_thread(
        reaper_resource_ownership.release_reaped_task_ownership,
        task,
        task.execution_context,
        previous_runner_id="runner-old",
        redis_queue=SimpleNamespace(),
        event_loop=loop,
        logger=SimpleNamespace(warning=lambda *args, **kwargs: None),
    )

    assert result.complete is True
    assert [event[0] for event in events] == ["lock", "resource"]
    assert events[1][2]["task_id"] == "task-1"
    assert events[1][2]["runner_id"] == "runner-old"


class _Store:
    def __init__(self, task, *, refreshed=None):
        self.task = task
        self.refreshed = refreshed or task
        self.updates = []

    def list_running_playbook_execution_tasks(self, workspace_id=None, limit=500):
        return [self.task]

    def update_task(self, task_id, **updates):
        self.updates.append((task_id, updates))

    def get_task(self, task_id):
        return self.refreshed


@pytest.mark.parametrize(
    ("context", "refreshed_status", "expected_terminal_status"),
    [
        (
            {"execution_mode": "runner", "status": "queued"},
            TaskStatus.RUNNING,
            TaskStatus.PENDING,
        ),
        (
            {
                "execution_mode": "runner",
                "status": "queued",
                "runner_reaper": {"requeue_count": 3},
            },
            TaskStatus.RUNNING,
            TaskStatus.FAILED,
        ),
        (
            {"execution_mode": "runner", "status": "running"},
            TaskStatus.FAILED,
            None,
        ),
    ],
)
def test_each_reaper_ownership_ending_path_releases_once(
    monkeypatch,
    context,
    refreshed_status,
    expected_terminal_status,
):
    task = _task(context=context)
    refreshed = SimpleNamespace(status=refreshed_status)
    store = _Store(task, refreshed=refreshed)
    released = []
    monkeypatch.setattr(
        reaper_stale_tasks,
        "_effective_task_heartbeat_at",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        reaper_stale_tasks,
        "_emit_run_state_changed_for_task",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        reaper_stale_tasks,
        "_invoke_on_fail_hook_sync",
        lambda *args, **kwargs: refreshed_status == TaskStatus.FAILED,
    )
    monkeypatch.setattr(
        reaper_stale_tasks,
        "release_reaped_task_ownership",
        lambda *args, **kwargs: released.append((args, kwargs)),
    )

    reaper_stale_tasks._reap_stale_running_tasks(store, "runner-current")

    assert len(released) == 1
    assert released[0][1]["previous_runner_id"] == "runner-old"
    if expected_terminal_status is not None:
        assert store.updates[-1][1]["status"] == expected_terminal_status


def test_reaper_preserves_resource_ownership_without_terminal_readback(monkeypatch):
    task = _task(context={"execution_mode": "runner", "status": "running"})
    store = _Store(task, refreshed=None)
    store.refreshed = None
    released = []
    warnings = []
    monkeypatch.setattr(
        reaper_stale_tasks,
        "_effective_task_heartbeat_at",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        reaper_stale_tasks,
        "_invoke_on_fail_hook_sync",
        lambda *args, **kwargs: True,
    )
    monkeypatch.setattr(
        reaper_stale_tasks,
        "release_reaped_task_ownership",
        lambda *args, **kwargs: released.append((args, kwargs)),
    )
    monkeypatch.setattr(
        reaper_stale_tasks.logger,
        "warning",
        lambda *args, **kwargs: warnings.append(args),
    )

    reaper_stale_tasks._reap_stale_running_tasks(store, "runner-current")

    assert released == []
    assert store.updates == []
    assert any("Preserved resource ownership" in str(args[0]) for args in warnings)
