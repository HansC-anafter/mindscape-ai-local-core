"""
Unit tests for DispatchOrchestrator L4 dispatch behavior.

Covers:
- dependency / blocked_by gate
- policy-block skip
- playbook launch vs task projection
- multi-workspace fan-out / aggregate result
- partial failure & terminal status
- PhaseIR cross-workspace fields
- tool-name self-heal (via MeetingDispatchMixin)
- parse/IR compiler preservation of cross-workspace fields
"""

import json
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.app.models.task_ir import PhaseIR, TaskIR, PhaseStatus


@pytest.fixture(autouse=True)
def _mock_data_locality(monkeypatch):
    """Prevent real DataLocalityService from interfering in tests."""
    monkeypatch.setattr(
        "backend.app.services.data_locality_service.get_data_locality_service",
        lambda: None,
    )


class TestPhaseIRCrossWorkspaceFields:
    """Tests for target_workspace_id and asset_refs on PhaseIR."""

    def test_defaults_to_none_and_empty(self):
        phase = PhaseIR(id="p1", name="Phase 1")
        assert phase.target_workspace_id is None
        assert phase.asset_refs == []

    def test_can_set_target_workspace(self):
        phase = PhaseIR(
            id="p1",
            name="Phase 1",
            target_workspace_id="ws-data-001",
            asset_refs=["urn:asset:ig-followers-db", "urn:asset:content-lib"],
        )
        assert phase.target_workspace_id == "ws-data-001"
        assert len(phase.asset_refs) == 2
        assert "urn:asset:ig-followers-db" in phase.asset_refs

    def test_serialization_round_trip(self):
        phase = PhaseIR(
            id="p1",
            name="Phase 1",
            target_workspace_id="ws-data",
            asset_refs=["urn:asset:db"],
        )
        data = phase.model_dump()
        restored = PhaseIR(**data)
        assert restored.target_workspace_id == "ws-data"
        assert restored.asset_refs == ["urn:asset:db"]

    def test_backward_compat_no_new_fields(self):
        """Old serialized data without new fields should still deserialize."""
        data = {"id": "p1", "name": "Phase 1", "status": "pending"}
        phase = PhaseIR(**data)
        assert phase.target_workspace_id is None
        assert phase.asset_refs == []


# ────────────────────────────────────────────────────────────
#  DispatchOrchestrator tests (replaces old StubDispatchEngine)
# ────────────────────────────────────────────────────────────


def _make_orchestrator(**kwargs):
    """Create a DispatchOrchestrator with sensible test defaults."""
    from backend.app.services.orchestration.dispatch_orchestrator import (
        DispatchOrchestrator,
    )

    defaults = {
        "session": MagicMock(
            id="sess-001",
            workspace_id="ws-default",
            metadata={},
        ),
        "profile_id": "user-001",
        "project_id": "proj-001",
    }
    defaults.update(kwargs)
    return DispatchOrchestrator(**defaults)


def _make_task_ir(phases, task_id="task-001"):
    """Build a TaskIR from a list of PhaseIR."""
    return TaskIR(
        task_id=task_id,
        intent_instance_id="intent-001",
        workspace_id="ws-default",
        actor_id="user-001",
        phases=phases,
    )


