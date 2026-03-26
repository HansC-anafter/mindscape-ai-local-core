import importlib
import importlib.util
import os
import sys
from unittest.mock import MagicMock

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
    def __init__(self, task):
        self.task = task
        self.updated_contexts = []
        self.status_updates = []

    def get_task_by_execution_id(self, execution_id):
        if self.task and self.task.execution_id == execution_id:
            return self.task
        return None

    def update_task(self, task_id, execution_context=None, **kwargs):
        assert self.task.id == task_id
        if execution_context is not None:
            self.task.execution_context = execution_context
            self.updated_contexts.append(execution_context)
        return self.task

    def update_task_status(self, task_id, status, result=None, error=None, **kwargs):
        assert self.task.id == task_id
        self.task.status = status
        self.task.result = result
        self.task.error = error
        self.status_updates.append(
            {
                "task_id": task_id,
                "status": status,
                "result": result,
                "error": error,
            }
        )
        return self.task


def _make_task():
    workspace_models = importlib.import_module("backend.app.models.workspace")
    return workspace_models.Task(
        id="task-1",
        workspace_id="ws-1",
        message_id="msg-1",
        execution_id="exec-1",
        project_id="proj-1",
        pack_id="ig_batch_pin_references",
        task_type="playbook_execution",
        status=workspace_models.TaskStatus.PENDING,
        execution_context={
            "playbook_code": "ig_batch_pin_references",
            "project_id": "proj-1",
            "remote_execution": {"cloud_dispatch_state": "pending"},
        },
    )


@pytest.mark.asyncio
async def test_remote_terminal_route_delegates_to_governance_engine(monkeypatch):
    route_module = _load_module(
        "test_remote_execution_callbacks_module",
        "backend/app/routes/core/remote_execution_callbacks.py",
    )

    captured = {}

    class StubGovernanceEngine:
        def process_remote_terminal_event(self, **kwargs):
            captured.update(kwargs)
            return {"success": True, "execution_id": kwargs["execution_id"]}

    monkeypatch.setenv("LOCAL_CORE_REMOTE_CALLBACK_SECRET", "secret-1")
    monkeypatch.setattr(route_module, "GovernanceEngine", StubGovernanceEngine)

    response = await route_module.remote_terminal_event_callback(
        body=route_module.RemoteTerminalEventRequest(
            tenant_id="tenant-1",
            workspace_id="ws-1",
            execution_id="exec-1",
            trace_id="trace-1",
            job_type="tool",
            capability_code="ig",
            playbook_code="ig_batch_pin_references",
            status="succeeded",
            result_payload={"outputs": {"artifact": "x"}},
            provider_metadata={"device_id": "gpu-1"},
        ),
        authorization="Bearer secret-1",
        x_callback_secret=None,
    )

    assert response["execution_id"] == "exec-1"
    assert captured["workspace_id"] == "ws-1"
    assert captured["trace_id"] == "trace-1"
    assert captured["job_type"] == "tool"
    assert captured["capability_code"] == "ig"


def test_remote_terminal_success_delegates_to_process_completion():
    governance_module = importlib.import_module(
        "backend.app.services.orchestration.governance_engine"
    )

    task = _make_task()
    store = StubTasksStore(task)
    engine = governance_module.GovernanceEngine()
    engine._tasks_store = store
    engine.process_completion = MagicMock(
        return_value={"success": True, "artifact_id": "art-1"}
    )

    result = engine.process_remote_terminal_event(
        tenant_id="tenant-1",
        workspace_id="ws-1",
        execution_id="exec-1",
        trace_id="trace-1",
        status="succeeded",
        result_payload={"outputs": {"artifact": "x"}},
        error_message=None,
        job_type="tool",
        capability_code="ig",
        playbook_code="ig_batch_pin_references",
        provider_metadata={
            "device_id": "gpu-1",
            "callback_delivered_at": "2026-03-26T10:01:02",
            "callback_error": None,
        },
    )

    engine.process_completion.assert_called_once_with(
        workspace_id="ws-1",
        execution_id="exec-1",
        result_data={"outputs": {"artifact": "x"}},
        project_id="proj-1",
        task_id="task-1",
        playbook_code="ig_batch_pin_references",
    )
    assert result["artifact_id"] == "art-1"
    assert store.updated_contexts[-1]["remote_execution"]["trace_id"] == "trace-1"
    assert store.updated_contexts[-1]["remote_execution"]["job_type"] == "tool"
    assert store.updated_contexts[-1]["remote_execution"]["capability_code"] == "ig"
    assert (
        store.updated_contexts[-1]["remote_execution"]["callback_delivered_at"]
        == "2026-03-26T10:01:02"
    )
    assert store.updated_contexts[-1]["remote_execution"].get("callback_error") is None


def test_remote_terminal_failure_does_not_call_process_completion():
    governance_module = importlib.import_module(
        "backend.app.services.orchestration.governance_engine"
    )
    workspace_models = importlib.import_module("backend.app.models.workspace")

    task = _make_task()
    store = StubTasksStore(task)
    engine = governance_module.GovernanceEngine()
    engine._tasks_store = store
    engine.process_completion = MagicMock()

    result = engine.process_remote_terminal_event(
        tenant_id="tenant-1",
        workspace_id="ws-1",
        execution_id="exec-1",
        trace_id="trace-1",
        status="failed",
        result_payload=None,
        error_message="gpu failed",
        job_type="tool",
        capability_code="ig",
        playbook_code="ig_batch_pin_references",
        provider_metadata={
            "device_id": "gpu-1",
            "callback_error": "local-core unavailable",
        },
    )

    engine.process_completion.assert_not_called()
    assert store.status_updates[-1]["status"] == workspace_models.TaskStatus.FAILED
    assert store.updated_contexts[-1]["trace_id"] == "trace-1"
    assert store.updated_contexts[-1]["remote_execution"]["job_type"] == "tool"
    assert store.updated_contexts[-1]["remote_execution"]["capability_code"] == "ig"
    assert store.updated_contexts[-1]["remote_execution"]["callback_error"] == "local-core unavailable"
    assert result["artifact_id"] is None


def test_remote_terminal_child_step_success_updates_task_without_completion():
    governance_module = importlib.import_module(
        "backend.app.services.orchestration.governance_engine"
    )
    workspace_models = importlib.import_module("backend.app.models.workspace")

    task = _make_task()
    task.task_type = "tool_execution"
    task.execution_context["remote_result_mode"] = "workflow_step_child"
    task.execution_context["workflow_step_id"] = "vision_analyze"
    task.execution_context["remote_execution"]["result_ingress_mode"] = (
        "workflow_step_child"
    )
    store = StubTasksStore(task)
    engine = governance_module.GovernanceEngine()
    engine._tasks_store = store
    engine.process_completion = MagicMock()

    result = engine.process_remote_terminal_event(
        tenant_id="tenant-1",
        workspace_id="ws-1",
        execution_id="exec-1",
        trace_id="trace-1",
        status="succeeded",
        result_payload={"result": {"status": "completed", "results": []}},
        error_message=None,
        job_type="tool",
        capability_code="core_llm",
        playbook_code="core_llm.multimodal_analyze",
        provider_metadata={"device_id": "gpu-1", "workflow_step_id": "vision_analyze"},
    )

    engine.process_completion.assert_not_called()
    assert store.status_updates[-1]["status"] == workspace_models.TaskStatus.SUCCEEDED
    assert store.status_updates[-1]["result"]["result_payload"]["result"]["status"] == "completed"
    assert result["task_status"] == workspace_models.TaskStatus.SUCCEEDED.value
    assert result["result_ingress_mode"] == "workflow_step_child"
