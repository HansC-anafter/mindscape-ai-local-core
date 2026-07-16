import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.app.app_bootstrap import lifecycle_startup_services
from backend.app.services.task_zombie_reaper import (
    reap_zombie_tasks_with_resource_cleanup,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


class _FakeTasksStore:
    def __init__(self, tasks):
        self.tasks = list(tasks)
        self.calls = []

    def reap_zombie_tasks(self, **kwargs):
        self.calls.append(kwargs)
        for task in self.tasks:
            kwargs["on_reaped"](task)
        return [task.id for task in self.tasks]


def _task(task_id, *, with_resource=True, runner_id="runner-a"):
    execution_context = {"runner_id": runner_id}
    if with_resource:
        execution_context["runner_resource_leases"] = [
            {
                "lease_key": f"lease:{task_id}",
                "resource_type": "ig_profile_lock",
                "resource_id": task_id,
            }
        ]
    return SimpleNamespace(
        id=task_id,
        runner_id=runner_id,
        execution_context=execution_context,
    )


@pytest.mark.asyncio
async def test_zombie_facade_releases_persisted_exact_owner_after_store_transition():
    store = _FakeTasksStore([_task("task-a"), _task("task-b", with_resource=False)])
    release_calls = []

    async def _release(_queue, **kwargs):
        release_calls.append(kwargs)
        return SimpleNamespace(complete=True)

    result = await reap_zombie_tasks_with_resource_cleanup(
        tasks_store=store,
        redis_queue=object(),
        release_func=_release,
    )

    assert result.task_ids == ("task-a", "task-b")
    assert result.released_task_ids == ("task-a",)
    assert result.skipped_task_ids == ("task-b",)
    assert result.incomplete_task_ids == ()
    assert result.cleanup_complete is True
    assert release_calls == [
        {
            "task_id": "task-a",
            "runner_id": "runner-a",
            "execution_context": store.tasks[0].execution_context,
        }
    ]
    assert store.calls[0]["heartbeat_ttl_minutes"] == 10
    assert store.calls[0]["no_heartbeat_ttl_minutes"] == 30


@pytest.mark.asyncio
async def test_zombie_facade_reports_incomplete_without_deleting_foreign_owner():
    store = _FakeTasksStore([_task("task-a")])

    async def _incomplete(_queue, **_kwargs):
        return SimpleNamespace(complete=False)

    result = await reap_zombie_tasks_with_resource_cleanup(
        tasks_store=store,
        redis_queue=object(),
        release_func=_incomplete,
    )

    assert result.released_task_ids == ()
    assert result.incomplete_task_ids == ("task-a",)
    assert result.cleanup_complete is False


def test_zombie_entrypoints_delegate_to_single_facade():
    startup_source = inspect.getsource(lifecycle_startup_services.start_zombie_reaper)
    route_source = (
        REPO_ROOT
        / "backend/app/routes/core/workspace/tasks_core/control_routes.py"
    ).read_text(encoding="utf-8")

    assert "reap_zombie_tasks_with_resource_cleanup" in startup_source
    assert "reap_zombie_tasks_with_resource_cleanup" in route_source
    assert ".reap_zombie_tasks(" not in startup_source
    assert ".reap_zombie_tasks(" not in route_source
