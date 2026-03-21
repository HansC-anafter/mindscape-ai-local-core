"""
Tests for Meeting Engine v6 changes.

Covers: PF-1 (dual-write removal), 5A (installed playbooks, task_type),
5B (field pass-through, three-way dispatch, blocked_by validation),
5E (policy gate).
"""

import json
import importlib
import os
import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

_repo_root = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
)
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)
_backend_root = os.path.join(_repo_root, "backend")
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)

from backend.app.models.task_ir import PhaseIR


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class StubMixin:
    """Minimal stubs for mixin testing."""

    def __init__(self):
        self.session = MagicMock()
        self.session.id = "sess-001"
        self.session.workspace_id = "ws-default"
        self.session.round_count = 1
        self.profile_id = "user-001"
        self.project_id = "proj-001"
        self.execution_launcher = None
        self.tasks_store = None
        self._events = []

    def _emit_event(self, event_type, payload=None):
        self._events.append({"type": event_type, "payload": payload})

    async def _land_action_item(self, item):
        item["landing_status"] = "task_created"
        item["task_id"] = f"task-{item.get('title', 'x')}"
        return item


# ---------------------------------------------------------------------------
# PF-1: _build_action_items returns raw items (no landing)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# 5A-2 / 5B-2: Three-way task_type dispatch
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# 5B-1: New fields preserved in parser
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# 5B-1: PhaseIR new fields
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# 5B-1: IR Compiler passes new fields
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# 5E: Policy Gate
# ---------------------------------------------------------------------------


class TestPolicyGate:
    """dispatch_policy_gate blocks unknown playbooks."""

    def test_blocks_unknown_playbook(self):
        from backend.app.services.orchestration.meeting.dispatch_policy_gate import (
            check_dispatch_policy,
        )

        items = [
            {"title": "A", "playbook_code": "ig_analyze"},
            {"title": "B", "playbook_code": "unknown_pb"},
        ]
        check_dispatch_policy(
            items,
            workspace_id="ws-1",
            available_playbooks_cache="- ig_analyze: IG Analyzer\n- ig_report: IG Report",
        )
        assert items[0].get("landing_status") is None  # known → passes
        assert items[1]["landing_status"] == "policy_blocked"
        assert items[1]["policy_reason_code"] == "UNKNOWN_PLAYBOOK"

    def test_no_playbooks_cache_passes_all(self):
        from backend.app.services.orchestration.meeting.dispatch_policy_gate import (
            check_dispatch_policy,
        )

        items = [{"title": "A", "playbook_code": "any_code"}]
        check_dispatch_policy(items, workspace_id="ws-1", available_playbooks_cache="")
        # No cache → no enforcement → item passes
        assert items[0].get("landing_status") is None

    def test_reason_code_present(self):
        from backend.app.services.orchestration.meeting.dispatch_policy_gate import (
            check_dispatch_policy,
        )

        items = [{"title": "X", "playbook_code": "nonexistent"}]
        check_dispatch_policy(
            items, workspace_id="ws-1", available_playbooks_cache="- valid: Valid PB"
        )
        assert "policy_reason_code" in items[0]
        assert items[0]["policy_reason_code"] == "UNKNOWN_PLAYBOOK"


# ---------------------------------------------------------------------------
# 5E: Policy gate in single-path dispatch
# ---------------------------------------------------------------------------


class TestPolicyGateSinglePath:
    """Policy-blocked items are skipped in DispatchOrchestrator."""

    @pytest.mark.asyncio
    async def test_single_path_skips_blocked(self):
        from backend.app.services.orchestration.dispatch_orchestrator import (
            DispatchOrchestrator,
        )
        from backend.app.models.task_ir import TaskIR, PhaseIR

        orch = DispatchOrchestrator(
            session=MagicMock(id="sess-001", workspace_id="ws-default", metadata={}),
            profile_id="user-001",
            tasks_store=MagicMock(create_task=MagicMock(return_value="t-1")),
        )
        phases = [
            PhaseIR(id="p1", name="Good"),
            PhaseIR(id="p2", name="Blocked"),
        ]
        task_ir = TaskIR(
            task_id="t-001",
            intent_instance_id="i-001",
            workspace_id="ws-default",
            actor_id="user-001",
            phases=phases,
        )
        action_items = [
            {"title": "Good", "description": "ok"},
            {
                "title": "Blocked",
                "description": "blocked",
                "landing_status": "policy_blocked",
            },
        ]
        result = await orch.execute(task_ir, action_items)
        assert result["succeeded"] >= 1
        assert result["skipped"] >= 1


