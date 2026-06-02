from types import SimpleNamespace

from backend.app.models.workspace import TaskStatus
from backend.app.runner.worker import _pending_task_runnable_from_queue


def _task(**overrides):
    data = {
        "status": TaskStatus.PENDING,
        "frontier_state": "ready",
        "blocked_reason": None,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def test_ready_unblocked_pending_task_is_runnable_from_queue():
    assert _pending_task_runnable_from_queue(_task()) is True


def test_admission_deferred_task_is_not_runnable_from_stale_queue_item():
    assert (
        _pending_task_runnable_from_queue(
            _task(frontier_state="cold", blocked_reason="admission_deferred")
        )
        is False
    )


def test_cold_unblocked_task_is_not_runnable_from_stale_queue_item():
    assert _pending_task_runnable_from_queue(_task(frontier_state="cold")) is False
