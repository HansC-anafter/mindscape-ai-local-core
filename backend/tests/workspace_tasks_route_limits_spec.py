import pytest

from backend.app.services import mindscape_store
from backend.app.models.workspace import TaskStatus


class _FakeMindscapeStoreForImport:
    db_path = ":memory:"


mindscape_store.MindscapeStore = _FakeMindscapeStoreForImport

from backend.app.routes.core.workspace import tasks as tasks_route


class _FakeTask:
    def __init__(self, task_id):
        self.id = task_id

    def model_dump(self):
        return {"id": self.id}


class _FakeTasksStore:
    pending_count = 0
    calls = []

    def list_tasks_by_workspace(
        self,
        workspace_id,
        status=None,
        limit=None,
        exclude_cancelled=False,
        task_type=None,
        compact=False,
    ):
        self.calls.append(
            {
                "workspace_id": workspace_id,
                "status": status,
                "limit": limit,
                "exclude_cancelled": exclude_cancelled,
                "task_type": task_type,
                "compact": compact,
            }
        )
        if status == TaskStatus.PENDING:
            count = min(self.pending_count, limit if limit is not None else self.pending_count)
            return [_FakeTask(f"pending-{index}") for index in range(count)]
        if status == TaskStatus.RUNNING:
            count = limit if limit is not None else 0
            return [_FakeTask(f"running-{index}") for index in range(count)]
        return []


async def _inline_ui_read(func, *args, **kwargs):
    return func(*args, **kwargs)


@pytest.fixture(autouse=True)
def _patch_tasks_store(monkeypatch):
    _FakeTasksStore.calls = []
    _FakeTasksStore.pending_count = 0
    monkeypatch.setattr(tasks_route, "TasksStore", _FakeTasksStore)
    monkeypatch.setattr(tasks_route, "run_ui_read", _inline_ui_read)


@pytest.mark.asyncio
async def test_workspace_tasks_uses_limit_for_pending_reads():
    _FakeTasksStore.pending_count = 10

    payload = await tasks_route._load_workspace_tasks_payload(
        "workspace-1",
        limit=5,
        include_completed=False,
        task_type=None,
    )

    assert len(payload["tasks"]) == 5
    assert _FakeTasksStore.calls == [
        {
            "workspace_id": "workspace-1",
            "status": TaskStatus.PENDING,
            "limit": 5,
            "exclude_cancelled": False,
            "task_type": None,
            "compact": True,
        }
    ]


@pytest.mark.asyncio
async def test_workspace_tasks_reads_running_only_for_remaining_slots():
    _FakeTasksStore.pending_count = 3

    payload = await tasks_route._load_workspace_tasks_payload(
        "workspace-1",
        limit=5,
        include_completed=False,
        task_type=None,
    )

    assert [task["id"] for task in payload["tasks"]] == [
        "pending-0",
        "pending-1",
        "pending-2",
        "running-0",
        "running-1",
    ]
    assert _FakeTasksStore.calls == [
        {
            "workspace_id": "workspace-1",
            "status": TaskStatus.PENDING,
            "limit": 5,
            "exclude_cancelled": False,
            "task_type": None,
            "compact": True,
        },
        {
            "workspace_id": "workspace-1",
            "status": TaskStatus.RUNNING,
            "limit": 2,
            "exclude_cancelled": False,
            "task_type": None,
            "compact": True,
        },
    ]
