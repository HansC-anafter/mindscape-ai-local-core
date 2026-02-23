"""
Unit tests for MeetingIRCompilerMixin.

Tests the compilation of meeting output (decision + action_items)
into structured TaskIR, with and without HandoffIn governance context.
"""

import pytest
from unittest.mock import MagicMock
from datetime import datetime, timezone

from backend.app.services.orchestration.meeting._ir_compiler import (
    MeetingIRCompilerMixin,
)
from backend.app.models.task_ir import (
    TaskIR,
    PhaseIR,
    PhaseStatus,
    TaskStatus,
    GovernanceContext,
)
from backend.app.models.handoff import (
    HandoffIn,
    DeliverableSpec,
    HandoffConstraints,
)


class FakeMeetingEngine(MeetingIRCompilerMixin):
    """Minimal stub that mimics MeetingEngine attributes used by compiler."""

    def __init__(
        self, session_id="sess-001", workspace_id="ws-001", profile_id="user-001"
    ):
        self.session = MagicMock()
        self.session.id = session_id
        self.session.workspace_id = workspace_id
        self.profile_id = profile_id


class TestCompileBasic:
    def test_empty_action_items_produces_single_phase(self):
        engine = FakeMeetingEngine()
        ir = engine._compile_to_task_ir(
            decision="Do nothing for now",
            action_items=[],
        )
        assert isinstance(ir, TaskIR)
        assert len(ir.phases) == 1
        assert ir.phases[0].name == "Execute Decision"
        assert ir.status == TaskStatus.PENDING

    def test_action_items_to_phases(self):
        engine = FakeMeetingEngine()
        items = [
            {"title": "Design mockup", "description": "Create wireframes"},
            {"title": "Build frontend", "description": "Implement React components"},
            {"title": "Deploy", "description": "Ship to production"},
        ]
        ir = engine._compile_to_task_ir(decision="Build the page", action_items=items)

        assert len(ir.phases) == 3
        assert ir.phases[0].name == "Design mockup"
        assert ir.phases[0].description == "Create wireframes"
        assert ir.phases[1].depends_on == ["action_0"]
        assert ir.phases[2].depends_on == ["action_1"]
        assert ir.phases[0].depends_on is None

    def test_action_items_with_engine_preference(self):
        engine = FakeMeetingEngine()
        items = [
            {"title": "Run playbook", "engine": "playbook:landing_page"},
        ]
        ir = engine._compile_to_task_ir(decision="Execute", action_items=items)
        assert ir.phases[0].preferred_engine == "playbook:landing_page"

    def test_action_items_with_playbook_code_fallback(self):
        """playbook_code from _action_items.py maps to preferred_engine with prefix."""
        engine = FakeMeetingEngine()
        items = [
            {"title": "Generate report", "playbook_code": "yoga_course_outline"},
        ]
        ir = engine._compile_to_task_ir(decision="Go", action_items=items)
        assert ir.phases[0].preferred_engine == "playbook:yoga_course_outline"

    def test_action_items_engine_takes_priority_over_playbook_code(self):
        """When both engine and playbook_code are present, engine wins."""
        engine = FakeMeetingEngine()
        items = [
            {"title": "Run", "engine": "skill:research", "playbook_code": "fallback"},
        ]
        ir = engine._compile_to_task_ir(decision="Go", action_items=items)
        assert ir.phases[0].preferred_engine == "skill:research"

    def test_workspace_from_session(self):
        engine = FakeMeetingEngine(workspace_id="ws-test")
        ir = engine._compile_to_task_ir(decision="Test", action_items=[])
        assert ir.workspace_id == "ws-test"

    def test_actor_from_profile(self):
        engine = FakeMeetingEngine(profile_id="prof-123")
        ir = engine._compile_to_task_ir(decision="Test", action_items=[])
        assert ir.actor_id == "prof-123"

    def test_task_id_format(self):
        engine = FakeMeetingEngine()
        ir = engine._compile_to_task_ir(decision="Test", action_items=[])
        assert ir.task_id.startswith("task_")
        assert len(ir.task_id) == 21  # "task_" + 16 hex chars


class TestCompileWithHandoffIn:
    def _make_handoff(self, **kwargs):
        defaults = {
            "handoff_id": "h-001",
            "workspace_id": "ws-from-handoff",
            "intent_summary": "Build landing page",
            "goals": ["Deploy page", "Include hero banner"],
        }
        defaults.update(kwargs)
        return HandoffIn(**defaults)

    def test_governance_populated_from_handoff(self):
        engine = FakeMeetingEngine()
        handoff = self._make_handoff(
            acceptance_tests=["Page loads under 2s"],
            risk_notes=["CDN may be slow"],
        )
        ir = engine._compile_to_task_ir(
            decision="Build it",
            action_items=[{"title": "Build"}],
            handoff_in=handoff,
        )
        gov = ir.metadata.get_governance()
        assert gov is not None
        assert gov.goals == ["Deploy page", "Include hero banner"]
        assert gov.acceptance_tests == ["Page loads under 2s"]
        assert gov.risk_profile == {"risk_notes": ["CDN may be slow"]}
        assert gov.handoff_id == "h-001"

    def test_governance_constraints_from_handoff(self):
        engine = FakeMeetingEngine()
        handoff = self._make_handoff(
            constraints=HandoffConstraints(
                action_space="WRITE_WS",
                max_duration_seconds=7200,
            ),
        )
        ir = engine._compile_to_task_ir(
            decision="Go",
            action_items=[],
            handoff_in=handoff,
        )
        gov = ir.metadata.get_governance()
        assert gov.constraints is not None
        assert gov.constraints["action_space"] == "WRITE_WS"

    def test_governance_deliverables_from_handoff(self):
        engine = FakeMeetingEngine()
        handoff = self._make_handoff(
            deliverables=[
                DeliverableSpec(name="report", mime_type="application/pdf"),
                DeliverableSpec(name="summary", mime_type="text/markdown"),
            ],
        )
        ir = engine._compile_to_task_ir(
            decision="Generate",
            action_items=[],
            handoff_in=handoff,
        )
        gov = ir.metadata.get_governance()
        assert gov.deliverables is not None
        assert len(gov.deliverables) == 2
        assert gov.deliverables[0]["name"] == "report"

    def test_workspace_from_handoff_overrides_session(self):
        engine = FakeMeetingEngine(workspace_id="ws-session")
        handoff = self._make_handoff(workspace_id="ws-handoff")
        ir = engine._compile_to_task_ir(
            decision="Test",
            action_items=[],
            handoff_in=handoff,
        )
        assert ir.workspace_id == "ws-handoff"

    def test_no_handoff_still_works(self):
        """Pure meeting scenario without HandoffIn."""
        engine = FakeMeetingEngine()
        ir = engine._compile_to_task_ir(
            decision="Approve design",
            action_items=[{"title": "Apply feedback"}],
            handoff_in=None,
        )
        assert ir.metadata.get_governance() is None
        assert len(ir.phases) == 1

    def test_governance_schema_version_set(self):
        engine = FakeMeetingEngine()
        handoff = self._make_handoff()
        ir = engine._compile_to_task_ir(
            decision="Go",
            action_items=[],
            handoff_in=handoff,
        )
        gov = ir.metadata.get_governance()
        assert gov.schema_version == "0.1"
