from __future__ import annotations

from types import SimpleNamespace

from backend.app.models.workspace import TaskStatus
from backend.app.services.playbook.task_manager import PlaybookTaskManager


class _FakeTasksStore:
    def __init__(self, task):
        self.task = task
        self.calls = []

    def get_task_by_execution_id(self, execution_id: str):
        assert execution_id == "exec_test"
        return self.task

    def update_task_status(self, **kwargs):
        self.calls.append(kwargs)


def test_update_task_status_to_failed_invokes_on_fail_hook(monkeypatch) -> None:
    task = SimpleNamespace(
        id="task_test",
        execution_context={
            "inputs": {
                "workspace_id": "ws_test",
                "request_id": "dar_test",
            },
            "lifecycle_hooks": {
                "on_fail": {
                    "tool_slot": "decision_assets.decision_assets_mark_request_terminal",
                    "inputs_map": {
                        "workspace_id": "{{input.workspace_id}}",
                        "request_id": "{{input.request_id}}",
                        "task_id": "{{context.task_id}}",
                        "failure_reason": "{{context.error}}",
                    },
                }
            },
        },
    )
    fake_store = _FakeTasksStore(task)
    manager = PlaybookTaskManager(store=None)
    manager.tasks_store = fake_store

    hook_calls = []

    def _capture_hook(execution_context, failure_reason, task_id):
        hook_calls.append(
            {
                "execution_context": execution_context,
                "failure_reason": failure_reason,
                "task_id": task_id,
            }
        )
        return True

    monkeypatch.setattr(
        "backend.app.services.playbook.task_manager._invoke_on_fail_hook_sync",
        _capture_hook,
    )

    result = manager.update_task_status_to_failed(
        execution_id="exec_test",
        error="decision_assets_runtime_request_failed:[Errno 111] Connection refused",
    )

    assert result is True
    assert len(fake_store.calls) == 1
    assert fake_store.calls[0]["task_id"] == "task_test"
    assert fake_store.calls[0]["status"] == TaskStatus.FAILED
    assert fake_store.calls[0]["error"] == "decision_assets_runtime_request_failed:[Errno 111] Connection refused"
    assert fake_store.calls[0]["completed_at"] is not None
    assert hook_calls == [
        {
            "execution_context": task.execution_context,
            "failure_reason": "decision_assets_runtime_request_failed:[Errno 111] Connection refused",
            "task_id": "task_test",
        }
    ]
