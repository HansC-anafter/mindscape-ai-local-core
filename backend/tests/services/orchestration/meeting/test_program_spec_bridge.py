from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from backend.app.models.meeting_session import MeetingSession
from backend.app.models.program_spec import ProgramSpec
from backend.app.models.request_contract import DeliverableSpec, RequestContract
from backend.app.models.request_contract import ScaleEstimate
from backend.app.models.task_ir import PhaseIR, TaskIR
from backend.app.services.orchestration.meeting._dispatch_pipeline import (
    stage_decompose_and_dispatch,
)
from backend.app.services.orchestration.meeting.engine import MeetingEngine
from backend.app.services.orchestration.meeting.program_spec_bridge import (
    action_intents_from_program_spec,
    parse_program_spec_from_output,
)


class _FakeSessionStore:
    def __init__(self) -> None:
        self.updated_sessions: list[MeetingSession] = []

    def update(self, session: MeetingSession) -> None:
        self.updated_sessions.append(session)


class _ActionStageHarness(MeetingEngine):
    def __init__(self, session: MeetingSession, executor_output: str) -> None:
        self.session = session
        self.session_store = _FakeSessionStore()
        self.workspace = SimpleNamespace(id=session.workspace_id)
        self.profile_id = "profile-001"
        self.thread_id = session.thread_id
        self.project_id = session.project_id
        self.model_name = "gpt-5.4"
        self._request_contract = SimpleNamespace(scale_estimate=ScaleEstimate.PROGRAM)
        self._executor_output = executor_output
        self._rag_tool_cache = []
        self._pending_program_spec = None
        self._pending_program_spec_source = None

    async def _emit_meeting_stage(self, stage: str, message: str) -> None:
        return None

    async def _role_turn(self, *args, **kwargs):
        return SimpleNamespace(content=self._executor_output)

    async def _gap_refetch_for_null_actuators(self, action_intents, **kwargs):
        return action_intents

    def _emit_turn(self, turn) -> None:
        return None

    def _has_workspace_tool_bindings(self) -> bool:
        return False


class _DispatchHarness:
    def __init__(self, session: MeetingSession) -> None:
        self.session = session
        self.execution_launcher = None
        self.tasks_store = None
        self.profile_id = "profile-001"
        self.project_id = session.project_id
        self.model_name = "gpt-5.4"
        self._request_contract = SimpleNamespace(scale_estimate=ScaleEstimate.PROGRAM)

    async def _emit_meeting_stage(self, stage: str, message: str) -> None:
        return None

    def _build_tool_inventory_block(self) -> str:
        return ""

    def _compile_to_task_ir(self, **kwargs) -> TaskIR:
        return TaskIR(
            task_id="task-001",
            intent_instance_id="intent-instance-001",
            workspace_id=self.session.workspace_id,
            actor_id="meeting-engine",
            phases=[
                PhaseIR(
                    id="fallback-phase",
                    source_intent_id="fallback-intent",
                    name="Fallback",
                    description="Fallback compiled phase",
                )
            ],
        )

    def _get_handoff_registry_store(self):
        return None

    def _get_pack_dispatch_adapter(self):
        return None


class _QuotaFallbackHarness(_ActionStageHarness):
    def __init__(
        self,
        session: MeetingSession,
        request_contract: RequestContract,
    ) -> None:
        super().__init__(session=session, executor_output="")
        self._request_contract = request_contract

    async def _role_turn(self, *args, **kwargs):
        raise RuntimeError(
            "Meeting turn generation failed: Preferred agent 'codex_cli' failed: "
            "You've hit your usage limit."
        )


class _QuotaFallbackWithToolContextHarness(_QuotaFallbackHarness):
    def __init__(
        self,
        session: MeetingSession,
        request_contract: RequestContract,
    ) -> None:
        super().__init__(session=session, request_contract=request_contract)
        self.role_turn_calls = 0
        self.gap_refetch_calls = 0

    async def _role_turn(self, *args, **kwargs):
        self.role_turn_calls += 1
        return await super()._role_turn(*args, **kwargs)

    async def _gap_refetch_for_null_actuators(self, action_intents, **kwargs):
        self.gap_refetch_calls += 1
        raise AssertionError(
            "gap-refetch should be skipped for request_contract_fallback"
        )

    def _has_workspace_tool_bindings(self) -> bool:
        return True