class TestDispatchOrchestrator:
    """Tests for DispatchOrchestrator.execute() — replaces old _dispatch_phases_to_workspaces tests."""

    @pytest.mark.asyncio
    async def test_single_workspace_all_complete(self):
        """All phases dispatched to same workspace should succeed."""
        orch = _make_orchestrator(
            tasks_store=MagicMock(create_task=MagicMock(return_value="t-1"))
        )
        phases = [
            PhaseIR(id="p1", name="Task A", description="Do A"),
            PhaseIR(id="p2", name="Task B", description="Do B"),
        ]
        task_ir = _make_task_ir(phases)
        action_items = [
            {"title": "Task A", "description": "Do A"},
            {"title": "Task B", "description": "Do B"},
        ]

        result = await orch.execute(task_ir, action_items)
        assert result["total"] == 2
        assert result["succeeded"] == 2
        assert result["failed"] == 0
        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_multi_workspace_fan_out(self):
        """Phases targeting different workspaces should all complete."""
        orch = _make_orchestrator(
            tasks_store=MagicMock(create_task=MagicMock(return_value="t-1"))
        )
        phases = [
            PhaseIR(id="p1", name="Scrape IG", target_workspace_id="ws-data"),
            PhaseIR(id="p2", name="Analyze", target_workspace_id="ws-analytics"),
            PhaseIR(id="p3", name="Report", target_workspace_id="ws-data"),
        ]
        task_ir = _make_task_ir(phases)
        action_items = [
            {
                "title": "Scrape IG",
                "description": "Scrape data",
                "target_workspace_id": "ws-data",
            },
            {
                "title": "Analyze",
                "description": "Analyze",
                "target_workspace_id": "ws-analytics",
            },
            {
                "title": "Report",
                "description": "Generate report",
                "target_workspace_id": "ws-data",
            },
        ]

        result = await orch.execute(task_ir, action_items)
        assert result["total"] == 3
        assert result["succeeded"] == 3
        assert result["status"] == "ok"
        assert "ws-data" in result["workspaces"]
        assert "ws-analytics" in result["workspaces"]

    @pytest.mark.asyncio
    async def test_partial_failure_reported(self):
        """If one phase fails, aggregate should be partial_failure."""
        orch = _make_orchestrator()
        phases = [
            PhaseIR(id="p1", name="Good", description="Works"),
            PhaseIR(id="p2", name="Bad", description="Fails"),
        ]
        task_ir = _make_task_ir(phases)
        action_items = [
            {"title": "Good", "description": "Works"},
            {
                "title": "Bad",
                "description": "Fails",
                "landing_status": "policy_blocked",
            },
        ]

        result = await orch.execute(task_ir, action_items)
        assert result["status"] == "partial_failure"
        assert result["succeeded"] >= 1
        assert result["skipped"] >= 1

    @pytest.mark.asyncio
    async def test_all_failed_status(self):
        """If all phases are pre-blocked, aggregate should be all_failed."""
        orch = _make_orchestrator()
        phases = [
            PhaseIR(id="p1", name="A"),
            PhaseIR(id="p2", name="B"),
        ]
        task_ir = _make_task_ir(phases)
        action_items = [
            {"title": "A", "description": "A", "landing_status": "policy_blocked"},
            {"title": "B", "description": "B", "landing_status": "policy_blocked"},
        ]

        result = await orch.execute(task_ir, action_items)
        assert result["status"] == "all_failed"
        assert result["succeeded"] == 0

    @pytest.mark.asyncio
    async def test_playbook_launch_via_orchestrator(self):
        """Phase with preferred_engine=playbook:X should call execution_launcher.launch."""
        mock_launcher = AsyncMock()
        mock_launcher.launch = AsyncMock(return_value={"execution_id": "exec-1"})
        orch = _make_orchestrator(execution_launcher=mock_launcher)
        phases = [
            PhaseIR(
                id="p1",
                name="Launch PB",
                preferred_engine="playbook:ig_analyze",
                target_workspace_id="ws-data",
            ),
        ]
        task_ir = _make_task_ir(phases)
        action_items = [{"title": "Launch PB", "description": "Analyze IG"}]

        result = await orch.execute(task_ir, action_items)
        assert result["succeeded"] == 1
        mock_launcher.launch.assert_called_once()
        call_kwargs = mock_launcher.launch.call_args
        # Verify launcher was called with correct contract
        assert call_kwargs.kwargs["playbook_code"] == "ig_analyze"
        assert "inputs" in call_kwargs.kwargs
        assert call_kwargs.kwargs["inputs"]["task"] == "Analyze IG"

    @pytest.mark.asyncio
    async def test_task_projection_fallback(self):
        """Phase without playbook_code and without tool_name → task projection."""
        mock_store = MagicMock()
        mock_store.create_task = MagicMock(return_value="task-projected-1")
        orch = _make_orchestrator(tasks_store=mock_store)
        phases = [PhaseIR(id="p1", name="Plan something")]
        task_ir = _make_task_ir(phases)
        action_items = [{"title": "Plan something", "description": "Make a plan"}]

        result = await orch.execute(task_ir, action_items)
        assert result["succeeded"] == 1
        mock_store.create_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_dependency_gate_skips_downstream(self):
        """Phase that depends on a failed phase should be skipped."""
        orch = _make_orchestrator()
        phases = [
            PhaseIR(id="p1", name="Upstream"),
            PhaseIR(id="p2", name="Downstream", depends_on=["p1"]),
        ]
        task_ir = _make_task_ir(phases)
        # Pre-block p1 so it "fails"
        action_items = [
            {
                "title": "Upstream",
                "description": "U",
                "landing_status": "dispatch_error",
            },
            {"title": "Downstream", "description": "D"},
        ]

        result = await orch.execute(task_ir, action_items)
        # p1 should be skipped, p2 should be skipped due to dep gate
        assert result["skipped"] >= 1

    @pytest.mark.asyncio
    async def test_boundary_violated_items_skipped(self):
        """Items pre-marked as boundary_violation must be skipped in orchestrator."""
        orch = _make_orchestrator(
            tasks_store=MagicMock(create_task=MagicMock(return_value="t-1"))
        )
        phases = [
            PhaseIR(id="p1", name="Good", target_workspace_id="ws-data"),
            PhaseIR(id="p2", name="Bad", target_workspace_id="ws-other"),
        ]
        task_ir = _make_task_ir(phases)
        action_items = [
            {"title": "Good", "description": "Passes"},
            {
                "title": "Bad",
                "description": "Violates boundary",
                "landing_status": "boundary_violation",
            },
        ]

        result = await orch.execute(task_ir, action_items)
        assert result["succeeded"] >= 1
        assert result["skipped"] >= 1

    @pytest.mark.asyncio
    async def test_empty_task_ir_returns_empty(self):
        """Empty TaskIR should return status=empty."""
        orch = _make_orchestrator()
        result = await orch.execute(None, [])
        assert result["status"] == "empty"
        assert result["total"] == 0


