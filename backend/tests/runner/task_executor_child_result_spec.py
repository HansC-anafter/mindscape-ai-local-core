from backend.app.runner.task_executor_child import _playbook_result_status
from backend.app.runner.task_executor_intent import (
    _classify_non_retryable_task_error,
    _is_non_retryable_task_error,
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
