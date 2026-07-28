from backend.app.runner import task_executor_child
from backend.app.runner.task_executor_child import (
    _child_execute_playbook,
    _playbook_result_status,
)
from backend.app.runner.task_executor_intent import (
    _classify_non_retryable_task_error,
    _is_non_retryable_task_error,
)
from backend.app.services.capability_tool_invocation import (
    current_runtime_task_identity,
)


def test_playbook_child_reads_nested_terminal_status():
    assert (
        _playbook_result_status(
            {"execution_mode": "workflow", "result": {"status": "failed"}}
        )
        == "failed"
    )
    assert (
        _playbook_result_status(
            {"execution_mode": "workflow", "result": {"status": "paused"}}
        )
        == "paused"
    )


def test_terminal_workflow_failure_is_not_retried_by_parent_runner():
    message = "Runner subprocess exited non-zero: Terminal workflow failure"
    assert _is_non_retryable_task_error(message)
    assert (
        _classify_non_retryable_task_error(message)
        == "terminal_workflow_failure"
    )


def test_playbook_child_scopes_current_task_identity(monkeypatch):
    captured = {}

    class FakePlaybookRunExecutor:
        async def execute_playbook_run(self, **kwargs):
            captured["kwargs"] = kwargs
            captured["runtime_task_identity"] = (
                current_runtime_task_identity()
            )
            return {"status": "succeeded"}

    monkeypatch.setattr(
        task_executor_child,
        "PlaybookRunExecutor",
        FakePlaybookRunExecutor,
    )

    _child_execute_playbook(
        {
            "runner_id": "runner-1",
            "task_id": "task-current",
            "task_type": "playbook_execution",
            "playbook_code": "ig_analyze_following",
            "profile_id": "profile-1",
            "inputs": {"target_username": "target"},
            "workspace_id": None,
            "project_id": None,
        },
        initialize_capability_packages_for_runner=lambda **kwargs: None,
    )

    assert captured["runtime_task_identity"].task_id == "task-current"
    assert current_runtime_task_identity() is None