def test_parse_program_spec_from_output_accepts_structured_workstreams():
    executor_output = json.dumps(
        {
            "workstreams": [
                {
                    "id": "WS1",
                    "name": "Season Bible",
                    "description": "Lock the core world bible.",
                    "produces_deliverables": ["D1"],
                    "estimated_units": 1,
                    "eligible_engines": ["playbook:project_breakdown"],
                },
                {
                    "id": "WS2",
                    "name": "Episode Beats",
                    "description": "Draft episodic beat structure.",
                    "produces_deliverables": ["D2"],
                    "eligible_engines": ["tool:storyboard.generate"],
                    "depends_on": ["WS1"],
                },
            ],
            "dependency_graph": {"WS2": ["WS1"]},
            "target_outputs": ["series_bible", "episode_beat_sheet"],
            "scale": "program",
        }
    )

    program_spec = parse_program_spec_from_output(executor_output)

    assert program_spec is not None
    assert program_spec.scale == ScaleEstimate.PROGRAM
    assert program_spec.dependency_graph == {"WS1": [], "WS2": ["WS1"]}
    assert program_spec.workstreams[0].produces_deliverables == ["D1"]
    assert program_spec.workstreams[0].eligible_engines == [
        "playbook:project_breakdown"
    ]
    assert program_spec.workstreams[1].eligible_engines == ["tool:storyboard.generate"]


@pytest.mark.asyncio
async def test_stage_extract_actions_persists_executor_structured_program_spec():
    session = MeetingSession.new(
        workspace_id="ws-001",
        project_id="proj-001",
        thread_id="thread-001",
        agenda=["Bridge ProgramSpec into runtime"],
    )
    session.metadata = {"last_coverage_matrix": {"covered_deliverables": ["D1"]}}
    executor_output = json.dumps(
        {
            "workstreams": [
                {
                    "id": "WS1",
                    "name": "Series Bible",
                    "description": "Draft the long-form series bible.",
                    "produces_deliverables": ["D1"],
                    "eligible_engines": ["playbook:project_breakdown"],
                },
                {
                    "id": "WS2",
                    "name": "Storyboard Seeds",
                    "description": "Draft storyboard seeds for the first arc.",
                    "produces_deliverables": ["D2"],
                    "eligible_engines": ["tool:storyboard.generate"],
                    "depends_on": ["WS1"],
                },
            ],
            "dependency_graph": {"WS2": ["WS1"]},
            "target_outputs": ["series_bible", "storyboard_seed_pack"],
            "scale": "program",
        }
    )
    engine = _ActionStageHarness(session=session, executor_output=executor_output)

    action_intents, action_items = await engine._stage_extract_actions(
        decision="Create a long-horizon story program.",
        user_message="Plan the next season.",
        critic_notes=[],
        planner_proposals=[],
    )

    assert len(action_intents) == 2
    assert action_items[1]["blocked_by"] == ["WS1"]
    assert session.metadata["last_program_spec_source"] == "executor_structured"
    assert session.metadata["last_program_spec_workstream_count"] == 2
    assert session.metadata["last_program_spec"]["coverage_snapshot"] == {
        "covered_deliverables": ["D1"]
    }
    assert session.metadata["last_program_spec"]["dependency_graph"]["WS2"] == ["WS1"]
    assert engine.session_store.updated_sessions[-1] is session


@pytest.mark.asyncio
async def test_stage_extract_actions_bootstraps_program_spec_from_legacy_action_items():
    session = MeetingSession.new(
        workspace_id="ws-001",
        project_id="proj-001",
        thread_id="thread-001",
        agenda=["Fallback bootstrap"],
    )
    executor_output = json.dumps(
        [
            {
                "title": "Outline season structure",
                "description": "Break the season into major arcs.",
                "playbook_code": "project_breakdown",
            },
            {
                "title": "Draft storyboard seed pack",
                "description": "Create first-pass storyboard seeds.",
                "tool_name": "storyboard.generate",
                "blocked_by": [0],
            },
        ]
    )
    engine = _ActionStageHarness(session=session, executor_output=executor_output)

    action_intents, _action_items = await engine._stage_extract_actions(
        decision="Create a long-horizon story program.",
        user_message="Plan the next season.",
        critic_notes=[],
        planner_proposals=[],
    )

    program_spec_payload = session.metadata["last_program_spec"]

    assert session.metadata["last_program_spec_source"] == "action_intent_bootstrap"
    assert len(program_spec_payload["workstreams"]) == 2
    assert program_spec_payload["workstreams"][0]["id"] == action_intents[0].intent_id
    assert program_spec_payload["dependency_graph"][action_intents[1].intent_id] == [
        action_intents[0].intent_id
    ]
    assert program_spec_payload["workstreams"][1]["eligible_engines"] == [
        "tool:storyboard.generate"
    ]


