import pytest

from backend.app.services import mindscape_store


class _FakeMindscapeStoreForImport:
    db_path = ":memory:"


mindscape_store.MindscapeStore = _FakeMindscapeStoreForImport

from backend.app.routes.core.workspace import tasks as tasks_route


class _FakeTasksProjectionStore:
    calls = []

    def list_workspace_tasks(
        self,
        workspace_id,
        limit,
        include_completed=False,
        task_type=None,
    ):
        self.calls.append(
            {
                "workspace_id": workspace_id,
                "limit": limit,
                "include_completed": include_completed,
                "task_type": task_type,
            }
        )
        return [{"id": f"projected-{index}"} for index in range(limit)]


async def _inline_ui_read(func, *args, **kwargs):
    return func(*args, **kwargs)


@pytest.fixture(autouse=True)
def _patch_tasks_store(monkeypatch):
    _FakeTasksProjectionStore.calls = []
    monkeypatch.setattr(tasks_route, "TasksProjectionStore", _FakeTasksProjectionStore)
    monkeypatch.setattr(tasks_route, "run_ui_read", _inline_ui_read)


@pytest.mark.asyncio
async def test_workspace_tasks_uses_projection_store_with_limit():
    payload = await tasks_route._load_workspace_tasks_payload(
        "workspace-1",
        limit=5,
        include_completed=False,
        task_type=None,
    )

    assert len(payload["tasks"]) == 5
    assert _FakeTasksProjectionStore.calls == [
        {
            "workspace_id": "workspace-1",
            "limit": 5,
            "include_completed": False,
            "task_type": None,
        }
    ]


@pytest.mark.asyncio
async def test_workspace_tasks_passes_execution_filter_to_projection_store():
    payload = await tasks_route._load_workspace_tasks_payload(
        "workspace-1",
        limit=100,
        include_completed=True,
        task_type="execution",
    )

    assert len(payload["tasks"]) == 100
    assert _FakeTasksProjectionStore.calls == [
        {
            "workspace_id": "workspace-1",
            "limit": 100,
            "include_completed": True,
            "task_type": "execution",
        },
    ]
