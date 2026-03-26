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
        self._selected_memory_packet_trace = None

    def _capture_state_snapshot(self):
        return {"phase": "closed"}

    def _capture_selected_memory_packet_trace(self):
        return self._selected_memory_packet_trace

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
    engine._selected_memory_packet_trace = {
        "selected_memory_packet": {
            "selection": {"workspace_mode": "planning", "memory_scope": "standard"},
            "layers": {
                "episodic": [
                    {
                        "id": "mem-prior-001",
                        "title": "Prior governed memory",
                    }
                ]
            },
            "route_plan": ["episodic_evidence"],
        },
        "selected_memory_packet_node_ids": ["memory_item:mem-prior-001"],
    }

    engine._close_session(
        minutes_md="We linked the closed meeting to canonical memory.",
        action_items=[{"title": "Verify memory candidate"}],
        dispatch_result={"status": "accepted"},
    )

    assert session.status.value == "closed"
    assert session.metadata["canonical_memory_item_id"] == "mem-001"
    assert session.metadata["canonical_memory"]["memory_item_id"] == "mem-001"
    assert session.metadata["selected_memory_packet"]["route_plan"] == [
        "episodic_evidence"
    ]
    assert session.metadata["selected_memory_packet_node_ids"] == [
        "memory_item:mem-prior-001"
    ]
    assert session.metadata["memory_impact_trace"]["explicit"] == {
        "session_node_id": f"meeting_session:{session.id}",
        "selected_packet_node_ids": ["memory_item:mem-prior-001"],
        "action_item_node_ids": [f"action_item:{session.id}:0"],
        "canonical_writeback_node_id": "memory_item:mem-001",
        "digest_node_id": "session_digest:digest-001",
        "writeback_run_id": "run-001",
    }
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


def test_start_session_records_workflow_evidence_diagnostics():
    session = MeetingSession.new(
        workspace_id="ws-001",
        project_id="proj-001",
        thread_id="thread-001",
        agenda=["Review workflow evidence"],
    )
    engine = _FakeEngine(session=session)
    engine._workflow_evidence_diagnostics = {
        "profile": "review",
        "scope": "thread",
        "selected_line_count": 5,
        "total_line_budget": 9,
        "total_candidate_count": 8,
        "total_dropped_count": 3,
        "rendered_section_count": 3,
        "budget_utilization_ratio": 0.556,
    }
    engine._selected_memory_packet_trace = {
        "selected_memory_packet": {
            "selection": {"workspace_mode": "review", "memory_scope": "standard"},
            "layers": {
                "knowledge": {"verified": [{"id": "pk-001", "content": "Known fact"}]}
            },
            "route_plan": ["verified_knowledge"],
        },
        "selected_memory_packet_node_ids": ["knowledge:pk-001"],
    }

    engine._start_session()

    assert session.metadata["workflow_evidence_diagnostics"]["profile"] == "review"
    assert session.metadata["selected_memory_packet"]["route_plan"] == [
        "verified_knowledge"
    ]
    assert session.metadata["selected_memory_packet_node_ids"] == ["knowledge:pk-001"]
    assert engine.session_store.updated_sessions
    assert engine.emitted_events[0]["event_type"] == EventType.MEETING_START
    assert engine.emitted_events[0]["payload"]["workflow_evidence_profile"] == "review"
    assert engine.emitted_events[0]["payload"]["workflow_evidence_scope"] == "thread"
    assert (
        engine.emitted_events[0]["payload"]["workflow_evidence_selected_line_count"]
        == 5
    )
    assert (
        engine.emitted_events[0]["payload"]["workflow_evidence_total_line_budget"]
        == 9
    )
    assert (
        engine.emitted_events[0]["payload"]["workflow_evidence_total_candidate_count"]
        == 8
    )
    assert (
        engine.emitted_events[0]["payload"]["workflow_evidence_total_dropped_count"]
        == 3
    )
    assert (
        engine.emitted_events[0]["payload"]["workflow_evidence_rendered_section_count"]
        == 3
    )
    assert (
        engine.emitted_events[0]["payload"]["workflow_evidence_budget_utilization_ratio"]
        == 0.556
    )