@pytest.mark.asyncio
async def test_stage_extract_actions_falls_back_to_request_contract_deliverables():
    session = MeetingSession.new(
        workspace_id="ws-001",
        project_id="proj-001",
        thread_id="thread-001",
        agenda=["Quota fallback bootstrap"],
    )
    session.metadata = {"last_coverage_matrix": {"covered_deliverables": ["D1", "D2"]}}
    request_contract = RequestContract(
        goals=["Create three markdown deliverables"],
        deliverables=[
            DeliverableSpec(id="D1", name="persona_operating_system.md"),
            DeliverableSpec(id="D2", name="instagram_week1_calendar.md"),
        ],
        scale_estimate=ScaleEstimate.PROGRAM,
    )
    engine = _QuotaFallbackHarness(
        session=session,
        request_contract=request_contract,
    )

    action_intents, action_items = await engine._stage_extract_actions(
        decision="Produce the requested deliverables as publishable markdown files.",
        user_message="Create the deliverables.",
        critic_notes=[],
        planner_proposals=[],
    )

    assert len(action_intents) == 2
    assert action_items[0]["input_params"]["deliverable_id"] == "D1"
    assert action_items[1]["input_params"]["deliverable_name"] == "instagram_week1_calendar.md"
    assert session.metadata["last_program_spec_source"] == "request_contract_fallback"
    assert session.metadata["last_program_spec"]["workstreams"][0][
        "produces_deliverables"
    ] == ["D1"]
    assert session.metadata["last_program_spec"]["workstreams"][1][
        "produces_deliverables"
    ] == ["D2"]


@pytest.mark.asyncio
async def test_stage_extract_actions_skips_null_actuator_retries_for_request_contract_fallback():
    session = MeetingSession.new(
        workspace_id="ws-001",
        project_id="proj-001",
        thread_id="thread-001",
        agenda=["Quota fallback bootstrap with tool context"],
    )
    session.metadata = {"last_coverage_matrix": {"covered_deliverables": ["D1", "D2"]}}
    request_contract = RequestContract(
        goals=["Create three markdown deliverables"],
        deliverables=[
            DeliverableSpec(id="D1", name="persona_operating_system.md"),
            DeliverableSpec(id="D2", name="instagram_week1_calendar.md"),
        ],
        scale_estimate=ScaleEstimate.PROGRAM,
    )
    engine = _QuotaFallbackWithToolContextHarness(
        session=session,
        request_contract=request_contract,
    )

    action_intents, action_items = await engine._stage_extract_actions(
        decision="Produce the requested deliverables as publishable markdown files.",
        user_message="Create the deliverables.",
        critic_notes=[],
        planner_proposals=[],
    )

    assert len(action_intents) == 2
    assert len(action_items) == 2
    assert engine.role_turn_calls == 1
    assert engine.gap_refetch_calls == 0
    assert session.metadata["last_program_spec_source"] == "request_contract_fallback"


