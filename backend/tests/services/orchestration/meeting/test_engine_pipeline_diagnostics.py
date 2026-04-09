from __future__ import annotations

import asyncio
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from backend.app.models.meeting_session import MeetingSession
from backend.app.services.orchestration.meeting_agents import DeliberationDepth
from backend.app.services.orchestration.meeting.round_router import (
    build_executor_routing_graph,
    build_round_routing_graph,
)
from backend.app.services.orchestration.meeting.engine import MeetingEngine, RoleTurnResult


class _FakeSessionStore:
    def __init__(self) -> None:
        self.updated_sessions: list[MeetingSession] = []

    def update(self, session: MeetingSession) -> None:
        self.updated_sessions.append(session)


class _PipelineHarness(MeetingEngine):
    def __init__(self, session: MeetingSession) -> None:
        self.session = session
        self.session_store = _FakeSessionStore()
        self.workspace = SimpleNamespace(id=session.workspace_id)
        self.profile_id = "profile-001"
        self.thread_id = session.thread_id
        self.project_id = session.project_id

    async def _stage_agenda_and_rag(self, user_message: str) -> None:
        raise RuntimeError("agenda stage stalled")

    async def _stage_compile_contract(self, user_message: str) -> None:
        raise AssertionError("compile_contract should not run after agenda failure")

    async def _stage_deliberation(self, user_message: str):
        raise AssertionError("deliberation should not run after agenda failure")


class _RoundProgressHarness(MeetingEngine):
    def __init__(self, session: MeetingSession) -> None:
        self.session = session
        self.session_store = _FakeSessionStore()
        self.workspace = SimpleNamespace(id=session.workspace_id)
        self.profile_id = "profile-001"
        self.thread_id = session.thread_id
        self.project_id = session.project_id


class _RoutingWarningHarness(_RoundProgressHarness):
    def __init__(self, session: MeetingSession) -> None:
        super().__init__(session=session)
        self.emitted_warnings: list[dict[str, object]] = []

    def _emit_round_routing_warning(self, payload: dict[str, object]) -> None:
        self.emitted_warnings.append(payload)


class _CompileContractHarness(_RoundProgressHarness):
    def __init__(self, session: MeetingSession) -> None:
        super().__init__(session=session)
        self.model_name = "gpt-5.4"
        self.emitted_stages: list[tuple[str, str]] = []

    async def _emit_meeting_stage(self, stage: str, message: str) -> None:
        self.emitted_stages.append((stage, message))


class _FakeRequestContract:
    def __init__(self) -> None:
        self.deliverables = [SimpleNamespace(id="D1")]
        self.scale_estimate = SimpleNamespace(value="task")

    def model_dump(self) -> dict[str, object]:
        return {
            "goals": ["Trace compile contract"],
            "deliverables": [{"id": "D1", "name": "Brief", "quantity": 1}],
            "scale_estimate": "task",
        }


@pytest.mark.asyncio
async def test_run_persists_pipeline_stage_on_pre_deliberation_failure():
    session = MeetingSession.new(
        workspace_id="ws-001",
        project_id="proj-001",
        thread_id="thread-001",
        agenda=["Trace stalled compile"],
    )
    engine = _PipelineHarness(session=session)

    with pytest.raises(RuntimeError, match="agenda stage stalled"):
        await engine.run("Investigate stalled compile")

    assert session.status.value == "failed"
    assert session.round_count == 0
    assert session.metadata["pipeline_stage"] == "agenda_and_rag"
    assert session.metadata["pipeline_stage_status"] == "failed"
    assert session.metadata["pipeline_stage_error"] == "agenda stage stalled"
    assert session.metadata["pipeline_failure"]["before_deliberation"] is True
    assert session.metadata["pipeline_failure"]["stage"] == "agenda_and_rag"
    assert session.ended_at is not None
    assert engine.session_store.updated_sessions
    assert session.metadata["pipeline_stage_history"][0]["status"] == "started"
    assert session.metadata["pipeline_stage_history"][-1]["status"] == "failed"


def test_persist_round_progress_updates_session_for_live_polling():
    session = MeetingSession.new(
        workspace_id="ws-001",
        project_id="proj-001",
        thread_id="thread-001",
        agenda=["Trace deliberation progress"],
    )
    engine = _RoundProgressHarness(session=session)

    session.round_count = 2
    engine._persist_round_progress(2, "completed")

    assert engine.session_store.updated_sessions
    assert engine.session_store.updated_sessions[-1] is session
    assert session.metadata["last_round_status"] == "completed"
    assert session.metadata["last_round_updated_at"]


