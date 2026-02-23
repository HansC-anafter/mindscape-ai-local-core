"""
Unit tests for handoff models and governance context.

Covers HandoffIn, Commitment, DeliverableSpec, HandoffConstraints,
GovernanceContext, and ExecutionMetadata setter/getter methods.
"""

import pytest
from datetime import datetime, timezone

from backend.app.models.handoff import (
    HandoffIn,
    Commitment,
    DeliverableSpec,
    HandoffConstraints,
)
from backend.app.models.task_ir import (
    TaskIR,
    PhaseIR,
    PhaseStatus,
    TaskStatus,
    ExecutionMetadata,
    ExecutionEngine,
    GovernanceContext,
    GOVERNANCE_SCHEMA_VERSION,
)


class TestDeliverableSpec:
    def test_basic_construction(self):
        spec = DeliverableSpec(name="report", mime_type="text/markdown")
        assert spec.name == "report"
        assert spec.mime_type == "text/markdown"
        assert spec.description is None

    def test_with_description(self):
        spec = DeliverableSpec(
            name="image", mime_type="image/png", description="Hero banner"
        )
        assert spec.description == "Hero banner"


class TestHandoffConstraints:
    def test_all_none_by_default(self):
        c = HandoffConstraints()
        assert c.style_refs is None
        assert c.ip_policy is None
        assert c.action_space is None
        assert c.max_duration_seconds is None

    def test_full_construction(self):
        c = HandoffConstraints(
            style_refs=["brand_guide_v2"],
            ip_policy="no_external_api",
            action_space="WRITE_WS",
            max_duration_seconds=3600,
        )
        assert c.action_space == "WRITE_WS"
        assert c.max_duration_seconds == 3600


class TestHandoffIn:
    def test_minimal_construction(self):
        h = HandoffIn(
            handoff_id="h-001",
            workspace_id="ws-001",
            intent_summary="Build landing page",
            goals=["Deploy page"],
        )
        assert h.handoff_id == "h-001"
        assert h.goals == ["Deploy page"]
        assert h.non_goals is None
        assert h.constraints is None
        assert h.created_at is not None

    def test_full_construction(self):
        h = HandoffIn(
            handoff_id="h-002",
            workspace_id="ws-001",
            intent_summary="Generate report",
            goals=["Produce PDF", "Include charts"],
            non_goals=["No video"],
            deliverables=[
                DeliverableSpec(name="report", mime_type="application/pdf"),
            ],
            constraints=HandoffConstraints(action_space="READ_ONLY"),
            acceptance_tests=["PDF is valid", "Charts are present"],
            risk_notes=["Large dataset may cause timeout"],
            assets=["data_snapshot_v3"],
        )
        assert len(h.deliverables) == 1
        assert h.constraints.action_space == "READ_ONLY"
        assert len(h.acceptance_tests) == 2

    def test_serialization_roundtrip(self):
        h = HandoffIn(
            handoff_id="h-003",
            workspace_id="ws-001",
            intent_summary="Test roundtrip",
            goals=["Goal A"],
        )
        d = h.model_dump()
        h2 = HandoffIn(**d)
        assert h2.handoff_id == h.handoff_id
        assert h2.goals == h.goals


class TestCommitment:
    def test_accepted(self):
        c = Commitment(
            commitment_id="c-001",
            handoff_id="h-001",
            accepted=True,
            scope_summary="Will build landing page with 3 sections",
            estimated_phases=3,
            task_ir_id="task_abc123",
        )
        assert c.accepted is True
        assert c.task_ir_id == "task_abc123"

    def test_rejected(self):
        c = Commitment(
            commitment_id="c-002",
            handoff_id="h-001",
            accepted=False,
            scope_summary="Cannot handle video generation",
            open_questions=["Can we use external API?"],
        )
        assert c.accepted is False
        assert c.task_ir_id is None