@pytest.mark.asyncio
async def test_stage_decompose_and_dispatch_prefers_executor_structured_program_spec(
    monkeypatch,
):
    import backend.app.services.orchestration.dispatch_orchestrator as dispatch_module
    import backend.app.services.orchestration.task_decomposer as decomposer_module

    session = MeetingSession.new(
        workspace_id="ws-001",
        project_id="proj-001",
        thread_id="thread-001",
        agenda=["Dispatch ProgramSpec first"],
    )
    program_spec = ProgramSpec.model_validate(
        {
            "workstreams": [
                {
                    "id": "WS1",
                    "name": "Series Bible",
                    "description": "Draft the series bible.",
                    "estimated_units": 1,
                    "produces_deliverables": ["D1"],
                    "eligible_engines": ["playbook:project_breakdown"],
                },
                {
                    "id": "WS2",
                    "name": "Storyboard Seeds",
                    "description": "Seed the first storyboard pack.",
                    "estimated_units": 1,
                    "produces_deliverables": ["D2"],
                    "eligible_engines": ["tool:storyboard.generate"],
                },
            ],
            "milestones": [],
            "dependency_graph": {"WS2": ["WS1"]},
            "target_outputs": ["series_bible", "storyboard_seed_pack"],
            "scale": "program",
            "coverage_snapshot": {
                "entries": [
                    {
                        "deliverable_id": "D1",
                        "deliverable_name": "Series bible",
                        "covered_by": ["WS1"],
                    },
                    {
                        "deliverable_id": "D2",
                        "deliverable_name": "Storyboard seed pack",
                        "covered_by": ["WS2"],
                    },
                ]
            },
        }
    )
    session.metadata = {
        "last_program_spec": program_spec.model_dump(mode="json"),
        "last_program_spec_source": "executor_structured",
    }
    meeting = _DispatchHarness(session=session)
    action_intents = action_intents_from_program_spec(
        program_spec,
        default_workspace_id=session.workspace_id,
    )
    action_items = [intent.to_action_item_dict() for intent in action_intents]
    captured: dict[str, object] = {}

    class _ExplodingTaskDecomposer:
        def __init__(self, *args, **kwargs) -> None:
            raise AssertionError("TaskDecomposer should be skipped for ProgramSpec")

    class _FakeDispatchOrchestrator:
        def __init__(self, **kwargs) -> None:
            captured["init_kwargs"] = kwargs

        async def execute(self, *, task_ir, action_items):
            captured["task_ir"] = task_ir
            captured["action_items"] = action_items
            return {"status": "ok"}

    monkeypatch.setattr(
        decomposer_module,
        "TaskDecomposer",
        _ExplodingTaskDecomposer,
    )
    monkeypatch.setattr(
        dispatch_module,
        "DispatchOrchestrator",
        _FakeDispatchOrchestrator,
    )

    compiled_ir, dispatch_result = await stage_decompose_and_dispatch(
        meeting,
        decision="Create a long-horizon story program.",
        action_intents=action_intents,
        action_items=action_items,
        handoff_in=SimpleNamespace(
            deliverables=[
                {
                    "name": "series_bible.md",
                    "description": "Series bible markdown",
                },
                {
                    "name": "storyboard_seed_pack.md",
                    "description": "Storyboard seed pack markdown",
                },
            ]
        ),
    )

    assert dispatch_result == {"status": "ok"}
    assert [phase.id for phase in compiled_ir.phases] == ["WS1", "WS2"]
    assert compiled_ir.phases[0].preferred_engine == "playbook:project_breakdown"
    assert compiled_ir.phases[0].input_params["deliverable_id"] == "D1"
    assert compiled_ir.phases[0].input_params["deliverable_path"] == "series_bible.md"
    assert compiled_ir.phases[1].tool_name == "storyboard.generate"
    assert compiled_ir.phases[1].depends_on == ["WS1"]
    assert compiled_ir.phases[1].input_params["deliverable_id"] == "D2"
    assert (
        compiled_ir.phases[1].input_params["deliverable_path"]
        == "storyboard_seed_pack.md"
    )