def test_handle_round_routing_warning_persists_and_emits_warning():
    session = MeetingSession.new(
        workspace_id="ws-001",
        project_id="proj-001",
        thread_id="thread-001",
        agenda=["Trace routing warnings"],
    )
    engine = _RoutingWarningHarness(session=session)
    graph = build_executor_routing_graph(
        session_id=session.id,
        round_number=3,
        agenda=session.agenda,
        facilitator_summary="A" * 800,
        decision="B" * 800,
        planner_proposals=["C" * 800],
        critic_notes=["D" * 800],
    )
    graph.metadata["next_role_id"] = "executor"

    payload = engine._handle_round_routing_warning(graph)

    assert payload is not None
    assert engine.emitted_warnings
    assert engine.emitted_warnings[-1]["warning_types"] == ["context_pressure"]
    assert session.metadata["last_round_routing_warning"]["warning_types"] == [
        "context_pressure"
    ]
    assert session.metadata["round_routing_warning_history"][-1]["round_number"] == 3
    assert engine.session_store.updated_sessions[-1] is session


def test_handle_round_routing_warning_noops_when_graph_is_healthy():
    session = MeetingSession.new(
        workspace_id="ws-001",
        project_id="proj-001",
        thread_id="thread-001",
        agenda=["Trace routing warnings"],
    )
    engine = _RoutingWarningHarness(session=session)
    graph = build_round_routing_graph(
        session_id=session.id,
        round_number=1,
        agenda=session.agenda,
        facilitator_summary="Short summary",
        planner_proposals=[],
        critic_notes=[],
    )
    graph.metadata["next_role_id"] = "planner"

    payload = engine._handle_round_routing_warning(graph)

    assert payload is None
    assert engine.emitted_warnings == []
    assert "last_round_routing_warning" not in session.metadata


def test_mark_round_routing_fallback_marks_starved_next_role():
    session = MeetingSession.new(
        workspace_id="ws-001",
        project_id="proj-001",
        thread_id="thread-001",
        agenda=["Trace routing fallback"],
    )
    engine = _RoundProgressHarness(session=session)
    graph = build_round_routing_graph(
        session_id=session.id,
        round_number=2,
        agenda=session.agenda,
        facilitator_summary="Short summary",
        planner_proposals=["Planner proposal"],
        critic_notes=["Critic note"],
    )
    graph.metadata["starved_role_ids"] = ["planner"]
    graph.metadata["role_packet_stats"]["planner"]["status"] = "starved"

    applied = engine._mark_round_routing_fallback(graph, next_role_id="planner")

    assert applied is True
    assert graph.metadata["fallback_to_full_context"] is True
    assert graph.metadata["fallback_role_id"] == "planner"
    assert graph.metadata["fallback_reason"] == "starved_role"


def test_mark_round_routing_fallback_clears_flag_for_healthy_next_role():
    session = MeetingSession.new(
        workspace_id="ws-001",
        project_id="proj-001",
        thread_id="thread-001",
        agenda=["Trace routing fallback"],
    )
    engine = _RoundProgressHarness(session=session)
    graph = build_round_routing_graph(
        session_id=session.id,
        round_number=1,
        agenda=session.agenda,
        facilitator_summary="Short summary",
        planner_proposals=[],
        critic_notes=[],
    )
    graph.metadata["fallback_to_full_context"] = True
    graph.metadata["fallback_role_id"] = "planner"
    graph.metadata["fallback_reason"] = "starved_role"

    applied = engine._mark_round_routing_fallback(graph, next_role_id="planner")

    assert applied is False
    assert graph.metadata["fallback_to_full_context"] is False
    assert "fallback_role_id" not in graph.metadata
    assert "fallback_reason" not in graph.metadata


def test_mark_round_routing_prompt_mode_marks_compressed_sparse_on_context_pressure():
    session = MeetingSession.new(
        workspace_id="ws-001",
        project_id="proj-001",
        thread_id="thread-001",
        agenda=["Trace routing compression"],
    )
    engine = _RoundProgressHarness(session=session)
    graph = build_executor_routing_graph(
        session_id=session.id,
        round_number=3,
        agenda=session.agenda,
        facilitator_summary="A" * 800,
        decision="B" * 800,
        planner_proposals=["C" * 800],
        critic_notes=["D" * 800],
    )

    mode = engine._mark_round_routing_prompt_mode(graph, next_role_id="executor")

    assert mode == "compressed_sparse"
    assert graph.metadata["routing_prompt_mode"] == "compressed_sparse"
    assert graph.metadata["routing_prompt_role_id"] == "executor"
    assert graph.metadata["routing_prompt_reason"] == "context_pressure"
    assert graph.metadata["routing_health_status"] == "warning"
    assert graph.metadata["routing_health_reason"] == "compression_pressure"
    assert graph.metadata["compressed_packet_char_limit"] == 96
    assert graph.metadata["fallback_to_full_context"] is False


