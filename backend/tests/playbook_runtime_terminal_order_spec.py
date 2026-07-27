import importlib
from types import SimpleNamespace

from backend.app.models.workspace import TaskStatus
from backend.app.services.playbook_run_executor_core.runtime_workflow_persistence import (
    persist_runtime_result,
)


class _FakeTasksStore:
    def __init__(self, events):
        self.events = events
        self.existing_task = SimpleNamespace(
            id="task-1",
            params={},
            execution_context={"seed": True},
        )

    def get_task_by_execution_id(self, _execution_id):
        return self.existing_task

    def update_task(self, task_id, **kwargs):
        self.events.append(("update", task_id, kwargs))


def test_runtime_result_lands_before_terminal_task_is_published(monkeypatch):
    events = []
    tasks_store_module = importlib.import_module(
        "backend.app.services.stores.tasks_store"
    )
    persistence = importlib.import_module(
        "backend.app.services.playbook_run_executor_core.runtime_workflow_persistence"
    )
    monkeypatch.setattr(
        tasks_store_module,
        "TasksStore",
        lambda: _FakeTasksStore(events),
    )
    monkeypatch.setattr(
        persistence,
        "_land_runtime_result",
        lambda **_kwargs: events.append(("land",)),
    )

    persist_runtime_result(
        playbook_run=SimpleNamespace(
            playbook_json=SimpleNamespace(steps=[{"id": "step-1"}]),
            playbook=SimpleNamespace(metadata=SimpleNamespace(name="Demo")),
        ),
        playbook_code="demo_playbook",
        execution_id="exec-order",
        workspace_id="ws-1",
        project_id=None,
        profile_id="profile-1",
        normalized_inputs={"reference_id": "ref-order"},
        runtime_result=SimpleNamespace(status="completed", outputs={}, metadata={}),
        result={"status": "completed"},
        runtime_result_has_errors_fn=lambda runtime_result, result: False,
    )

    assert [event[0] for event in events] == ["land", "update"]
    assert events[1][2]["status"] == TaskStatus.SUCCEEDED


def test_runner_child_keeps_success_running_for_parent_finalization(monkeypatch):
    events = []
    tasks_store_module = importlib.import_module(
        "backend.app.services.stores.tasks_store"
    )
    persistence = importlib.import_module(
        "backend.app.services.playbook_run_executor_core.runtime_workflow_persistence"
    )
    monkeypatch.setattr(
        tasks_store_module,
        "TasksStore",
        lambda: _FakeTasksStore(events),
    )
    monkeypatch.setattr(
        persistence,
        "_land_runtime_result",
        lambda **_kwargs: events.append(("land",)),
    )

    persist_runtime_result(
        playbook_run=SimpleNamespace(
            playbook_json=SimpleNamespace(steps=[{"id": "step-1"}]),
            playbook=SimpleNamespace(metadata=SimpleNamespace(name="Demo")),
        ),
        playbook_code="demo_playbook",
        execution_id="exec-runner-order",
        workspace_id="ws-1",
        project_id=None,
        profile_id="profile-1",
        normalized_inputs={"reference_id": "ref-runner-order"},
        runtime_result=SimpleNamespace(status="completed", outputs={}, metadata={}),
        result={"status": "completed"},
        runtime_result_has_errors_fn=lambda runtime_result, result: False,
        parent_finalizes_success=True,
    )

    assert [event[0] for event in events] == ["land", "update"]
    update = events[1][2]
    assert update["status"] == TaskStatus.RUNNING
    assert update["completed_at"] is None


def test_runner_child_keeps_failure_running_for_parent_finalization(monkeypatch):
    events = []
    tasks_store_module = importlib.import_module(
        "backend.app.services.stores.tasks_store"
    )
    persistence = importlib.import_module(
        "backend.app.services.playbook_run_executor_core.runtime_workflow_persistence"
    )
    monkeypatch.setattr(
        tasks_store_module,
        "TasksStore",
        lambda: _FakeTasksStore(events),
    )
    monkeypatch.setattr(
        persistence,
        "_land_runtime_result",
        lambda **_kwargs: events.append(("land",)),
    )

    persist_runtime_result(
        playbook_run=SimpleNamespace(
            playbook_json=SimpleNamespace(steps=[{"id": "step-1"}]),
            playbook=SimpleNamespace(metadata=SimpleNamespace(name="Demo")),
        ),
        playbook_code="demo_playbook",
        execution_id="exec-runner-failed",
        workspace_id="ws-1",
        project_id=None,
        profile_id="profile-1",
        normalized_inputs={"reference_id": "ref-runner-failed"},
        runtime_result=SimpleNamespace(status="failed", outputs={}, metadata={}),
        result={"status": "failed"},
        runtime_result_has_errors_fn=lambda runtime_result, result: True,
        parent_finalizes_success=True,
    )

    update = events[1][2]
    assert update["status"] == TaskStatus.RUNNING
    assert update["completed_at"] is None
    assert update["error"] == "Workflow completed with step errors"


def test_durable_execution_inputs_are_not_rewritten_to_hot_params(monkeypatch):
    events = []
    store = _FakeTasksStore(events)
    store.existing_task.execution_context = {
        "execution_inputs_ref": {
            "schema_version": 1,
            "storage_ref": "/workspace/execution-inputs/exec/inputs.json",
        }
    }
    tasks_store_module = importlib.import_module(
        "backend.app.services.stores.tasks_store"
    )
    persistence = importlib.import_module(
        "backend.app.services.playbook_run_executor_core.runtime_workflow_persistence"
    )
    monkeypatch.setattr(tasks_store_module, "TasksStore", lambda: store)
    monkeypatch.setattr(
        persistence,
        "_land_runtime_result",
        lambda **_kwargs: events.append(("land",)),
    )

    persist_runtime_result(
        playbook_run=SimpleNamespace(
            playbook_json=SimpleNamespace(steps=[{"id": "step-1"}]),
            playbook=SimpleNamespace(metadata=SimpleNamespace(name="Demo")),
        ),
        playbook_code="demo_playbook",
        execution_id="exec-durable",
        workspace_id="ws-1",
        project_id=None,
        profile_id="profile-1",
        normalized_inputs={"payload": "x" * 20000},
        runtime_result=SimpleNamespace(status="completed", outputs={}, metadata={}),
        result={"status": "completed"},
        runtime_result_has_errors_fn=lambda runtime_result, result: False,
    )

    update = events[1][2]
    assert "params" not in update
    assert "inputs" not in update["execution_context"]