# ────────────────────────────────────────────────────────────
#  Tool name self-heal (via MeetingDispatchMixin directly)
# ────────────────────────────────────────────────────────────


class TestToolNameSelfHeal:
    """Self-heal priority: attempt one LLM repair before final blocking."""

    @pytest.mark.asyncio
    async def test_repairs_tool_not_allowed(self):
        """Self-heal should repair tool_name to an allowed tool."""
        from backend.app.services.orchestration.meeting._dispatch import (
            MeetingDispatchMixin,
        )

        class StubEngine(MeetingDispatchMixin):
            def __init__(self):
                self.session = MagicMock()
                self.session.id = "sess-001"
                self.session.workspace_id = "ws-default"

            async def _generate_text(self, messages, **kwargs):
                return json.dumps([{"index": 0, "tool_name": "ig.ig_fetch_posts"}])

        engine = StubEngine()
        binding = MagicMock()
        binding.resource_id = "ig.ig_fetch_posts"
        binding_store = MagicMock()
        binding_store.list_bindings_by_workspace.return_value = [binding]

        items = [
            {
                "title": "Sync posts",
                "description": "Sync IG posts",
                "tool_name": "ig_fetch_post",  # typo
                "landing_status": "policy_blocked",
                "policy_reason_code": "TOOL_NOT_ALLOWED",
            }
        ]
        repaired = await engine._attempt_tool_name_self_heal(
            action_items=items, binding_store=binding_store
        )

        assert repaired == 1
        assert items[0]["tool_name"] == "ig.ig_fetch_posts"
        assert items[0]["tool_name_self_healed"] is True

    @pytest.mark.asyncio
    async def test_invalid_repair_keeps_policy_block(self):
        """Invalid repair suggestion should keep the policy block."""
        from backend.app.services.orchestration.meeting._dispatch import (
            MeetingDispatchMixin,
        )

        class StubEngine(MeetingDispatchMixin):
            def __init__(self):
                self.session = MagicMock()
                self.session.id = "sess-001"
                self.session.workspace_id = "ws-default"

            async def _generate_text(self, messages, **kwargs):
                return json.dumps([{"index": 0, "tool_name": "ig.nonexistent_tool"}])

        engine = StubEngine()
        binding = MagicMock()
        binding.resource_id = "ig.ig_fetch_posts"
        binding_store = MagicMock()
        binding_store.list_bindings_by_workspace.return_value = [binding]

        items = [
            {
                "title": "Sync posts",
                "description": "Sync IG posts",
                "tool_name": "ig_fetch_post",
                "landing_status": "policy_blocked",
                "policy_reason_code": "TOOL_NOT_ALLOWED",
            }
        ]
        repaired = await engine._attempt_tool_name_self_heal(
            action_items=items, binding_store=binding_store
        )

        assert repaired == 0
        assert items[0]["landing_status"] == "policy_blocked"
        assert items[0]["policy_reason_code"] == "TOOL_NOT_ALLOWED"


