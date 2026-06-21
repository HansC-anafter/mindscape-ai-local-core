import importlib

import pytest
from unittest.mock import AsyncMock, MagicMock


class TestMeetingV6PdStoryboardVisibility:
    @pytest.mark.asyncio
    async def test_pd_storyboard_route_skips_task_decomposer(self, monkeypatch):
        import importlib

        from backend.app.models.action_intent import ActionIntent
        from backend.app.services.orchestration.meeting.engine import MeetingEngine

        engine = MeetingEngine.__new__(MeetingEngine)
        engine.session = MagicMock()
        engine.session.id = "session-pd-atomic"
        engine.session.workspace_id = "ws-pd-atomic"
        engine.session.metadata = {"phase_attempts": {}}
        engine.session.created_at = None
        engine.workspace = MagicMock(id="ws-pd-atomic")
        engine.model_name = None
        engine.profile_id = "default-user"
        engine.project_id = "proj-pd-atomic"
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
            return MagicMock(phases=["pd-phase"])

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
                    "TaskDecomposer should be skipped for atomic PD storyboard routes"
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
                intent_id="PD_pd_intake_storyboard_preview",
                title="Create PD session and execute storyboard preview",
                description="Run the deterministic PD intake storyboard route.",
                playbook_code="pd_intake_storyboard_preview",
                engine="playbook:pd_intake_storyboard_preview",
                priority="high",
                target_workspace_id="ws-pd-atomic",
                input_params={
                    "workspace_id": "ws-pd-atomic",
                    "project_id": "proj-pd-atomic",
                    "reference_id": "ref_001",
                    "intent": {"capture_moment": "hero frame"},
                    "source_type": "human",
                },
            )
        ]
        action_items = [intent.to_action_item_dict() for intent in action_intents]

        compiled_ir, dispatch_result = await MeetingEngine._stage_decompose_and_dispatch(
            engine,
            decision="Run atomic PD route",
            action_intents=action_intents,
            action_items=action_items,
        )

        assert compiled_ir is not None
        assert dispatch_result["status"] == "ok"
        assert captured["compiled_intent_ids"] == ["PD_pd_intake_storyboard_preview"]
        assert captured["compiled_titles"] == [
            "Create PD session and execute storyboard preview"
        ]
        assert captured["action_item_titles"] == [
            "Create PD session and execute storyboard preview"
        ]
        assert captured["dispatched_phases"] == ["pd-phase"]

    def test_create_request_accepts_visibility(self):
        """CreateWorkspaceRequest can carry visibility field."""
        from backend.app.models.workspace import (
            CreateWorkspaceRequest,
            WorkspaceVisibility,
        )

        req = CreateWorkspaceRequest(
            title="New WS",
            visibility=WorkspaceVisibility.DISCOVERABLE,
        )
        assert req.visibility == WorkspaceVisibility.DISCOVERABLE

    def test_create_request_visibility_none_is_safe(self):
        """CreateWorkspaceRequest with visibility=None doesn't break Workspace()."""
        from backend.app.models.workspace import (
            Workspace,
            CreateWorkspaceRequest,
            WorkspaceVisibility,
        )

        req = CreateWorkspaceRequest(title="No Vis")
        # Simulate crud.py logic
        vis = req.visibility if req.visibility else WorkspaceVisibility.PRIVATE
        ws = Workspace(
            id="ws-test",
            title=req.title,
            owner_user_id="u1",
            visibility=vis,
        )
        assert ws.visibility == WorkspaceVisibility.PRIVATE
