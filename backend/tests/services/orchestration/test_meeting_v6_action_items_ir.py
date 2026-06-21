import json

import pytest
from unittest.mock import MagicMock

from backend.app.models.task_ir import PhaseIR
from meeting_v6_test_support import StubMixin


class TestBuildActionItemsRaw:
    """PF-1: _build_action_items no longer calls _land_action_item."""

    @pytest.mark.asyncio
    async def test_returns_raw_parsed_items(self):
        from backend.app.services.orchestration.meeting._action_items import (
            MeetingActionItemsMixin,
        )

        class StubEngine(MeetingActionItemsMixin, StubMixin):
            async def _role_turn(self, *args, **kwargs):
                return MagicMock(
                    content=json.dumps(
                        [
                            {
                                "title": "Task A",
                                "description": "Do A",
                                "priority": "high",
                            }
                        ]
                    )
                )

            def _emit_turn(self, turn):
                pass

        engine = StubEngine()
        items = await engine._build_action_items(
            decision="Approved",
            user_message="test",
            critic_notes=[],
            planner_proposals=[],
        )
        assert len(items) == 1
        assert items[0].title == "Task A"
        assert items[0].description == "Do A"
        # Raw items must remain unlanded (PF-1 contract)
        assert items[0].landing_status is None
        assert "task_id" not in items[0].model_dump()

class TestThreeWayTaskType:
    """_create_action_task sets task_type based on playbook_code/tool_name."""

    def _make_engine(self):
        from backend.app.services.orchestration.meeting._action_items import (
            MeetingActionItemsMixin,
        )

        class StubEngine(MeetingActionItemsMixin, StubMixin):
            pass

        engine = StubEngine()
        engine.tasks_store = MagicMock()
        engine.tasks_store.create_task = MagicMock()
        engine._events = [MagicMock(id="evt-001")]
        return engine

    def test_playbook_execution(self):
        engine = self._make_engine()
        item = {"playbook_code": "ig_analyze", "description": "Analyze"}
        task_id = engine._create_action_task(item)
        assert task_id is not None
        call_args = engine.tasks_store.create_task.call_args
        task_obj = call_args[0][0]
        assert task_obj.task_type == "playbook_execution"
        assert task_obj.pack_id == "ig_analyze"

    def test_tool_execution(self):
        engine = self._make_engine()
        item = {"tool_name": "web_scraper", "description": "Scrape"}
        task_id = engine._create_action_task(item)
        assert task_id is not None
        call_args = engine.tasks_store.create_task.call_args
        task_obj = call_args[0][0]
        assert task_obj.task_type == "tool_execution"
        assert task_obj.pack_id == "web_scraper"

    def test_meeting_action_item_default(self):
        engine = self._make_engine()
        item = {"description": "Do something"}
        task_id = engine._create_action_task(item)
        assert task_id is None
        engine.tasks_store.create_task.assert_not_called()

class TestParsePreservesNewFields:
    """_parse_action_items preserves tool_name, input_params, blocked_by."""

    def test_tool_name_and_input_params(self):
        from backend.app.services.orchestration.meeting._action_items import (
            MeetingActionItemsMixin,
        )

        class StubParser(MeetingActionItemsMixin):
            def __init__(self):
                self.session = MagicMock()
                self.session.id = "sess-001"

        parser = StubParser()
        output = json.dumps(
            [
                {
                    "title": "Scrape page",
                    "description": "Scrape the page",
                    "tool_name": "web_scraper",
                    "input_params": {"url": "https://example.com"},
                    "blocked_by": [0],
                },
                {
                    "title": "Other",
                    "description": "No tool",
                },
            ]
        )
        items = parser._parse_action_items(output, "decision")
        assert items[0]["tool_name"] == "web_scraper"
        assert items[0]["input_params"] == {"url": "https://example.com"}
        assert items[0]["blocked_by"] == [0]
        assert items[1]["tool_name"] is None
        assert items[1]["input_params"] is None
        assert items[1]["blocked_by"] is None

class TestPhaseIRNewFields:
    """PhaseIR supports tool_name, input_params, blocked_by."""

    def test_defaults_to_none(self):
        phase = PhaseIR(id="p1", name="Phase 1")
        assert phase.tool_name is None
        assert phase.input_params is None
        assert phase.blocked_by is None

    def test_can_set_fields(self):
        phase = PhaseIR(
            id="p1",
            name="Phase 1",
            tool_name="web_scraper",
            input_params={"url": "https://example.com"},
            blocked_by=[0, 1],
        )
        assert phase.tool_name == "web_scraper"
        assert phase.input_params == {"url": "https://example.com"}
        assert phase.blocked_by == [0, 1]

    def test_serialization_round_trip(self):
        phase = PhaseIR(
            id="p1",
            name="Phase 1",
            tool_name="scraper",
            input_params={"key": "val"},
            blocked_by=[0],
        )
        data = phase.model_dump()
        restored = PhaseIR(**data)
        assert restored.tool_name == "scraper"
        assert restored.input_params == {"key": "val"}
        assert restored.blocked_by == [0]

class TestIRCompilerNewFields:
    """_compile_to_task_ir passes tool_name, input_params, blocked_by to PhaseIR."""

    def test_passes_through(self):
        from backend.app.services.orchestration.meeting._ir_compiler import (
            MeetingIRCompilerMixin,
        )

        class StubCompiler(MeetingIRCompilerMixin):
            def __init__(self):
                self.session = MagicMock()
                self.session.id = "sess-001"
                self.session.workspace_id = "ws-default"
                self.profile_id = "user-001"

        compiler = StubCompiler()
        items = [
            {
                "title": "Scrape",
                "tool_name": "web_scraper",
                "input_params": {"url": "https://x.com"},
                "blocked_by": [1],
            },
            {"title": "Report"},
        ]
        task_ir = compiler._compile_to_task_ir(decision="Go", action_items=items)
        assert task_ir.phases[0].tool_name == "web_scraper"
        assert task_ir.phases[0].input_params == {"url": "https://x.com"}
        assert task_ir.phases[0].blocked_by == [1]
        assert task_ir.phases[1].tool_name is None