# ---------------------------------------------------------------------------
# 5B-4: blocked_by validation
# ---------------------------------------------------------------------------


class TestBlockedByValidation:
    """blocked_by cycle and missing reference detection."""

    def _make_engine(self):
        from backend.app.services.orchestration.meeting.engine import MeetingEngine

        class Eng(StubMixin):
            pass

        Eng._resolve_blocked_by_order = MeetingEngine._resolve_blocked_by_order
        return Eng()

    def test_cycle_detection(self):
        engine = self._make_engine()
        items = [
            {"title": "A", "description": "A", "blocked_by": [1]},
            {"title": "B", "description": "B", "blocked_by": [0]},
        ]
        result = engine._resolve_blocked_by_order(items)
        assert items[0]["landing_status"] == "dispatch_error"
        assert "cycle" in items[0]["landing_error"]
        assert items[1]["landing_status"] == "dispatch_error"

    def test_missing_reference(self):
        engine = self._make_engine()
        items = [
            {"title": "A", "description": "A", "blocked_by": [5]},
        ]
        result = engine._resolve_blocked_by_order(items)
        assert items[0]["landing_status"] == "dispatch_error"
        assert "missing dependency" in items[0]["landing_error"]

    def test_valid_deps_pass(self):
        engine = self._make_engine()
        items = [
            {"title": "A", "description": "A"},
            {"title": "B", "description": "B", "blocked_by": [0]},
        ]
        result = engine._resolve_blocked_by_order(items)
        assert items[0].get("landing_status") is None
        assert items[1].get("landing_status") is None
        # Topological order: A before B
        assert result[0]["title"] == "A"
        assert result[1]["title"] == "B"

    def test_no_blocked_by_noop(self):
        engine = self._make_engine()
        items = [
            {"title": "A", "description": "A"},
            {"title": "B", "description": "B"},
        ]
        result = engine._resolve_blocked_by_order(items)
        assert items[0].get("landing_status") is None
        assert items[1].get("landing_status") is None
        assert len(result) == 2


# ---------------------------------------------------------------------------
# [Medium] single-path 用實際 workspace key
# ---------------------------------------------------------------------------


class TestSinglePathWorkspaceKey:
    """DispatchOrchestrator records correct target workspace."""

    @pytest.mark.asyncio
    async def test_non_default_target_workspace_key(self):
        from backend.app.services.orchestration.dispatch_orchestrator import (
            DispatchOrchestrator,
        )
        from backend.app.models.task_ir import TaskIR, PhaseIR

        orch = DispatchOrchestrator(
            session=MagicMock(id="sess-001", workspace_id="ws-default", metadata={}),
            profile_id="user-001",
            tasks_store=MagicMock(create_task=MagicMock(return_value="t-1")),
        )
        phases = [
            PhaseIR(id="p1", name="Task", target_workspace_id="ws-other"),
        ]
        task_ir = TaskIR(
            task_id="t-001",
            intent_instance_id="i-001",
            workspace_id="ws-default",
            actor_id="user-001",
            phases=phases,
        )
        action_items = [
            {"title": "Task", "description": "ok", "target_workspace_id": "ws-other"},
        ]
        result = await orch.execute(task_ir, action_items)
        assert result["succeeded"] == 1
        assert "ws-other" in result["workspaces"]


# ---------------------------------------------------------------------------
# [High] multi all-policy-blocked aggregate_status
# ---------------------------------------------------------------------------


