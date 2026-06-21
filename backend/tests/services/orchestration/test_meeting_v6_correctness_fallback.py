import asyncio
import importlib

import pytest
from unittest.mock import AsyncMock, MagicMock



class TestCorrectnessFeedbackFallback:
    @pytest.mark.asyncio
    async def test_stage_agenda_and_rag_times_out_nonfatally(self, monkeypatch):
        from backend.app.services.orchestration.meeting.engine import MeetingEngine
        import backend.app.services.orchestration.meeting.engine_core.pipeline_stages_mixin as pipeline_stages_module

        engine = MeetingEngine.__new__(MeetingEngine)
        engine.session = MagicMock()
        engine.session.id = "session-rag-timeout"
        engine.session.workspace_id = "ws-rag-timeout"
        engine.session.agenda = ["Deliverable A", "Deliverable B"]
        engine.session.metadata = {}
        engine.session_store = MagicMock()
        engine._ensure_agenda_decomposed = AsyncMock()
        engine._emit_meeting_stage = AsyncMock()
        engine._verb_augment = MagicMock(return_value="")
        engine._build_tool_query_from_context = MagicMock(return_value="fallback query")

        async def _fake_retrieve(_query, top_k=15, workspace_id=None):
            return [
                {
                    "tool_id": f"{workspace_id}:{top_k}",
                    "display_name": "x",
                    "description": "y",
                }
            ]

        async def _fake_wait_for(awaitable, timeout):
            awaitable.close()
            raise asyncio.TimeoutError

        tool_rag_module = importlib.import_module("backend.app.services.tool_rag")
        monkeypatch.setattr(tool_rag_module, "retrieve_relevant_tools", _fake_retrieve)
        monkeypatch.setattr(pipeline_stages_module.asyncio, "wait_for", _fake_wait_for)

        await MeetingEngine._stage_agenda_and_rag(engine, "Create the handoff outputs")

        assert engine._rag_tool_cache == []
        engine._emit_meeting_stage.assert_any_await("agenda", "Analyzing agenda...")
        engine._emit_meeting_stage.assert_any_await(
            "tool_discovery", "Discovering available tools..."
        )

    @pytest.mark.asyncio
    async def test_policy_gate_fallback_skips_task_decomposer(self, monkeypatch):
        import importlib

        from backend.app.models.action_intent import ActionIntent
        from backend.app.services.orchestration.meeting.engine import MeetingEngine

        engine = MeetingEngine.__new__(MeetingEngine)
        engine.session = MagicMock()
        engine.session.id = "session-fallback"
        engine.session.workspace_id = "ws-fallback"
        engine.session.metadata = {
            "policy_gate_fallback": {
                "reason": "policy_blocked_deliverables",
                "replacement_intent_ids": ["WS_D1", "WS_D2", "WS_D3"],
            },
            "phase_attempts": {},
        }
        engine.session.created_at = None
        engine.workspace = MagicMock(id="ws-fallback")
        engine.model_name = None
        engine.profile_id = "default-user"
        engine.project_id = "proj-fallback"
        engine._available_playbooks_cache = ""
        engine._request_contract = None
        engine.execution_launcher = None
        engine.tasks_store = MagicMock()
        engine._emit_meeting_stage = AsyncMock()
        engine._build_tool_inventory_block = MagicMock(return_value="")
        engine._get_handoff_registry_store = MagicMock(return_value=None)
        engine._get_pack_dispatch_adapter = MagicMock(return_value=None)

        captured = {}

        def _compile_to_task_ir(*, decision, action_items, handoff_in, action_intents):
            captured["compiled_titles"] = [i.title for i in action_intents]
            captured["compiled_intent_ids"] = [i.intent_id for i in action_intents]
            captured["action_item_titles"] = [item["title"] for item in action_items]
            return MagicMock(phases=["fallback-phase"])

        engine._compile_to_task_ir = MagicMock(side_effect=_compile_to_task_ir)

        llm_adapter_module = importlib.import_module(
            "backend.app.services.orchestration.meeting.meeting_llm_adapter"
        )
        monkeypatch.setattr(
            llm_adapter_module.MeetingLLMAdapter,
            "from_engine",
            staticmethod(lambda _engine: MagicMock()),
        )

        task_decomposer_module = importlib.import_module(
            "backend.app.services.orchestration.task_decomposer"
        )

        class _ExplodingTaskDecomposer:
            def __init__(self, **kwargs):
                raise AssertionError(
                    "TaskDecomposer should be skipped when policy fallback is active"
                )

        monkeypatch.setattr(
            task_decomposer_module,
            "TaskDecomposer",
            _ExplodingTaskDecomposer,
        )

        dispatch_module = importlib.import_module(
            "backend.app.services.orchestration.dispatch_orchestrator"
        )

        class _FakeDispatchOrchestrator:
            def __init__(self, **kwargs):
                captured["dispatch_init"] = kwargs

            async def execute(self, task_ir, action_items):
                captured["dispatched_action_item_titles"] = [
                    item["title"] for item in action_items
                ]
                captured["dispatched_phases"] = task_ir.phases
                return {"status": "ok", "phase_results": []}

        monkeypatch.setattr(
            dispatch_module,
            "DispatchOrchestrator",
            _FakeDispatchOrchestrator,
        )

        action_intents = [
            ActionIntent(
                intent_id="WS_D1",
                title="persona_operating_system.md",
                description="fallback writer for D1",
                engine="agent:codex_cli",
                priority="high",
            ),
            ActionIntent(
                intent_id="WS_D2",
                title="instagram_week1_calendar.md",
                description="fallback writer for D2",
                engine="agent:codex_cli",
                priority="high",
            ),
            ActionIntent(
                intent_id="WS_D3",
                title="reel_hook_bank.md",
                description="fallback writer for D3",
                engine="agent:codex_cli",
                priority="high",
            ),
        ]
        action_items = [intent.to_action_item_dict() for intent in action_intents]

        compiled_ir, dispatch_result = await MeetingEngine._stage_decompose_and_dispatch(
            engine,
            decision="Fallback writers only",
            action_intents=action_intents,
            action_items=action_items,
        )

        assert compiled_ir is not None
        assert dispatch_result["status"] == "ok"
        assert captured["compiled_intent_ids"] == ["WS_D1", "WS_D2", "WS_D3"]
        assert captured["compiled_titles"] == [
            "persona_operating_system.md",
            "instagram_week1_calendar.md",
            "reel_hook_bank.md",
        ]
        assert captured["action_item_titles"] == [
            "persona_operating_system.md",
            "instagram_week1_calendar.md",
            "reel_hook_bank.md",
        ]
        assert captured["dispatched_phases"] == ["fallback-phase"]

    @pytest.mark.asyncio
    async def test_policy_gate_fallback_forces_replacement_intents_through_dispatch_gate(
        self, monkeypatch
    ):
        import importlib

        from backend.app.models.action_intent import ActionIntent
        from backend.app.services.orchestration.meeting.engine import MeetingEngine

        engine = MeetingEngine.__new__(MeetingEngine)
        engine.session = MagicMock()
        engine.session.id = "session-fallback-gate-bypass"
        engine.session.workspace_id = "ws-fallback-gate-bypass"
        engine.session.metadata = {
            "policy_gate_fallback": {
                "reason": "policy_blocked_deliverables",
                "replacement_intent_ids": ["WS_D1", "WS_D2", "WS_D3"],
                "preserved_intent_ids": ["PD_pd_intake_storyboard_preview"],
            },
            "phase_attempts": {},
        }
        engine.session.created_at = None
        engine.workspace = MagicMock(id="ws-fallback-gate-bypass")
        engine.model_name = None
        engine.profile_id = "default-user"
        engine.project_id = "proj-fallback-gate-bypass"
        engine._available_playbooks_cache = ""
        engine._request_contract = None
        engine.execution_launcher = None
        engine.tasks_store = MagicMock()
        engine._emit_meeting_stage = AsyncMock()
        engine._build_tool_inventory_block = MagicMock(return_value="")
        engine._get_handoff_registry_store = MagicMock(return_value=None)
        engine._get_pack_dispatch_adapter = MagicMock(return_value=None)

        captured = {}

        def _compile_to_task_ir(*, decision, action_items, handoff_in, action_intents):
            captured["compiled_intent_ids"] = [i.intent_id for i in action_intents]
            captured["compiled_titles"] = [i.title for i in action_intents]
            return MagicMock(phases=["fallback-phase"])

        engine._compile_to_task_ir = MagicMock(side_effect=_compile_to_task_ir)

        llm_adapter_module = importlib.import_module(
            "backend.app.services.orchestration.meeting.meeting_llm_adapter"
        )
        monkeypatch.setattr(
            llm_adapter_module.MeetingLLMAdapter,
            "from_engine",
            staticmethod(lambda _engine: MagicMock()),
        )

        task_decomposer_module = importlib.import_module(
            "backend.app.services.orchestration.task_decomposer"
        )

        class _ExplodingTaskDecomposer:
            def __init__(self, **kwargs):
                raise AssertionError(
                    "TaskDecomposer should be skipped when policy fallback is active"
                )

        monkeypatch.setattr(
            task_decomposer_module,
            "TaskDecomposer",
            _ExplodingTaskDecomposer,
        )

        dispatch_module = importlib.import_module(
            "backend.app.services.orchestration.dispatch_orchestrator"
        )

        class _FakeDispatchOrchestrator:
            def __init__(self, **kwargs):
                captured["dispatch_init"] = kwargs

            async def execute(self, task_ir, action_items):
                captured["dispatched_action_item_titles"] = [
                    item["title"] for item in action_items
                ]
                return {"status": "ok", "phase_results": []}

        monkeypatch.setattr(
            dispatch_module,
            "DispatchOrchestrator",
            _FakeDispatchOrchestrator,
        )

        long_desc = " ".join(["word"] * 150)
        action_intents = [
            ActionIntent(
                intent_id="PD_pd_intake_storyboard_preview",
                title="Create PD session and execute storyboard preview",
                description="Create storyboard preview through PD intake and MMS.",
                playbook_code="pd_intake_storyboard_preview",
                engine="playbook:pd_intake_storyboard_preview",
                priority="high",
            ),
            ActionIntent(
                intent_id="WS_D1",
                title="persona_operating_system.md",
                description="fallback writer for D1",
                engine="agent:codex_cli",
                priority="high",
            ),
            ActionIntent(
                intent_id="WS_D2",
                title="instagram_week1_calendar.md",
                description=long_desc,
                engine="agent:codex_cli",
                priority="high",
            ),
            ActionIntent(
                intent_id="WS_D3",
                title="reel_hook_bank.md",
                description=long_desc,
                engine="agent:codex_cli",
                priority="high",
            ),
        ]
        action_items = [intent.to_action_item_dict() for intent in action_intents]
        action_items[0]["playbook_code"] = "pd_intake_storyboard_preview"

        compiled_ir, dispatch_result = await MeetingEngine._stage_decompose_and_dispatch(
            engine,
            decision="PD route plus fallback writers",
            action_intents=action_intents,
            action_items=action_items,
        )

        assert compiled_ir is not None
        assert dispatch_result["status"] == "ok"
        assert captured["compiled_intent_ids"] == [
            "PD_pd_intake_storyboard_preview",
            "WS_D1",
            "WS_D2",
            "WS_D3",
        ]
        assert captured["compiled_titles"] == [
            "Create PD session and execute storyboard preview",
            "persona_operating_system.md",
            "instagram_week1_calendar.md",
            "reel_hook_bank.md",
        ]
        assert captured["dispatched_action_item_titles"] == [
            "Create PD session and execute storyboard preview",
            "persona_operating_system.md",
            "instagram_week1_calendar.md",
            "reel_hook_bank.md",
        ]