# ────────────────────────────────────────────────────────────
#  Parse / IR compiler preservation (unchanged)
# ────────────────────────────────────────────────────────────


class TestParseActionItemsPreservation:
    """Gap 2: _parse_action_items must preserve target_workspace_id + asset_refs."""

    def test_target_workspace_id_preserved_from_json(self):
        """Executor JSON with target_workspace_id should survive parsing."""
        from backend.app.services.orchestration.meeting._action_items import (
            MeetingActionItemsMixin,
        )

        class StubParser(MeetingActionItemsMixin):
            def __init__(self):
                self.session = MagicMock()
                self.session.id = "sess-001"

        parser = StubParser()
        executor_output = json.dumps(
            [
                {
                    "title": "Scrape followers",
                    "description": "Scrape IG followers",
                    "target_workspace_id": "ws-data-001",
                    "asset_refs": ["urn:asset:ig-followers"],
                    "priority": "high",
                },
                {
                    "title": "Analyze content",
                    "description": "Run content analysis",
                    "priority": "medium",
                },
            ]
        )
        items = parser._parse_action_items(executor_output, "some decision")
        assert len(items) == 2
        assert items[0]["target_workspace_id"] == "ws-data-001"
        assert items[0]["asset_refs"] == ["urn:asset:ig-followers"]
        # Second item has no target_workspace_id
        assert items[1]["target_workspace_id"] is None
        assert items[1]["asset_refs"] == []

    def test_bullet_fallback_has_no_target(self):
        """Bullet-point fallback items should have None target_workspace_id."""
        from backend.app.services.orchestration.meeting._action_items import (
            MeetingActionItemsMixin,
        )

        class StubParser(MeetingActionItemsMixin):
            def __init__(self):
                self.session = MagicMock()
                self.session.id = "sess-001"

        parser = StubParser()
        items = parser._parse_action_items("- Do something", "decision")
        assert len(items) == 1
        # Bullet fallback doesn't have dispatch fields
        assert items[0].get("target_workspace_id") is None


class TestIRCompilerPreservation:
    """Gap 3: _ir_compiler must pass target_workspace_id/asset_refs to PhaseIR."""

    def test_phaseir_gets_target_workspace(self):
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
        action_items = [
            {
                "title": "Fetch data",
                "description": "Fetch IG data",
                "target_workspace_id": "ws-data",
                "asset_refs": ["urn:asset:ig-db"],
            },
            {
                "title": "Report",
                "description": "Generate report",
            },
        ]
        task_ir = compiler._compile_to_task_ir(
            decision="Approved",
            action_items=action_items,
        )
        assert len(task_ir.phases) == 2
        assert task_ir.phases[0].target_workspace_id == "ws-data"
        assert task_ir.phases[0].asset_refs == ["urn:asset:ig-db"]
        assert task_ir.phases[1].target_workspace_id is None
        assert task_ir.phases[1].asset_refs == []