class TestGovernanceContext:
    def test_default_schema_version(self):
        g = GovernanceContext()
        assert g.schema_version == GOVERNANCE_SCHEMA_VERSION

    def test_full_construction(self):
        g = GovernanceContext(
            goals=["Deploy page"],
            non_goals=["No video"],
            deliverables=[{"name": "report", "mime_type": "text/markdown"}],
            constraints={"action_space": "WRITE_WS"},
            acceptance_tests=["Page loads"],
            risk_profile={"level": "low"},
            open_questions=["Timeline?"],
            lens_snapshot_ref="lens-snap-01",
            memory_refs=["mem-001"],
            handoff_id="h-001",
        )
        assert g.goals == ["Deploy page"]
        assert g.handoff_id == "h-001"

    def test_serialization_roundtrip(self):
        g = GovernanceContext(goals=["A"], handoff_id="h-x")
        d = g.model_dump()
        g2 = GovernanceContext(**d)
        assert g2.goals == g.goals
        assert g2.schema_version == GOVERNANCE_SCHEMA_VERSION


class TestExecutionMetadataSetters:
    def test_set_execution_context(self):
        m = ExecutionMetadata()
        assert m.execution is None
        m.set_execution_context(playbook_code="yoga_outline")
        assert m.execution == {"playbook_code": "yoga_outline"}
        m.set_execution_context(execution_id="exec-001")
        assert m.execution["playbook_code"] == "yoga_outline"
        assert m.execution["execution_id"] == "exec-001"

    def test_set_intent_context(self):
        m = ExecutionMetadata()
        m.set_intent_context(intent_instance_id="ii-001")
        assert m.intent == {"intent_instance_id": "ii-001"}

    def test_governance_roundtrip(self):
        m = ExecutionMetadata()
        gov = GovernanceContext(
            goals=["Build page"],
            handoff_id="h-rt",
            constraints={"action_space": "READ_ONLY"},
        )
        m.set_governance(gov)
        assert m.governance is not None
        assert m.governance["schema_version"] == GOVERNANCE_SCHEMA_VERSION

        restored = m.get_governance()
        assert restored is not None
        assert restored.goals == ["Build page"]
        assert restored.handoff_id == "h-rt"
        assert restored.constraints == {"action_space": "READ_ONLY"}

    def test_governance_none_returns_none(self):
        m = ExecutionMetadata()
        assert m.get_governance() is None

    def test_governance_persists_through_dict(self):
        """Verify governance survives dict() -> reconstruct cycle (simulates store)."""
        m = ExecutionMetadata()
        gov = GovernanceContext(goals=["X"], acceptance_tests=["test passes"])
        m.set_governance(gov)

        serialized = m.model_dump()
        m2 = ExecutionMetadata(**serialized)
        restored = m2.get_governance()
        assert restored is not None
        assert restored.goals == ["X"]
        assert restored.acceptance_tests == ["test passes"]
        assert restored.schema_version == GOVERNANCE_SCHEMA_VERSION


class TestPhaseIRActuationFields:
    def test_backward_compatible(self):
        """Existing PhaseIR without new fields still works."""
        p = PhaseIR(id="p1", name="Step 1")
        assert p.gate is None
        assert p.checkpoint_label is None
        assert p.action_space is None
        assert p.rollback_strategy is None
        assert p.input_artifacts is None

    def test_with_actuation_fields(self):
        p = PhaseIR(
            id="p2",
            name="Deploy",
            gate="hitl_approval",
            checkpoint_label="pre_deploy",
            action_space="PUBLISH",
            rollback_strategy="revert",
            input_artifacts=["art-001", "art-002"],
        )
        assert p.gate == "hitl_approval"
        assert p.rollback_strategy == "revert"
        assert len(p.input_artifacts) == 2


class TestTaskIRBackwardCompatibility:
    def test_existing_construction_unchanged(self):
        """TaskIR without any new fields still works."""
        t = TaskIR(
            task_id="task-001",
            intent_instance_id="ii-001",
            workspace_id="ws-001",
            actor_id="user-001",
        )
        assert t.status == TaskStatus.PENDING
        assert t.phases == []
        assert t.metadata.governance is None


class TestExecutionEngineEnum:
    def test_meeting_constant(self):
        assert ExecutionEngine.MEETING.value == "meeting"

    def test_external_constant(self):
        assert ExecutionEngine.EXTERNAL.value == "external"

    def test_existing_values_unchanged(self):
        assert ExecutionEngine.PLAYBOOK.value == "playbook"
        assert ExecutionEngine.SKILL.value == "skill"
        assert ExecutionEngine.MCP.value == "mcp"
        assert ExecutionEngine.N8N.value == "n8n"
        assert ExecutionEngine.LOCAL.value == "local"
