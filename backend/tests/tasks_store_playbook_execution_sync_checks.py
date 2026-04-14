import os
import sys

_repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)
_backend_root = os.path.join(_repo_root, "backend")
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)

from backend.app.models.workspace import TaskStatus
from backend.app.services.stores.tasks_store._base import (
    _project_playbook_execution_state,
)


def test_running_task_projects_execution_phase_as_execution():
    assert _project_playbook_execution_state(TaskStatus.RUNNING) == (
        "running",
        "execution",
    )


def test_pending_task_projects_execution_phase_as_queue():
    assert _project_playbook_execution_state(
        TaskStatus.PENDING,
        {"status": "queued"},
    ) == ("running", "queue")


def test_user_paused_pending_task_projects_execution_as_paused_queue():
    assert _project_playbook_execution_state(
        TaskStatus.PENDING,
        {"status": "paused"},
        blocked_reason="user_pause_reserved",
    ) == ("paused", "queue")


def test_terminal_task_projects_execution_terminal_state():
    assert _project_playbook_execution_state(TaskStatus.SUCCEEDED) == (
        "done",
        "execution",
    )
    assert _project_playbook_execution_state(TaskStatus.FAILED) == (
        "failed",
        "execution",
    )
