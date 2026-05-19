import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.app.models.mindscape import EventType
from backend.app.services.conversation import workflow_tracker
from backend.app.services.conversation.workflow_tracker import WorkflowTracker
from backend.app.services.conversation.workflow_tracker_core.agent_collaboration import (
    update_agent_collaboration_event,
)
from backend.app.services.conversation.workflow_tracker_core.playbook_steps import (
    create_playbook_step_event,
)
from backend.app.services.conversation.workflow_tracker_core.stage_results import (
    create_stage_result,
)
from backend.app.services.conversation.workflow_tracker_core.tool_calls import (
    record_tool_call_complete,
    record_tool_call_fail,
)


def test_workflow_tracker_preserves_public_method_surface():
    required = [
        "create_playbook_step_event",
        "update_playbook_step_event",
        "record_tool_call_start",
        "record_tool_call_complete",
        "record_tool_call_fail",
        "create_stage_result",
        "create_agent_collaboration_event",
        "update_agent_collaboration_event",
    ]

    assert [name for name in required if not hasattr(WorkflowTracker, name)] == []


def test_workflow_tracker_facade_delegates_core_methods(monkeypatch):
    calls = []

    def fake_create_playbook_step_event(**kwargs):
        calls.append(("step", kwargs))
        return "step-event"

    def fake_record_tool_call_start(**kwargs):
        calls.append(("tool", kwargs))
        return "tool-call"

    def fake_create_stage_result(**kwargs):
        calls.append(("stage", kwargs))
        return "stage-result"

    def fake_create_agent_collaboration_event(**kwargs):
        calls.append(("agent", kwargs))
        return "agent-event"

    monkeypatch.setattr(
        workflow_tracker,
        "create_playbook_step_event",
        fake_create_playbook_step_event,
    )
    monkeypatch.setattr(
        workflow_tracker,
        "record_tool_call_start",
        fake_record_tool_call_start,
    )
    monkeypatch.setattr(
        workflow_tracker,
        "create_stage_result",
        fake_create_stage_result,
    )
    monkeypatch.setattr(
        workflow_tracker,
        "create_agent_collaboration_event",
        fake_create_agent_collaboration_event,
    )

    tracker = WorkflowTracker.__new__(WorkflowTracker)

    assert tracker.create_playbook_step_event("exec-1", 1, "Step 1") == "step-event"
    assert (
        tracker.record_tool_call_start("exec-1", "step-1", "tool", {})
        == "tool-call"
    )
    assert (
        tracker.create_stage_result("exec-1", "step-1", "draft", "text", {})
        == "stage-result"
    )
    assert (
        tracker.create_agent_collaboration_event(
            "exec-1",
            "step-1",
            ["agent-a"],
            "Review",
        )
        == "agent-event"
    )

    assert [kind for kind, _kwargs in calls] == ["step", "tool", "stage", "agent"]
    assert all(call[1]["tracker"] is tracker for call in calls)


def test_create_playbook_step_event_writes_expected_mind_event():
    class FakeStore:
        def __init__(self):
            self.created = None

        def create_event(self, event):
            self.created = event

    store = FakeStore()
    tracker = SimpleNamespace(store=store)

    event = create_playbook_step_event(
        tracker=tracker,
        execution_id="exec-1",
        step_index=2,
        step_name="Draft",
        status="completed",
        used_tools=["tool-a"],
        workspace_id="workspace-1",
        profile_id="profile-1",
        playbook_code="playbook-1",
    )

    assert store.created is event
    assert event.event_type == EventType.PLAYBOOK_STEP
    assert event.payload["execution_id"] == "exec-1"
    assert event.payload["step_index"] == 2
    assert event.payload["used_tools"] == ["tool-a"]
    assert event.payload["completed_at"]
    assert event.metadata["is_playbook_step"] is True


def test_tool_call_complete_and_fail_delegate_store_updates():
    class FakeToolCallsStore:
        def __init__(self):
            self.calls = []

        def update_tool_call_status(self, **kwargs):
            self.calls.append(kwargs)
            return True

    tool_calls_store = FakeToolCallsStore()
    tracker = SimpleNamespace(tool_calls_store=tool_calls_store)

    assert (
        record_tool_call_complete(
            tracker=tracker,
            tool_call_id="tool-call-1",
            response={"ok": True},
        )
        is True
    )
    assert (
        record_tool_call_fail(
            tracker=tracker,
            tool_call_id="tool-call-2",
            error="failed",
        )
        is True
    )

    assert tool_calls_store.calls[0]["status"] == "completed"
    assert tool_calls_store.calls[0]["response"] == {"ok": True}
    assert tool_calls_store.calls[1]["status"] == "failed"
    assert tool_calls_store.calls[1]["error"] == "failed"


def test_create_stage_result_writes_store_record():
    class FakeStageResultsStore:
        def __init__(self):
            self.created = None

        def create_stage_result(self, stage_result):
            self.created = stage_result

    stage_results_store = FakeStageResultsStore()
    tracker = SimpleNamespace(stage_results_store=stage_results_store)

    result = create_stage_result(
        tracker=tracker,
        execution_id="exec-1",
        step_id="step-1",
        stage_name="final_output",
        result_type="draft",
        content={"body": "hello"},
        requires_review=True,
    )

    assert stage_results_store.created is result
    assert result.execution_id == "exec-1"
    assert result.stage_name == "final_output"
    assert result.review_status == "pending"


def test_update_agent_collaboration_event_updates_existing_event():
    event = SimpleNamespace(
        event_type=EventType.AGENT_EXECUTION,
        payload={"discussion": [{"speaker": "a", "text": "one"}]},
    )

    class FakeStore:
        def __init__(self):
            self.updated = None

        def get_event(self, event_id):
            return event if event_id == "event-1" else None

        def update_event(self, value):
            self.updated = value

    store = FakeStore()
    tracker = SimpleNamespace(store=store)

    result = update_agent_collaboration_event(
        tracker=tracker,
        collaboration_event_id="event-1",
        discussion=[{"speaker": "b", "text": "two"}],
        result={"approved": True},
    )

    assert result is True
    assert store.updated is event
    assert event.payload["status"] == "completed"
    assert len(event.payload["discussion"]) == 2
    assert event.payload["result"] == {"approved": True}
    assert event.payload["completed_at"]


def test_update_agent_collaboration_event_returns_false_for_missing_event():
    class FakeStore:
        def get_event(self, _event_id):
            return None

    tracker = SimpleNamespace(store=FakeStore())

    result = update_agent_collaboration_event(
        tracker=tracker,
        collaboration_event_id="missing",
    )

    assert result is False
