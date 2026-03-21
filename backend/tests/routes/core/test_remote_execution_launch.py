import importlib
import importlib.util
import os
import sys

import pytest

_repo_root = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
)
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)
_backend_root = os.path.join(_repo_root, "backend")
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)


def _load_module(module_name: str, relative_path: str):
    module_path = os.path.join(_repo_root, relative_path)
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class StubTasksStore:
    def __init__(self):
        self.tasks_by_execution = {}
        self.created_tasks = []
        self.updated_contexts = []
        self.status_updates = []

    def get_task_by_execution_id(self, execution_id):
        return self.tasks_by_execution.get(execution_id)

    def create_task(self, task):
        self.created_tasks.append(task)
        self.tasks_by_execution[task.execution_id] = task
        return task

    def update_task(self, task_id, execution_context=None, **kwargs):
        for task in self.tasks_by_execution.values():
            if task.id == task_id:
                if execution_context is not None:
                    task.execution_context = execution_context
                    self.updated_contexts.append(execution_context)
                return task
        raise AssertionError(f"unknown task_id: {task_id}")

    def update_task_status(self, task_id, status, result=None, error=None, **kwargs):
        for task in self.tasks_by_execution.values():
            if task.id == task_id:
                task.status = status
                task.result = result
                task.error = error
                self.status_updates.append(
                    {
                        "task_id": task_id,
                        "status": status,
                        "result": result,
                        "error": error,
                    }
                )
                return task
        raise AssertionError(f"unknown task_id: {task_id}")


class StubConnector:
    is_connected = True

    def __init__(self):
        self.calls = []

    async def start_remote_execution(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "id": kwargs["execution_id"],
            "state": "pending",
        }


@pytest.mark.asyncio
async def test_dispatch_remote_execution_creates_local_shell(monkeypatch):
    dispatch = _load_module(
        "test_execution_dispatch_module",
        "backend/app/routes/core/execution_dispatch.py",
    )
    tasks_store_module = importlib.import_module(
        "backend.app.services.stores.tasks_store"
    )

    store = StubTasksStore()
    connector = StubConnector()

    monkeypatch.setattr(tasks_store_module, "TasksStore", lambda: store)
    monkeypatch.setattr(dispatch, "get_cloud_connector", lambda: connector)

    result = await dispatch.dispatch_remote_execution(
        playbook_code="ig_batch_pin_references",
        inputs={"batch_id": "b-1"},
        workspace_id="ws-1",
        profile_id="user-1",
        project_id="proj-1",
        tenant_id="tenant-1",
        execution_id="exec-123",
        trace_id="trace-123",
    )

    assert result["execution_id"] == "exec-123"
    assert result["trace_id"] == "trace-123"
    assert len(store.created_tasks) == 1
    task = store.created_tasks[0]
    assert task.execution_context["remote_execution"]["trace_id"] == "trace-123"
    assert task.execution_context["remote_execution"]["tenant_id"] == "tenant-1"
    assert task.execution_context["runner_skip_reason"] == "remote_execution_shell"
    assert connector.calls[0]["execution_id"] == "exec-123"
    assert connector.calls[0]["trace_id"] == "trace-123"
    assert connector.calls[0]["callback_payload"]["mode"] == "local_core_terminal_event"
    assert connector.calls[0]["request_payload"]["inputs"]["execution_id"] == "exec-123"


def test_start_execution_request_exposes_remote_governance_fields():
    schemas_module = _load_module(
        "test_execution_schemas_module",
        "backend/app/routes/core/execution_schemas.py",
    )

    fields = schemas_module.StartExecutionRequest.model_fields

    assert "tenant_id" in fields
    assert "execution_id" in fields
    assert "trace_id" in fields
    assert "remote_job_type" in fields
