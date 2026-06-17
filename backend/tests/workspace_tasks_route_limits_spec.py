import pytest

from backend.app.services import mindscape_store


class _FakeMindscapeStoreForImport:
    db_path = ":memory:"


mindscape_store.MindscapeStore = _FakeMindscapeStoreForImport

from backend.app.routes.core.workspace.tasks_core import (
    execution_routes as execution_route,
)
from backend.app.routes.core.workspace.tasks_core import (
    task_list_routes as task_list_route,
)


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


class _FakeWorkspaceExecutionActivityStore:
    calls = []

    def list_executions(
        self,
        workspace_id,
        *,
        limit=30,
        offset=0,
        statuses=None,
        playbook_code=None,
        playbook_code_prefix=None,
        parent_execution_id=None,
        exclude_playbook_code=None,
        active_only=False,
        order_by="created_at",
        order="desc",
    ):
        self.calls.append(
            {
                "workspace_id": workspace_id,
                "limit": limit,
                "offset": offset,
                "statuses": statuses,
                "playbook_code": playbook_code,
                "playbook_code_prefix": playbook_code_prefix,
                "parent_execution_id": parent_execution_id,
                "exclude_playbook_code": exclude_playbook_code,
                "active_only": active_only,
                "order_by": order_by,
                "order": order,
            }
        )
        executions = [
            {
                "id": f"execution-{index}",
                "execution_id": f"execution-{index}",
                "pack_id": "pack-a",
                "queue_shard": "default",
            }
            for index in range(limit)
        ]
        return {
            "executions": executions,
            "limit": limit,
            "offset": offset,
            "returned": len(executions),
            "has_more": False,
            "next_offset": None,
        }


async def _inline_ui_read(func, *args, **kwargs):
    return func(*args, **kwargs)


@pytest.fixture(autouse=True)
def _patch_tasks_store(monkeypatch):
    _FakeTasksProjectionStore.calls = []
    _FakeWorkspaceExecutionActivityStore.calls = []
    monkeypatch.setattr(task_list_route, "TasksProjectionStore", _FakeTasksProjectionStore)
    monkeypatch.setattr(
        execution_route,
        "WorkspaceExecutionActivityStore",
        _FakeWorkspaceExecutionActivityStore,
    )
    monkeypatch.setattr(task_list_route, "run_ui_read", _inline_ui_read)
    monkeypatch.setattr(execution_route, "run_ui_read", _inline_ui_read)


@pytest.mark.asyncio
async def test_workspace_tasks_uses_projection_store_with_limit():
    payload = await task_list_route._load_workspace_tasks_payload(
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
    payload = await task_list_route._load_workspace_tasks_payload(
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
    payload = await execution_route.get_workspace_executions(
        "workspace-1",
        limit=3,
        offset=0,
        status=None,
        playbook_code=None,
        playbook_code_prefix="pack",
        parent_execution_id="parent-1",
        exclude_playbook_code=None,
        active_only=False,
        order_by="created_at",
        order="desc",
        include_execution_context=True,
        group_by_parent=False,
    )

    assert len(payload["executions"]) == 3
    assert _FakeWorkspaceExecutionActivityStore.calls == [
        {
            "workspace_id": "workspace-1",
            "limit": 3,
            "offset": 0,
            "statuses": None,
            "playbook_code": None,
            "playbook_code_prefix": "pack",
            "parent_execution_id": "parent-1",
            "exclude_playbook_code": None,
            "active_only": False,
            "order_by": "created_at",
            "order": "desc",
        }
    ]
    assert payload["executions"][0]["queue_position"] is None
    assert payload["executions"][0]["queue_total"] is None


def test_workspace_execution_live_runner_state_overlay_updates_running_rows():
    execution = {
        "id": "task-1",
        "task_id": "task-1",
        "execution_id": "task-1",
        "status": "running",
        "runner_id": None,
        "heartbeat_at": None,
        "execution_context": {"inputs": {"reference_id": "ref-1"}},
    }

    class _FakeLiveStateStore:
        def get_task_heartbeat(self, task_id):
            assert task_id == "task-1"
            return {
                "runner_id": "runner-vision-1",
                "heartbeat_at": "2026-05-29T21:28:45.733596+00:00",
            }

    payload = execution_route._attach_live_runner_state_to_execution(
        execution,
        live_state_store=_FakeLiveStateStore(),
    )

    assert payload["runner_id"] == "runner-vision-1"
    assert payload["heartbeat_at"] == "2026-05-29T21:28:45.733596+00:00"
    assert payload["execution_context"]["runner_id"] == "runner-vision-1"
    assert (
        payload["execution_context"]["heartbeat_at"]
        == "2026-05-29T21:28:45.733596+00:00"
    )
