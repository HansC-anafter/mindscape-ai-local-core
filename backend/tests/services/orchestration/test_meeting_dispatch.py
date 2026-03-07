"""
Unit tests for Phase 2: PhaseIR cross-workspace fields and
MeetingEngine._dispatch_phases_to_workspaces fan-in aggregation.
"""

import json
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.app.models.task_ir import PhaseIR


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


class StubDispatchEngine:
    """Minimal stub for testing _dispatch_phases_to_workspaces."""

    def __init__(self):
        self.session = MagicMock()
        self.session.id = "sess-001"
        self.session.workspace_id = "ws-default"
        self.profile_id = "user-001"
        self.project_id = "proj-001"
        self.execution_launcher = None
        self.tasks_store = None
        self._events = []
        self._available_playbooks_cache = ""
        self._repair_output = "[]"

    def _emit_event(self, event_type, payload=None):
        self._events.append({"type": event_type, "payload": payload})

    async def _land_action_item(self, item):
        """Stub that marks items as task_created."""
        item["landing_status"] = "task_created"
        item["task_id"] = f"task-{item.get('title', 'x')}"
        return item

    async def _generate_text(self, messages, **kwargs):
        return self._repair_output


# Attach the actual methods to the stub
from backend.app.services.orchestration.meeting.engine import MeetingEngine

StubDispatchEngine._dispatch_phases_to_workspaces = (
    MeetingEngine._dispatch_phases_to_workspaces
)
StubDispatchEngine._resolve_blocked_by_order = MeetingEngine._resolve_blocked_by_order
StubDispatchEngine._attempt_tool_name_self_heal = (
    MeetingEngine._attempt_tool_name_self_heal
)


class TestDispatchPhasesToWorkspaces:
    """Tests for _dispatch_phases_to_workspaces fan-in."""

    @pytest.mark.asyncio
    async def test_single_workspace_serial_path(self):
        engine = StubDispatchEngine()
        items = [
            {"title": "Task A", "description": "Do A"},
            {"title": "Task B", "description": "Do B"},
        ]
        result = await engine._dispatch_phases_to_workspaces(items)
        assert result["dispatch_mode"] == "single"
        assert result["total"] == 2
        assert result["succeeded"] == 2
        assert result["failed"] == 0
        assert result["aggregate_status"] == "ok"

    @pytest.mark.asyncio
    async def test_multi_workspace_fan_out_fan_in(self):
        engine = StubDispatchEngine()
        items = [
            {
                "title": "Scrape IG",
                "description": "Scrape data",
                "target_workspace_id": "ws-data",
            },
            {
                "title": "Analyze content",
                "description": "Analyze",
                "target_workspace_id": "ws-analytics",
            },
            {
                "title": "Report",
                "description": "Generate report",
                "target_workspace_id": "ws-data",
            },
        ]
        result = await engine._dispatch_phases_to_workspaces(items)
        assert result["dispatch_mode"] == "multi"
        assert result["total"] == 3
        assert result["succeeded"] == 3
        assert result["aggregate_status"] == "ok"
        assert "ws-data" in result["workspace_results"]
        assert "ws-analytics" in result["workspace_results"]
        assert len(result["workspace_results"]["ws-data"]) == 2
        assert len(result["workspace_results"]["ws-analytics"]) == 1
        # Should have emitted an audit event
        assert len(engine._events) == 1
        assert engine._events[0]["payload"]["cross_workspace_dispatch"] is True

    @pytest.mark.asyncio
    async def test_partial_failure_reported(self):
        engine = StubDispatchEngine()

        call_count = 0

        async def _land_with_failure(item):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                item["landing_status"] = "launch_error"
                item["landing_error"] = "simulated failure"
            else:
                item["landing_status"] = "task_created"
                item["task_id"] = f"task-{call_count}"
            return item

        engine._land_action_item = _land_with_failure

        items = [
            {"title": "A", "description": "A", "target_workspace_id": "ws-1"},
            {"title": "B", "description": "B", "target_workspace_id": "ws-2"},
            {"title": "C", "description": "C", "target_workspace_id": "ws-1"},
        ]
        result = await engine._dispatch_phases_to_workspaces(items)
        assert result["dispatch_mode"] == "multi"
        assert result["aggregate_status"] == "partial_failure"
        assert result["succeeded"] == 2
        assert result["failed"] == 1

    @pytest.mark.asyncio
    async def test_fallback_when_no_target_workspace(self):
        engine = StubDispatchEngine()
        items = [
            {"title": "A", "description": "A"},
            {"title": "B", "description": "B"},
        ]
        result = await engine._dispatch_phases_to_workspaces(items)
        assert result["dispatch_mode"] == "single"
        # All items should have been assigned to default workspace
        for item in items:
            assert item["target_workspace_id"] == "ws-default"

    @pytest.mark.asyncio
    async def test_all_failed_status(self):
        engine = StubDispatchEngine()

        async def _always_fail(item):
            item["landing_status"] = "launch_error"
            return item

        engine._land_action_item = _always_fail

        items = [
            {"title": "A", "description": "A", "target_workspace_id": "ws-1"},
            {"title": "B", "description": "B", "target_workspace_id": "ws-2"},
        ]
        result = await engine._dispatch_phases_to_workspaces(items)
        assert result["aggregate_status"] == "all_failed"
        assert result["succeeded"] == 0
        assert result["failed"] == 2


