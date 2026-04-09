from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

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


class _FakeWorldMemoryWritebackOrchestrator:
    def run_for_closed_session(self, *, session, workspace, profile_id):
        return {
            "updated": True,
            "workspace_id": getattr(workspace, "id", ""),
            "snapshot_id": "world-snap-001",
            "source": "meeting_governed",
            "world_memory_root": {
                "workspace_id": getattr(workspace, "id", ""),
                "current_snapshot": {"snapshot_id": "world-snap-001"},
            },
            "world_memory_delta": {
                "workspace_id": getattr(workspace, "id", ""),
                "snapshot_id": "world-snap-001",
            },
            "world_memory_packet": {"scene_id": "scene.demo", "current_zone": "main_floor"},
            "world_card_projection": {
                "title": "World Card",
                "summary_lines": ["Scene: scene.demo", "Zone: main_floor"],
            },
            "world_card_text": "World Card\n- Scene: scene.demo\n- Zone: main_floor",
        }


@dataclass
class _FakeEngine(MeetingSessionMixin):
    session: MeetingSession

    def __post_init__(self) -> None:
        self.session_store = _FakeSessionStore()
        self.workspace = SimpleNamespace(id=self.session.workspace_id)
        self.profile_id = "profile-001"
        self.project_id = self.session.project_id
        self.emitted_events: list[dict] = []
        self._selected_memory_packet_trace = None
        self._governance_packet = None
        self._memory_context_summary = ""
        self._world_memory_packet = None
        self._world_card_projection = None
        self._world_card_text = ""

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
    import backend.app.system_capabilities.world_memory_core.services.world_memory_writeback_orchestrator as world_writeback_module

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
    monkeypatch.setattr(
        world_writeback_module,
        "WorldMemoryWritebackOrchestrator",
        _FakeWorldMemoryWritebackOrchestrator,
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
    assert session.metadata["world_memory_writeback"]["snapshot_id"] == "world-snap-001"
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
        "world_snapshot_node_id": "world_snapshot:world-snap-001",
    }
    assert len(engine.session_store.updated_sessions) >= 2

    assert [event["event_type"] for event in engine.emitted_events] == [
        EventType.MEMORY_WRITEBACK,
        EventType.MEETING_END,
    ]
    assert engine.emitted_events[0]["payload"]["memory_item_id"] == "mem-001"
    assert engine.emitted_events[0]["kwargs"]["entity_ids"] == ["mem-001"]
    assert (
        engine.emitted_events[1]["payload"]["world_memory_writeback"]["snapshot_id"]
        == "world-snap-001"
    )
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


def test_start_session_persists_prefetched_governed_memory_and_world_sidecars():
    session = MeetingSession.new(
        workspace_id="ws-001",
        project_id="proj-001",
        thread_id="thread-001",
        agenda=["Inject governed context"],
    )
    engine = _FakeEngine(session=session)
    engine._governance_packet = {
        "governance_context": {"workspace_id": "ws-001", "mode": "director"},
        "memory_packet": {"selection": {"workspace_mode": "director"}},
        "world_memory_packet": {"scene_id": "scene.demo", "current_zone": "main_floor"},
        "world_card_projection": {
            "title": "World Card",
            "summary_lines": ["Scene: scene.demo", "Zone: main_floor"],
        },
        "world_card_text": "World Card\n- Scene: scene.demo\n- Zone: main_floor",
    }
    engine._memory_context_summary = "Routing mode: director / standard"

    engine._start_session()

    assert session.metadata["governance_context"]["mode"] == "director"
    assert session.metadata["memory_packet"]["selection"]["workspace_mode"] == "director"
    assert session.metadata["world_memory_packet"]["scene_id"] == "scene.demo"
    assert session.metadata["world_card_projection"]["summary_lines"][1] == "Zone: main_floor"
    assert "Scene: scene.demo" in session.metadata["world_card_text"]
    assert session.metadata["memory_context_summary"] == "Routing mode: director / standard"


@pytest.mark.asyncio
async def test_prefetch_governed_context_packet_populates_runtime_sidecars(monkeypatch):
    class _FakeReadModel:
        def __init__(self, *, store=None):
            self.store = store

        async def build_for_workspace(self, workspace, **kwargs):
            assert kwargs["profile_id"] == "profile-001"
            assert kwargs["project_id"] == "proj-001"
            return {
                "governance_context": {"workspace_id": workspace.id, "mode": "director"},
                "memory_packet": {"selection": {"workspace_mode": "director"}},
                "world_memory_packet": {"scene_id": "scene.prefetch"},
                "world_card_projection": {
                    "title": "World Card",
                    "summary_lines": ["Scene: scene.prefetch"],
                },
                "world_card_text": "World Card\n- Scene: scene.prefetch",
            }

        def format_memory_packet_for_context(self, governance_packet):
            assert governance_packet["memory_packet"]["selection"]["workspace_mode"] == "director"
            return "Routing mode: director / standard"

    class _FakeMindscapeStore:
        pass

    monkeypatch.setattr(
        "backend.app.services.governance.governance_context_read_model.GovernanceContextReadModel",
        _FakeReadModel,
    )
    monkeypatch.setattr(
        "backend.app.services.mindscape_store.MindscapeStore",
        _FakeMindscapeStore,
    )

    session = MeetingSession.new(
        workspace_id="ws-001",
        project_id="proj-001",
        thread_id="thread-001",
        agenda=["Prefetch governed context"],
    )
    engine = _FakeEngine(session=session)

    await engine._prefetch_governed_context_packet()

    assert engine._governance_packet["governance_context"]["mode"] == "director"
    assert engine._memory_context_summary == "Routing mode: director / standard"
    assert engine._world_memory_packet["scene_id"] == "scene.prefetch"
    assert "Scene: scene.prefetch" in engine._world_card_text