def test_persist_round_routing_prompt_decision_tracks_history_and_counts():
    session = MeetingSession.new(
        workspace_id="ws-001",
        project_id="proj-001",
        thread_id="thread-001",
        agenda=["Trace prompt mode history"],
    )
    engine = _RoundProgressHarness(session=session)
    sparse_graph = build_round_routing_graph(
        session_id=session.id,
        round_number=1,
        agenda=session.agenda,
        facilitator_summary="Short summary",
        planner_proposals=[],
        critic_notes=[],
    )
    sparse_graph.metadata["next_role_id"] = "planner"
    engine._mark_round_routing_prompt_mode(sparse_graph, next_role_id="planner")
    engine._persist_round_routing_prompt_decision(sparse_graph)

    compressed_graph = build_executor_routing_graph(
        session_id=session.id,
        round_number=2,
        agenda=session.agenda,
        facilitator_summary="A" * 800,
        decision="B" * 800,
        planner_proposals=["C" * 800],
        critic_notes=["D" * 800],
    )
    compressed_graph.metadata["next_role_id"] = "executor"
    engine._mark_round_routing_prompt_mode(
        compressed_graph,
        next_role_id="executor",
    )
    engine._persist_round_routing_prompt_decision(compressed_graph)

    last_decision = session.metadata["last_round_routing_prompt_decision"]
    assert last_decision["round_number"] == 2
    assert last_decision["role_id"] == "executor"
    assert last_decision["prompt_mode"] == "compressed_sparse"
    assert last_decision["reason"] == "context_pressure"
    assert last_decision["compressed_packet_char_limit"] == 96
    assert session.metadata["round_routing_prompt_mode_counts"] == {
        "sparse": 1,
        "compressed_sparse": 1,
    }
    assert session.metadata["round_routing_prompt_mode_summary"] == {
        "total_decisions": 2,
        "sparse_count": 1,
        "compressed_count": 1,
        "fallback_count": 0,
        "adaptive_count": 1,
        "sparse_ratio": 0.5,
        "compressed_ratio": 0.5,
        "fallback_ratio": 0.0,
        "adaptive_ratio": 0.5,
        "health_status": "warning",
        "health_reason": "compression_pressure",
        "last_prompt_mode": "compressed_sparse",
        "last_prompt_role_id": "executor",
        "last_prompt_reason": "context_pressure",
        "last_round_number": 2,
        "last_recorded_at": last_decision["recorded_at"],
    }
    assert len(session.metadata["round_routing_prompt_mode_history"]) == 2
    assert session.metadata["round_routing_prompt_mode_history"][0]["prompt_mode"] == (
        "sparse"
    )
    assert session.metadata["round_routing_prompt_mode_history"][-1][
        "prompt_mode"
    ] == "compressed_sparse"
    assert engine.session_store.updated_sessions[-1] is session


@pytest.mark.asyncio
async def test_stage_compile_contract_times_out_playbook_discovery_and_continues(
    monkeypatch,
):
    import backend.app.models.request_contract as request_contract_module
    import backend.app.services.orchestration.meeting.engine as engine_module

    session = MeetingSession.new(
        workspace_id="ws-001",
        project_id="proj-001",
        thread_id="thread-001",
        agenda=["Trace compile contract timeout"],
    )
    engine = _CompileContractHarness(session=session)

    async def _hang_discovery():
        await asyncio.sleep(0.05)
        return "should not complete"

    async def _compile_with_llm(cls, **kwargs):
        return _FakeRequestContract()

    engine._async_load_installed_playbooks = _hang_discovery
    monkeypatch.setattr(
        engine_module,
        "COMPILE_CONTRACT_PLAYBOOK_DISCOVERY_TIMEOUT_S",
        0.01,
    )
    monkeypatch.setattr(
        request_contract_module.RequestContract,
        "compile_with_llm",
        classmethod(_compile_with_llm),
    )

    await engine._stage_compile_contract("Investigate compile contract stall")

    assert engine._available_playbooks_cache == "(playbook discovery timed out)"
    assert engine._request_contract is not None
    assert session.metadata["request_contract"]["deliverables"][0]["id"] == "D1"
    assert engine.emitted_stages[-1] == (
        "deliberation",
        "Starting multi-role deliberation...",
    )


