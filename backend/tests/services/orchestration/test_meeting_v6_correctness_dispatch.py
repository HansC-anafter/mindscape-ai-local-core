import importlib

import pytest
from unittest.mock import AsyncMock, MagicMock

from meeting_v6_test_support import StubMixin


class TestCorrectnessFeedbackDispatch:
    @pytest.mark.asyncio
    async def test_stage_dispatch_skips_plan_only_manual_verification(
        self, monkeypatch
    ):
        from backend.app.models.action_intent import ActionIntent
        from backend.app.services.orchestration.meeting.engine import MeetingEngine

        class StubEngine(StubMixin):
            pass

        engine = StubEngine()
        engine.session.metadata = {"phase_attempts": {}}
        engine.session.created_at = None
        engine.workspace = MagicMock(id="ws-default")
        engine.model_name = None
        engine._available_playbooks_cache = ""
        engine._request_contract = None
        engine.execution_launcher = None
        engine.tasks_store = MagicMock()
        engine._emit_meeting_stage = AsyncMock()

        compiled_ir = MagicMock(phases=[MagicMock(id="native.spatial.verification")])
        engine._compile_to_task_ir = MagicMock(return_value=compiled_ir)

        dispatch_module = importlib.import_module(
            "backend.app.services.orchestration.dispatch_orchestrator"
        )

        class _UnexpectedDispatchOrchestrator:
            def __init__(self, **kwargs):
                raise AssertionError("plan-only verification must not dispatch runtime")

        monkeypatch.setattr(
            dispatch_module,
            "DispatchOrchestrator",
            _UnexpectedDispatchOrchestrator,
        )

        action_intents = [
            ActionIntent(
                intent_id="native.spatial.verification",
                title="Verify target scene readiness",
                description="Stop dispatch if required inputs are missing.",
                engine="manual:verification",
                priority="high",
            )
        ]
        action_items = [intent.to_action_item_dict() for intent in action_intents]

        result_ir, dispatch_result = await MeetingEngine._stage_decompose_and_dispatch(
            engine,
            decision="S7 decision",
            action_intents=action_intents,
            action_items=action_items,
        )

        assert result_ir is compiled_ir
        assert dispatch_result["status"] == "skipped"
        assert dispatch_result["reason"] == "plan_only_no_actuator"
        assert action_items[0]["landing_status"] == "planned"

    @pytest.mark.asyncio
    async def test_stage_dispatch_filters_low_priority_when_remediation_active(
        self, monkeypatch
    ):
        from backend.app.models.action_intent import ActionIntent
        from backend.app.services.orchestration.meeting.engine import MeetingEngine

        class StubEngine(StubMixin):
            pass

        engine = StubEngine()
        engine.session.metadata = {
            "correctness_signals": {
                "quality_score": 0.35,
                "acceptance_pass_rate": 0.25,
                "remediation_round": 1,
            },
            "phase_attempts": {},
        }
        engine.session.created_at = None
        engine.workspace = MagicMock(id="ws-default")
        engine.model_name = None
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
            captured["decision"] = decision
            captured["compiled_intent_ids"] = [i.intent_id for i in action_intents]
            captured["compiled_titles"] = [i.title for i in action_intents]
            captured["action_item_titles"] = [item["title"] for item in action_items]
            return MagicMock(phases=[])

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

        class _FakePolicy:
            max_phases_per_wave = 2

        class _FakeTaskDecomposer:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

            async def decompose(self, **kwargs):
                return None

        monkeypatch.setattr(
            task_decomposer_module.DecompositionPolicy,
            "from_scale",
            staticmethod(lambda _scale: _FakePolicy()),
        )
        monkeypatch.setattr(
            task_decomposer_module,
            "TaskDecomposer",
            _FakeTaskDecomposer,
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
                return {
                    "status": "ok",
                    "phase_results": [],
                    "compiled_titles": captured["compiled_titles"],
                }

        monkeypatch.setattr(
            dispatch_module,
            "DispatchOrchestrator",
            _FakeDispatchOrchestrator,
        )

        action_intents = [
            ActionIntent(
                title="Optional expansion",
                description="nice to have",
                tool_name="tool.optional",
                priority="low",
            ),
            ActionIntent(
                title="Critical remediation",
                description="must fix failed output",
                tool_name="tool.fix",
                priority="high",
            ),
        ]
        action_items = [intent.to_action_item_dict() for intent in action_intents]

        compiled_ir, dispatch_result = await MeetingEngine._stage_decompose_and_dispatch(
            engine,
            decision="Continue with remediation",
            action_intents=action_intents,
            action_items=action_items,
        )

        assert compiled_ir is not None
        assert captured["compiled_titles"] == ["Critical remediation"]
        assert dispatch_result["compiled_titles"] == ["Critical remediation"]
        assert captured["action_item_titles"] == [
            "Optional expansion",
            "Critical remediation",
        ]