class TestMultiAllPolicyBlocked:
    """All items policy_blocked → DispatchOrchestrator reports all_failed."""

    @pytest.mark.asyncio
    async def test_all_policy_blocked_gives_all_failed(self):
        from backend.app.services.orchestration.dispatch_orchestrator import (
            DispatchOrchestrator,
        )
        from backend.app.models.task_ir import TaskIR, PhaseIR

        orch = DispatchOrchestrator(
            session=MagicMock(id="sess-001", workspace_id="ws-default", metadata={}),
            profile_id="user-001",
        )
        phases = [
            PhaseIR(id="p1", name="A", target_workspace_id="ws-a"),
            PhaseIR(id="p2", name="B", target_workspace_id="ws-b"),
        ]
        task_ir = TaskIR(
            task_id="t-001",
            intent_instance_id="i-001",
            workspace_id="ws-default",
            actor_id="user-001",
            phases=phases,
        )
        action_items = [
            {
                "title": "A",
                "description": "a",
                "landing_status": "policy_blocked",
            },
            {
                "title": "B",
                "description": "b",
                "landing_status": "policy_blocked",
            },
        ]
        result = await orch.execute(task_ir, action_items)
        assert result["total"] == 2
        assert result["succeeded"] == 0
        assert result["status"] == "all_failed"


# ---------------------------------------------------------------------------
# [High] tool_execution input_params 寫入 execution_context
# ---------------------------------------------------------------------------


class TestToolExecutionInputParams:
    """_create_action_task writes input_params + tool_name to execution_context."""

    def test_input_params_in_execution_context(self):
        from backend.app.services.orchestration.meeting._action_items import (
            MeetingActionItemsMixin,
        )

        class StubEngine(MeetingActionItemsMixin, StubMixin):
            pass

        engine = StubEngine()
        engine.tasks_store = MagicMock()
        engine.tasks_store.create_task = MagicMock()
        engine._events = [MagicMock(id="evt-001")]

        item = {
            "tool_name": "web_scraper",
            "input_params": {"url": "https://example.com", "depth": 2},
            "description": "Scrape it",
        }
        task_id = engine._create_action_task(item)
        assert task_id is not None

        task_obj = engine.tasks_store.create_task.call_args[0][0]
        assert task_obj.task_type == "tool_execution"
        assert task_obj.execution_context["tool_name"] == "web_scraper"
        assert task_obj.execution_context["inputs"] == {
            "url": "https://example.com",
            "depth": 2,
        }
        assert task_obj.params["tool_name"] == "web_scraper"
        assert task_obj.params["input_params"] == {
            "url": "https://example.com",
            "depth": 2,
        }


# ---------------------------------------------------------------------------
# 5E: Tool allowlist enforcement
# ---------------------------------------------------------------------------


