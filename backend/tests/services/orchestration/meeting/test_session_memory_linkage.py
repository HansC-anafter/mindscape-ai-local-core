from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from backend.app.models.meeting_session import MeetingSession
from backend.app.models.mindscape import EventType
from backend.app.services.orchestration.meeting._session import MeetingSessionMixin


class _FakeSessionStore:
    def __init__(self) -> None:
        self.updated_sessions: list[MeetingSession] = []
        self.saved_decisions = None

    def update(self, session: MeetingSession) -> None:
        self.updated_sessions.append(session)

    def save_decisions(self, decisions) -> None:
        self.saved_decisions = decisions


class _FakeWritebackOrchestrator:
    def run_for_closed_session(self, *, session, workspace, profile_id):
        return {
            "digest": SimpleNamespace(id="digest-001"),
            "memory_item": SimpleNamespace(
                id="mem-001",
                lifecycle_status="candidate",
                verification_status="pending",
            ),
            "run": SimpleNamespace(id="run-001"),
        }


@dataclass
class _FakeEngine(MeetingSessionMixin):
    session: MeetingSession

    def __post_init__(self) -> None:
        self.session_store = _FakeSessionStore()
        self.workspace = SimpleNamespace(id=self.session.workspace_id)
        self.profile_id = "profile-001"
        self.emitted_events: list[dict] = []

    def _capture_state_snapshot(self):
        return {"phase": "closed"}

    def _emit_event(self, event_type, payload, **kwargs):
        self.emitted_events.append(
            {
                "event_type": event_type,
                "payload": payload,
                "kwargs": kwargs,
            }
        )


def test_close_session_records_canonical_memory_and_emits_memory_writeback(
    monkeypatch,
):
    import backend.app.models.meeting_decision as meeting_decision_module
    import backend.app.services.memory.writeback.meeting_memory_writeback_orchestrator as writeback_module

    monkeypatch.setattr(
        meeting_decision_module.MeetingDecision,
        "extract_from_session",
        staticmethod(lambda session: []),
    )
    monkeypatch.setattr(
        writeback_module,
        "MeetingMemoryWritebackOrchestrator",
        _FakeWritebackOrchestrator,
    )

    session = MeetingSession.new(
        workspace_id="ws-001",
        project_id="proj-001",
        thread_id="thread-001",
        agenda=["Close the memory loop"],
    )
    session.start()
    engine = _FakeEngine(session=session)

    engine._close_session(
        minutes_md="We linked the closed meeting to canonical memory.",
        action_items=[{"title": "Verify memory candidate"}],
        dispatch_result={"status": "accepted"},
    )

    assert session.status.value == "closed"
    assert session.metadata["canonical_memory_item_id"] == "mem-001"
    assert session.metadata["canonical_memory"]["memory_item_id"] == "mem-001"
    assert len(engine.session_store.updated_sessions) >= 2

    assert [event["event_type"] for event in engine.emitted_events] == [
        EventType.MEMORY_WRITEBACK,
        EventType.MEETING_END,
    ]
    assert engine.emitted_events[0]["payload"]["memory_item_id"] == "mem-001"
    assert engine.emitted_events[0]["kwargs"]["entity_ids"] == ["mem-001"]
    assert (
        engine.emitted_events[1]["payload"]["canonical_memory"]["memory_item_id"]
        == "mem-001"
    )
