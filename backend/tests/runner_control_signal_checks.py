from backend.app.models.workspace import Task, TaskStatus, _utc_now
from backend.app.runner.task_executor import _get_task_control_signal


def _task(status: TaskStatus, *, error: str = "", execution_context=None) -> Task:
    return Task(
        id="task-1",
        workspace_id="ws-1",
        message_id="msg-1",
        execution_id="exec-1",
        pack_id="generic_playbook",
        task_type="playbook_execution",
        status=status,
        params={},
        execution_context=execution_context or {},
        created_at=_utc_now(),
    )


def test_failed_status_does_not_abort_owned_subprocess_cleanup():
    signal = _get_task_control_signal(
        _task(TaskStatus.FAILED, error="Workflow completed with step errors")
    )

    assert signal is None


def test_user_cancel_still_aborts_runner_subprocess():
    signal = _get_task_control_signal(
        _task(TaskStatus.CANCELLED_BY_USER, error="Cancelled by user")
    )

    assert signal == {"kind": "cancelled", "message": "Cancelled by user"}


def test_watchdog_abort_still_controls_runner_subprocess():
    signal = _get_task_control_signal(
        _task(
            TaskStatus.RUNNING,
            execution_context={
                "watchdog_abort_requested_at": _utc_now().isoformat(),
                "watchdog_abort_reason": "No semantic progress",
            },
        )
    )

    assert signal == {"kind": "watchdog_abort", "message": "No semantic progress"}
