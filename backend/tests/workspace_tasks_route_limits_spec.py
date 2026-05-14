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

    def list_workspace_executions(
        self,
        workspace_id,
        limit,
        *,
        playbook_code=None,
        playbook_code_prefix=None,
        parent_execution_id=None,
        order_by="created_at",
        order="desc",
    ):
        self.calls.append(
            {
                "workspace_id": workspace_id,
                "limit": limit,
                "playbook_code": playbook_code,
                "playbook_code_prefix": playbook_code_prefix,
                "parent_execution_id": parent_execution_id,
                "order_by": order_by,
                "order": order,
            }
        )
        return [
            {
                "id": f"execution-{index}",
                "execution_id": f"execution-{index}",
                "pack_id": "pack-a",
                "queue_shard": "default",
            }
            for index in range(limit)
        ]


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


@pytest.mark.asyncio
async def test_workspace_executions_uses_projection_store_with_filters():
    payload = await tasks_route.get_workspace_executions(
        "workspace-1",
        limit=3,
        playbook_code=None,
        playbook_code_prefix="pack",
        parent_execution_id="parent-1",
        order_by="created_at",
        order="desc",
        include_execution_context=True,
        group_by_parent=False,
    )

    assert len(payload["executions"]) == 3
    assert _FakeTasksProjectionStore.calls == [
        {
            "workspace_id": "workspace-1",
            "limit": 3,
            "playbook_code": None,
            "playbook_code_prefix": "pack",
            "parent_execution_id": "parent-1",
            "order_by": "created_at",
            "order": "desc",
        }
    ]
    assert payload["executions"][0]["queue_position"] is None
    assert payload["executions"][0]["queue_total"] is None