def test_close_session_stitches_execution_lineage_into_action_items(monkeypatch):
    import backend.app.services.memory.writeback.meeting_memory_writeback_orchestrator as writeback_module

    monkeypatch.setattr(
        writeback_module,
        "MeetingMemoryWritebackOrchestrator",
        _FakeWritebackOrchestrator,
    )

    session = MeetingSession.new(
        workspace_id="ws-001",
        project_id="proj-001",
        thread_id="thread-001",
        agenda=["Close the execution lineage loop"],
    )
    session.start()
    engine = _FakeEngine(session=session)

    engine._close_session(
        minutes_md="Execution lineage should be persisted before decision extraction.",
        action_items=[{"title": "Finalize artifact", "intent_id": "intent-1"}],
        dispatch_result={
            "status": "ok",
            "attempts": {
                "intent-1": {
                    "adapter_meta": {"execution_id": "exec-123"},
                    "result": {"task_id": "task-123"},
                }
            },
        },
    )

    assert session.action_items[0]["execution_id"] == "exec-123"
    assert session.action_items[0]["task_id"] == "task-123"
    assert engine.session_store.saved_decisions is not None
    decision = engine.session_store.saved_decisions[0]
    assert decision.source_action_item["execution_id"] == "exec-123"
    assert decision.source_action_item["task_id"] == "task-123"


def test_close_session_falls_back_to_task_id_when_execution_id_missing(monkeypatch):
    import backend.app.services.memory.writeback.meeting_memory_writeback_orchestrator as writeback_module

    monkeypatch.setattr(
        writeback_module,
        "MeetingMemoryWritebackOrchestrator",
        _FakeWritebackOrchestrator,
    )

    session = MeetingSession.new(
        workspace_id="ws-001",
        project_id="proj-001",
        thread_id="thread-001",
        agenda=["Use task id as execution lineage fallback"],
    )
    session.start()
    engine = _FakeEngine(session=session)

    engine._close_session(
        minutes_md="Execution lineage should fall back to task id when needed.",
        action_items=[{"title": "Run tool", "intent_id": "intent-2"}],
        dispatch_result={
            "status": "ok",
            "attempts": {
                "intent-2": {
                    "adapter_meta": {},
                    "result": {"task_id": "task-456"},
                }
            },
        },
    )

    assert session.action_items[0]["execution_id"] == "task-456"
    assert session.action_items[0]["task_id"] == "task-456"
    assert engine.session_store.saved_decisions is not None
    decision = engine.session_store.saved_decisions[0]
    assert decision.source_action_item["execution_id"] == "task-456"


def test_close_session_stitches_phase_index_lineage_when_phase_ids_are_ordinal(
    monkeypatch,
):
    import backend.app.services.memory.writeback.meeting_memory_writeback_orchestrator as writeback_module

    monkeypatch.setattr(
        writeback_module,
        "MeetingMemoryWritebackOrchestrator",
        _FakeWritebackOrchestrator,
    )

    session = MeetingSession.new(
        workspace_id="ws-001",
        project_id="proj-001",
        thread_id="thread-001",
        agenda=["Backfill lineage for ordinal phase ids"],
    )
    session.start()
    engine = _FakeEngine(session=session)

    engine._close_session(
        minutes_md="Ordinal phase ids should still stitch back into action items.",
        action_items=[
            {"title": "Plan first", "intent_id": "intent-1"},
            {"title": "Run tool second", "intent_id": "intent-2"},
        ],
        dispatch_result={
            "status": "ok",
            "attempts": {
                "phase_1": {
                    "adapter_meta": {},
                    "result": {"task_id": "task-789"},
                }
            },
        },
    )

    assert session.action_items[1]["execution_id"] == "task-789"
    assert session.action_items[1]["task_id"] == "task-789"
    decision = engine.session_store.saved_decisions[1]
    assert decision.source_action_item["execution_id"] == "task-789"


def test_close_session_prefers_source_intent_id_over_ordinal_phase_id(monkeypatch):
    import backend.app.services.memory.writeback.meeting_memory_writeback_orchestrator as writeback_module

    monkeypatch.setattr(
        writeback_module,
        "MeetingMemoryWritebackOrchestrator",
        _FakeWritebackOrchestrator,
    )

    session = MeetingSession.new(
        workspace_id="ws-001",
        project_id="proj-001",
        thread_id="thread-001",
        agenda=["Prefer explicit source intent over ordinal phase fallback"],
    )
    session.start()
    engine = _FakeEngine(session=session)

    engine._close_session(
        minutes_md="Explicit source_intent_id should win over phase_0 fallback.",
        action_items=[
            {"title": "Planning item", "intent_id": "intent-1"},
            {"title": "Execution item", "intent_id": "intent-2"},
        ],
        dispatch_result={
            "status": "ok",
            "attempts": {
                "phase_0": {
                    "adapter_meta": {"source_intent_id": "intent-2"},
                    "result": {"task_id": "task-900"},
                }
            },
        },
    )

    assert "execution_id" not in session.action_items[0]
    assert session.action_items[1]["source_intent_id"] == "intent-2"
    assert session.action_items[1]["source_phase_id"] == "phase_0"
    assert session.action_items[1]["execution_id"] == "task-900"
    assert session.action_items[1]["execution_ids"] == ["task-900"]
    decision = engine.session_store.saved_decisions[1]
    assert decision.source_action_item["execution_id"] == "task-900"
