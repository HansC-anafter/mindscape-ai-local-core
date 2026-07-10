from types import SimpleNamespace

import pytest

from backend.app.models.workspace import TaskStatus
from backend.app.runner import worker


class _Store:
    def __init__(self, task):
        self.task = task
        self.updated = []

    def list_running_playbook_execution_tasks(self, workspace_id=None, limit=500):
        return []

    def list_tasks_by_workspace(
        self,
        workspace_id,
        status=None,
        limit=None,
        exclude_cancelled=False,
    ):
        return [self.task] if status == TaskStatus.PENDING else []

    def update_task(self, task_id, **kwargs):
        self.updated.append((task_id, kwargs))


@pytest.mark.asyncio
async def test_startup_reset_preserves_resource_blocked_pending_task():
    task = SimpleNamespace(
        id="task-resource-blocked",
        status=TaskStatus.PENDING,
        frontier_state="cold",
        blocked_reason="resource_exhausted",
        execution_context={"status": "blocked_resource"},
        pack_id="ig_batch_pin_references",
        queue_shard="browser_local",
        concurrency_key=None,
    )
    store = _Store(task)

    await worker._reset_orphaned_running_tasks(store, "new-runner")

    assert store.updated == []
