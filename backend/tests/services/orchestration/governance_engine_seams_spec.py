"""Seam tests for GovernanceEngine helper extraction."""

import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from backend.app.models.workspace import TaskStatus
from backend.app.services.orchestration.governance_engine import GovernanceEngine


REPO_ROOT = Path(__file__).resolve().parents[4]
ROUTES_PATH = REPO_ROOT / "backend" / "features" / "mindscape" / "routes.py"
ROUTES_CORE_PATH = (
    REPO_ROOT
    / "backend"
    / "features"
    / "mindscape"
    / "routes_core"
    / "onboarding_profile.py"
)


class FakeTasksStore:
    def __init__(self, task):
        self.task = task
        self.update_task_calls = []
        self.update_task_status_calls = []

    def get_task_by_execution_id(self, execution_id):
        return self.task

    def update_task(self, task_id, **kwargs):
        self.update_task_calls.append((task_id, kwargs))

    def update_task_status(self, task_id, status, **kwargs):
        self.update_task_status_calls.append((task_id, status, kwargs))


def _make_engine(task):
    engine = GovernanceEngine()
    engine._tasks_store = FakeTasksStore(task)
    return engine


def _load_function_ast(path: Path, fn_name: str) -> ast.AsyncFunctionDef:
    tree = ast.parse(path.read_text())
    for node in tree.body:
        if isinstance(node, ast.AsyncFunctionDef) and node.name == fn_name:
            return node
    raise AssertionError(f"Function {fn_name} not found in {path}")


def test_playbook_webhook_route_delegates_to_payload_helper():
    fn = _load_function_ast(ROUTES_PATH, "playbook_completion_webhook")

    payload_calls = []
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call):
            continue

        func_name = node.func.id if isinstance(node.func, ast.Name) else None
        if func_name == "playbook_completion_webhook_payload":
            payload_calls.append(node)

    assert len(payload_calls) == 1


def test_playbook_webhook_payload_uses_governance_engine_ingress():
    fn = _load_function_ast(ROUTES_CORE_PATH, "playbook_completion_webhook_payload")

    governance_calls = []
    legacy_calls = []
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue

        owner = node.func.value
        owner_name = owner.id if isinstance(owner, ast.Name) else None
        if (
            owner_name == "governance_engine"
            and node.func.attr == "process_playbook_webhook"
        ):
            governance_calls.append(node)
        if owner_name == "webhook_handler" and node.func.attr == "handle_playbook_completion":
            legacy_calls.append(node)

    assert len(governance_calls) == 1
    assert legacy_calls == []


def test_remote_terminal_child_shell_updates_status_without_completion():
    task = SimpleNamespace(
        id="task-child",
        status=TaskStatus.RUNNING,
        execution_context={
            "remote_execution": {"result_ingress_mode": "workflow_step_child"},
        },
        project_id="project-1",
    )
    engine = _make_engine(task)
    engine.process_completion = MagicMock(return_value={"success": True})

    result = engine.process_remote_terminal_event(
        tenant_id="tenant-1",
        workspace_id="workspace-1",
        execution_id="exec-child",
        trace_id="trace-1",
        status="completed",
        result_payload={"output": "done"},
        error_message=None,
        provider_metadata={"remote_execution_id": "remote-1"},
    )

    assert result["success"] is True
    assert result["task_status"] == TaskStatus.SUCCEEDED.value
    assert result["result_ingress_mode"] == "workflow_step_child"
    assert result["artifact_id"] is None
    assert len(engine.tasks_store.update_task_calls) == 1
    assert len(engine.tasks_store.update_task_status_calls) == 1
    task_id, status, kwargs = engine.tasks_store.update_task_status_calls[0]
    assert task_id == "task-child"
    assert status == TaskStatus.SUCCEEDED
    assert kwargs["result"]["result_payload"] == {"output": "done"}
    assert kwargs["error"] is None
    engine.process_completion.assert_not_called()


def test_remote_terminal_regular_success_uses_completion_facade():
    task = SimpleNamespace(
        id="task-regular",
        status=TaskStatus.RUNNING,
        execution_context={
            "project_id": "project-from-context",
            "playbook_code": "playbook-from-context",
            "remote_execution": {},
        },
        project_id=None,
    )
    engine = _make_engine(task)
    engine.process_completion = MagicMock(
        return_value={
            "success": True,
            "execution_id": "exec-regular",
            "artifact_id": "artifact-1",
        }
    )

    result = engine.process_remote_terminal_event(
        tenant_id="tenant-1",
        workspace_id="workspace-1",
        execution_id="exec-regular",
        trace_id="trace-1",
        status="succeeded",
        result_payload={"output": "done"},
        error_message=None,
        job_type="render",
        capability_code="capability-a",
        provider_metadata={"cloud_state": "completed"},
    )

    assert result["success"] is True
    assert result["artifact_id"] == "artifact-1"
    assert result["remote_terminal_status"] == "succeeded"
    assert len(engine.tasks_store.update_task_calls) == 1
    assert engine.tasks_store.update_task_status_calls == []
    engine.process_completion.assert_called_once_with(
        workspace_id="workspace-1",
        execution_id="exec-regular",
        result_data={"output": "done"},
        project_id="project-from-context",
        task_id="task-regular",
        playbook_code="playbook-from-context",
    )


def test_remote_terminal_terminal_task_is_idempotent():
    task = SimpleNamespace(
        id="task-done",
        status=TaskStatus.SUCCEEDED,
        execution_context={"remote_execution": {}},
        project_id=None,
    )
    engine = _make_engine(task)
    engine.process_completion = MagicMock(return_value={"success": True})

    result = engine.process_remote_terminal_event(
        tenant_id="tenant-1",
        workspace_id="workspace-1",
        execution_id="exec-done",
        trace_id="trace-1",
        status="succeeded",
        result_payload={"output": "done"},
        error_message=None,
    )

    assert result == {
        "success": True,
        "execution_id": "exec-done",
        "idempotent": True,
        "task_status": TaskStatus.SUCCEEDED.value,
    }
    assert engine.tasks_store.update_task_calls == []
    assert engine.tasks_store.update_task_status_calls == []
    engine.process_completion.assert_not_called()


def test_governance_engine_facade_methods_remain_importable():
    engine = GovernanceEngine()

    assert callable(engine.process_completion)
    assert callable(engine.process_remote_terminal_event)
    assert callable(engine.process_playbook_webhook)
    assert callable(engine._register_project_artifact)
    assert callable(engine._update_artifact_metadata)
    assert callable(engine._backfill_provenance)