class TestToolAllowlist:
    """Tool allowlist blocks tools not in workspace bindings."""

    def test_tool_not_in_allowlist(self):
        from backend.app.services.orchestration.meeting.dispatch_policy_gate import (
            check_dispatch_policy,
        )

        binding = MagicMock()
        binding.resource_id = "allowed_tool"
        binding_store = MagicMock()
        binding_store.list_bindings_by_workspace.return_value = [binding]

        items = [
            {"title": "A", "tool_name": "allowed_tool", "description": "ok"},
            {"title": "B", "tool_name": "blocked_tool", "description": "bad"},
        ]
        check_dispatch_policy(
            items,
            workspace_id="ws-1",
            binding_store=binding_store,
        )
        assert items[0].get("landing_status") is None  # allowed
        assert items[1]["landing_status"] == "policy_blocked"
        assert items[1]["policy_reason_code"] == "TOOL_NOT_ALLOWED"

    def test_tool_in_allowlist_passes(self):
        from backend.app.services.orchestration.meeting.dispatch_policy_gate import (
            check_dispatch_policy,
        )

        binding = MagicMock()
        binding.resource_id = "my_tool"
        binding_store = MagicMock()
        binding_store.list_bindings_by_workspace.return_value = [binding]

        items = [{"title": "OK", "tool_name": "my_tool", "description": "fine"}]
        check_dispatch_policy(items, workspace_id="ws-1", binding_store=binding_store)
        assert items[0].get("landing_status") is None

    def test_no_binding_store_passes_all(self):
        from backend.app.services.orchestration.meeting.dispatch_policy_gate import (
            check_dispatch_policy,
        )

        items = [{"title": "Any", "tool_name": "any_tool", "description": "ok"}]
        check_dispatch_policy(items, workspace_id="ws-1", binding_store=None)
        assert items[0].get("landing_status") is None  # no enforcement

    def test_per_item_target_workspace_allowlist(self):
        """5E: allowlist uses item's target_workspace_id, not session workspace."""
        from backend.app.services.orchestration.meeting.dispatch_policy_gate import (
            check_dispatch_policy,
        )

        # ws-target has tool_a allowed; session ws-session has tool_b allowed
        binding_a = MagicMock()
        binding_a.resource_id = "tool_a"
        binding_b = MagicMock()
        binding_b.resource_id = "tool_b"
        binding_store = MagicMock()

        def _list(ws_id, resource_type=None):
            if ws_id == "ws-target":
                return [binding_a]
            if ws_id == "ws-session":
                return [binding_b]
            return []

        binding_store.list_bindings_by_workspace.side_effect = _list

        items = [
            {"title": "A", "tool_name": "tool_a", "target_workspace_id": "ws-target"},
            {"title": "B", "tool_name": "tool_b"},  # falls back to session ws
        ]
        check_dispatch_policy(
            items, workspace_id="ws-session", binding_store=binding_store
        )
        # tool_a is allowed on ws-target → pass
        assert items[0].get("landing_status") is None
        # tool_b is allowed on ws-session (fallback) → pass
        assert items[1].get("landing_status") is None

    def test_suffix_tool_name_is_canonicalized_when_unique(self):
        """Bare tool name should be normalized to canonical allowlist ID."""
        from backend.app.services.orchestration.meeting.dispatch_policy_gate import (
            check_dispatch_policy,
        )

        binding = MagicMock()
        binding.resource_id = "ig.ig_fetch_posts"
        binding_store = MagicMock()
        binding_store.list_bindings_by_workspace.return_value = [binding]

        items = [{"title": "Sync", "tool_name": "ig_fetch_posts"}]
        check_dispatch_policy(items, workspace_id="ws-1", binding_store=binding_store)

        assert items[0].get("landing_status") is None
        assert items[0]["tool_name"] == "ig.ig_fetch_posts"
        assert items[0]["tool_name_original"] == "ig_fetch_posts"
        assert items[0]["tool_name_normalized"] is True

    def test_suffix_tool_name_ambiguous_still_blocked(self):
        """Ambiguous bare name should stay blocked for later repair phase."""
        from backend.app.services.orchestration.meeting.dispatch_policy_gate import (
            check_dispatch_policy,
        )

        binding_a = MagicMock()
        binding_a.resource_id = "ig.ig_fetch_posts"
        binding_b = MagicMock()
        binding_b.resource_id = "legacy.ig_fetch_posts"
        binding_store = MagicMock()
        binding_store.list_bindings_by_workspace.return_value = [binding_a, binding_b]

        items = [{"title": "Sync", "tool_name": "ig_fetch_posts"}]
        check_dispatch_policy(items, workspace_id="ws-1", binding_store=binding_store)

        assert items[0]["landing_status"] == "policy_blocked"
        assert items[0]["policy_reason_code"] == "TOOL_NOT_ALLOWED"


class TestVisibilityModel:
    """Tests for WorkspaceVisibility integration in models."""

    def test_workspace_defaults_to_private(self):
        """Workspace model defaults to PRIVATE when visibility not specified."""
        from backend.app.models.workspace import Workspace, WorkspaceVisibility

        ws = Workspace(
            id="ws-test",
            title="Test",
            owner_user_id="u1",
        )
        assert ws.visibility == WorkspaceVisibility.PRIVATE


# ---------------------------------------------------------------------------
# 5E / Block F: real-path correctness feedback wiring
# ---------------------------------------------------------------------------


class TestCorrectnessFeedbackRealPath:
    """MeetingEngine stage should apply session correctness feedback."""

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