class TestToolNameSelfHeal:
    """Self-heal priority: attempt one LLM repair before final blocking."""

    @pytest.mark.asyncio
    async def test_repairs_tool_not_allowed_then_dispatches(self):
        engine = StubDispatchEngine()
        engine._repair_output = json.dumps(
            [{"index": 0, "tool_name": "ig.ig_fetch_posts"}]
        )

        binding = MagicMock()
        binding.resource_id = "ig.ig_fetch_posts"
        binding_store = MagicMock()
        binding_store.list_bindings_by_workspace.return_value = [binding]

        with patch(
            "backend.app.services.stores.workspace_resource_binding_store.WorkspaceResourceBindingStore",
            return_value=binding_store,
        ):
            items = [
                {
                    "title": "Sync posts",
                    "description": "Sync IG posts",
                    "tool_name": "ig_fetch_post",  # typo: deterministic normalize fails
                }
            ]
            result = await engine._dispatch_phases_to_workspaces(items)

        assert result["succeeded"] == 1
        assert result["failed"] == 0
        assert items[0]["tool_name"] == "ig.ig_fetch_posts"
        assert items[0]["tool_name_self_healed"] is True
        assert items[0]["landing_status"] == "task_created"

    @pytest.mark.asyncio
    async def test_invalid_repair_keeps_policy_block(self):
        engine = StubDispatchEngine()
        engine._repair_output = json.dumps(
            [{"index": 0, "tool_name": "ig.nonexistent_tool"}]
        )

        binding = MagicMock()
        binding.resource_id = "ig.ig_fetch_posts"
        binding_store = MagicMock()
        binding_store.list_bindings_by_workspace.return_value = [binding]

        with patch(
            "backend.app.services.stores.workspace_resource_binding_store.WorkspaceResourceBindingStore",
            return_value=binding_store,
        ):
            items = [
                {
                    "title": "Sync posts",
                    "description": "Sync IG posts",
                    "tool_name": "ig_fetch_post",
                }
            ]
            result = await engine._dispatch_phases_to_workspaces(items)

        assert result["succeeded"] == 0
        assert result["failed"] == 1
        assert items[0]["landing_status"] == "policy_blocked"
        assert items[0]["policy_reason_code"] == "TOOL_NOT_ALLOWED"


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


class TestBoundaryViolationSkip:
    """Engine-level: violated items must not reach _land_action_item."""

    @pytest.mark.asyncio
    async def test_boundary_violated_items_skipped(self):
        """Items that fail boundary check must not be dispatched."""
        engine = StubDispatchEngine()
        landed_titles = []

        async def _tracking_land(item):
            landed_titles.append(item["title"])
            item["landing_status"] = "task_created"
            return item

        engine._land_action_item = _tracking_land

        items = [
            {
                "title": "Good",
                "description": "Passes",
                "target_workspace_id": "ws-data",
                "asset_refs": ["urn:asset:ig-db"],
            },
            {
                "title": "Bad",
                "description": "Violates boundary",
                "target_workspace_id": "ws-other",
                "asset_refs": ["urn:asset:ig-db"],
            },
        ]

        # Pre-mark the bad item as boundary_violation (simulates what the
        # real code does after check_dispatch_boundary finds a violation)
        items[1]["landing_status"] = "boundary_violation"
        items[1]["landing_error"] = "Asset not bound"

        result = await engine._dispatch_phases_to_workspaces(items)

        # "Bad" must never have reached _land_action_item
        assert "Bad" not in landed_titles
        assert "Good" in landed_titles
        assert result["failed"] >= 1  # boundary_violation counted as failed

    @pytest.mark.asyncio
    async def test_all_boundary_violated_gives_all_failed(self):
        """If all items are boundary_violation, aggregate = all_failed."""
        engine = StubDispatchEngine()

        items = [
            {
                "title": "A",
                "description": "A",
                "target_workspace_id": "ws-1",
                "landing_status": "boundary_violation",
                "landing_error": "not bound",
            },
            {
                "title": "B",
                "description": "B",
                "target_workspace_id": "ws-2",
                "landing_status": "boundary_violation",
                "landing_error": "not bound",
            },
        ]
        result = await engine._dispatch_phases_to_workspaces(items)
        assert result["failed"] == 2
        assert result["succeeded"] == 0
        assert result["aggregate_status"] == "all_failed"
