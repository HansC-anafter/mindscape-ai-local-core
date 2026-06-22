from pathlib import Path

from backend.app.models.mindscape import EventType
from backend.app.models.workspace import Task, TaskStatus
from backend.app.runner import reaper_context, task_executor_events


class _FakeMindscapeStore:
    def __init__(self):
        self.events = []

    def create_event(self, event):
        self.events.append(event)


def _build_task(
    *,
    task_id: str = "task-1",
    execution_id: str = "exec-1",
    pack_id: str = "ig_analyze_following",
) -> Task:
    return Task(
        id=task_id,
        workspace_id="workspace-1",
        message_id="message-1",
        execution_id=execution_id,
        project_id="project-1",
        pack_id=pack_id,
        task_type="playbook_execution",
        status=TaskStatus.RUNNING,
        params={
            "playbook_code": pack_id,
            "target_username": "demo_target",
        },
        execution_context={
            "profile_id": "profile-1",
            "playbook_code": pack_id,
            "inputs": {
                "playbook_code": pack_id,
                "target_username": "demo_target",
            },
        },
    )


def _assert_run_state_event(
    store: _FakeMindscapeStore,
    *,
    previous_state: str,
    new_state: str,
    reason: str,
):
    assert len(store.events) == 1
    event = store.events[0]
    assert event.event_type == EventType.RUN_STATE_CHANGED
    assert event.workspace_id == "workspace-1"
    assert event.project_id == "project-1"
    assert event.profile_id == "profile-1"
    assert event.payload["execution_id"] == "exec-1"
    assert event.payload["previous_state"] == previous_state
    assert event.payload["new_state"] == new_state
    assert event.payload["reason"] == reason
    assert event.payload["playbook_code"] == "ig_analyze_following"
    assert event.payload["target_username"] == "demo_target"
    assert event.metadata["playbook_code"] == "ig_analyze_following"
    assert event.metadata["reason"] == reason


def test_task_executor_done_event_uses_public_builder(monkeypatch):
    store = _FakeMindscapeStore()
    monkeypatch.setattr(task_executor_events, "MindscapeStore", lambda: store)

    task_executor_events._emit_run_state_changed_for_task(
        _build_task(),
        previous_state="RUNNING",
        new_state="DONE",
        reason="task_completed",
    )

    _assert_run_state_event(
        store,
        previous_state="RUNNING",
        new_state="DONE",
        reason="task_completed",
    )


def test_task_executor_failed_event_uses_public_builder(monkeypatch):
    store = _FakeMindscapeStore()
    monkeypatch.setattr(task_executor_events, "MindscapeStore", lambda: store)

    task_executor_events._emit_run_state_changed_for_task(
        _build_task(),
        previous_state="RUNNING",
        new_state="FAILED",
        reason="task_failed",
    )

    _assert_run_state_event(
        store,
        previous_state="RUNNING",
        new_state="FAILED",
        reason="task_failed",
    )


def test_reaper_stale_failed_event_uses_public_builder(monkeypatch):
    store = _FakeMindscapeStore()
    monkeypatch.setattr(reaper_context, "MindscapeStore", lambda: store)

    reaper_context._emit_run_state_changed_for_task(
        _build_task(),
        previous_state="RUNNING",
        new_state="FAILED",
        reason="stale_task_reaped",
    )

    _assert_run_state_event(
        store,
        previous_state="RUNNING",
        new_state="FAILED",
        reason="stale_task_reaped",
    )


def test_lifecycle_cancel_route_uses_public_builder():
    repo_root = Path(__file__).resolve().parents[2]
    source = (
        repo_root
        / "app"
        / "routes"
        / "core"
        / "playbook_execution_core"
        / "lifecycle_routes.py"
    ).read_text(encoding="utf-8")

    assert "playbook_runner import _build_run_state_changed_event" not in source
    assert "backend.app.services.playbook_runner_core.run_state" in source
    assert "build_run_state_changed_event" in source