@pytest.mark.asyncio
async def test_stage_compile_contract_times_out_request_contract_compile(
    monkeypatch,
):
    import backend.app.models.request_contract as request_contract_module
    import backend.app.services.orchestration.meeting.engine as engine_module

    session = MeetingSession.new(
        workspace_id="ws-001",
        project_id="proj-001",
        thread_id="thread-001",
        agenda=["Trace request contract timeout"],
    )
    engine = _CompileContractHarness(session=session)

    async def _load_playbooks():
        return "- project_breakdown: Project Breakdown"

    async def _hang_compile_with_llm(cls, **kwargs):
        await asyncio.sleep(0.05)
        return _FakeRequestContract()

    engine._async_load_installed_playbooks = _load_playbooks
    monkeypatch.setattr(
        engine_module,
        "COMPILE_CONTRACT_REQUEST_TIMEOUT_S",
        0.01,
    )
    monkeypatch.setattr(
        request_contract_module.RequestContract,
        "compile_with_llm",
        classmethod(_hang_compile_with_llm),
    )

    await engine._stage_compile_contract("Investigate request contract stall")

    assert engine._available_playbooks_cache == "- project_breakdown: Project Breakdown"
    assert engine._request_contract is None
    assert "request_contract" not in (session.metadata or {})
    assert engine.emitted_stages[-1] == (
        "deliberation",
        "Starting multi-role deliberation...",
    )


@pytest.mark.asyncio
async def test_stage_deliberation_salvages_quota_failure_after_planner_progress(
    monkeypatch,
):
    import backend.app.services.orchestration.meeting.engine as engine_module

    session = MeetingSession.new(
        workspace_id="ws-001",
        project_id="proj-001",
        thread_id="thread-001",
        agenda=["Trace quota fallback"],
    )
    session.max_rounds = 5
    engine = _RoundProgressHarness(session=session)
    monkeypatch.setattr(
        engine_module,
        "select_deliberation_depth",
        lambda **kwargs: DeliberationDepth.STANDARD,
    )
    engine.ctx = SimpleNamespace(budget_headroom_pct=1.0)
    engine._rag_tool_cache = []
    engine.orchestrator = SimpleNamespace(
        should_stop=lambda: False,
        record_iteration=lambda: None,
        record_turn=lambda: None,
        record_error=lambda: None,
    )
    engine._start_session = lambda: None
    engine._emit_meeting_stage = AsyncMock()
    engine._emit_round_event = lambda *args, **kwargs: None
    engine._emit_turn = lambda *args, **kwargs: None
    engine._emit_decision_proposal = lambda *args, **kwargs: None
    engine._try_coverage_audit = AsyncMock()
    engine._prepare_round_routing_graph = lambda *args, **kwargs: None
    engine._persist_round_progress = lambda *args, **kwargs: None
    engine._emit_decision_final = lambda *args, **kwargs: None
    engine._is_converged = lambda *args, **kwargs: False

    engine._role_turn = AsyncMock(
        side_effect=[
            RoleTurnResult("facilitator", "facilitator", 1, "fac-1"),
            RoleTurnResult("planner", "planner", 1, "plan-1"),
            RoleTurnResult("critic", "critic", 1, "critic-1"),
            RoleTurnResult("facilitator", "facilitator", 2, "fac-2"),
            RoleTurnResult("planner", "planner", 2, "plan-2"),
            RoleTurnResult("critic", "critic", 2, "critic-2"),
            RoleTurnResult("facilitator", "facilitator", 3, "fac-3"),
            RoleTurnResult("planner", "planner", 3, "plan-3"),
            RuntimeError(
                "Meeting turn failed for role 'critic' at round 3: "
                "Meeting turn generation failed: Preferred agent 'codex_cli' failed: "
                "You've hit your usage limit."
            ),
        ]
    )

    decision, planner_proposals, critic_notes, converged = await engine._stage_deliberation(
        "Trace quota fallback"
    )

    assert decision == "plan-3"
    assert planner_proposals == ["plan-1", "plan-2", "plan-3"]
    assert critic_notes == ["critic-1", "critic-2"]
    assert converged is False
    assert session.status.value != "failed"
    assert session.metadata["last_round_status"] == "quota_fallback"
    assert session.metadata["partial_rounds"] == 3
    assert session.metadata["deliberation_fallback"]["reason"] == (
        "runtime_quota_or_rate_limit"
    )
    assert session.metadata["deliberation_fallback"]["decision_source"] == (
        "latest_planner_proposal"
    )