@pytest.mark.asyncio
async def test_stage_decompose_and_dispatch_accepts_request_contract_fallback_program_spec(
    monkeypatch,
):
    import backend.app.services.orchestration.dispatch_orchestrator as dispatch_module
    import backend.app.services.orchestration.task_decomposer as decomposer_module

    session = MeetingSession.new(
        workspace_id="ws-001",
        project_id="proj-001",
        thread_id="thread-001",
        agenda=["Dispatch contract fallback ProgramSpec"],
    )
    program_spec = ProgramSpec.model_validate(
        {
            "workstreams": [
                {
                    "id": "WS_D1",
                    "name": "persona_operating_system.md",
                    "description": "Create the persona operating system deliverable.",
                    "estimated_units": 1,
                    "produces_deliverables": ["D1"],
                    "eligible_engines": [],
                },
                {
                    "id": "WS_D2",
                    "name": "instagram_week1_calendar.md",
                    "description": "Create the first-week calendar deliverable.",
                    "estimated_units": 1,
                    "produces_deliverables": ["D2"],
                    "eligible_engines": [],
                },
            ],
            "milestones": [],
            "dependency_graph": {"WS_D1": [], "WS_D2": []},
            "target_outputs": [
                "persona_operating_system.md",
                "instagram_week1_calendar.md",
            ],
            "scale": "program",
            "coverage_snapshot": {
                "entries": [
                    {
                        "deliverable_id": "D1",
                        "deliverable_name": "persona_operating_system.md",
                        "covered_by": ["WS_D1"],
                    },
                    {
                        "deliverable_id": "D2",
                        "deliverable_name": "instagram_week1_calendar.md",
                        "covered_by": ["WS_D2"],
                    },
                ]
            },
        }
    )
    session.metadata = {
        "last_program_spec": program_spec.model_dump(mode="json"),
        "last_program_spec_source": "request_contract_fallback",
    }
    meeting = _DispatchHarness(session=session)
    action_intents = action_intents_from_program_spec(
        program_spec,
        default_workspace_id=session.workspace_id,
    )
    action_items = [intent.to_action_item_dict() for intent in action_intents]

    class _ExplodingTaskDecomposer:
        def __init__(self, *args, **kwargs) -> None:
            raise AssertionError("TaskDecomposer should be skipped for ProgramSpec")

    class _FakeDispatchOrchestrator:
        def __init__(self, **kwargs) -> None:
            return None

        async def execute(self, *, task_ir, action_items):
            return {"status": "ok"}

    monkeypatch.setattr(
        decomposer_module,
        "TaskDecomposer",
        _ExplodingTaskDecomposer,
    )
    monkeypatch.setattr(
        dispatch_module,
        "DispatchOrchestrator",
        _FakeDispatchOrchestrator,
    )

    compiled_ir, dispatch_result = await stage_decompose_and_dispatch(
        meeting,
        decision="Produce the requested deliverables.",
        action_intents=action_intents,
        action_items=action_items,
        handoff_in=SimpleNamespace(
            deliverables=[
                {
                    "name": "persona_operating_system.md",
                    "description": "Persona operating system markdown",
                },
                {
                    "name": "instagram_week1_calendar.md",
                    "description": "Week-one calendar markdown",
                },
            ]
        ),
    )

    assert dispatch_result == {"status": "ok"}
    assert [phase.id for phase in compiled_ir.phases] == ["WS_D1", "WS_D2"]
    assert compiled_ir.phases[0].preferred_engine == "agent:auto"
    assert compiled_ir.phases[0].tool_name is None
    assert compiled_ir.phases[0].input_params["deliverable_id"] == "D1"
    assert (
        compiled_ir.phases[0].input_params["deliverable_path"]
        == "persona_operating_system.md"
    )
    assert compiled_ir.phases[1].input_params["deliverable_id"] == "D2"


def test_action_intents_from_program_spec_includes_deliverable_bindings():
    program_spec = ProgramSpec.model_validate(
        {
            "workstreams": [
                {
                    "id": "WS1",
                    "name": "Persona OS",
                    "description": "Create the persona operating system.",
                    "estimated_units": 1,
                    "produces_deliverables": ["D1"],
                    "eligible_engines": ["playbook:cis_mind_identity"],
                }
            ],
            "milestones": [],
            "dependency_graph": {"WS1": []},
            "target_outputs": ["persona_operating_system.md"],
            "scale": "program",
            "coverage_snapshot": {
                "entries": [
                    {
                        "deliverable_id": "D1",
                        "deliverable_name": "persona_operating_system.md",
                        "covered_by": ["WS1"],
                    }
                ]
            },
        }
    )

    action_intents = action_intents_from_program_spec(
        program_spec,
        default_workspace_id="ws-001",
        deliverable_bindings={
            "D1": {
                "deliverable_id": "D1",
                "deliverable_name": "persona_operating_system.md",
                "deliverable_path": "persona_operating_system.md",
            }
        },
    )

    assert len(action_intents) == 1
    assert action_intents[0].input_params["deliverable_id"] == "D1"
    assert (
        action_intents[0].input_params["deliverable_path"]
        == "persona_operating_system.md"
    )
