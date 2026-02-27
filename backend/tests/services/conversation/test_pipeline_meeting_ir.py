"""
Store-level and PipelineCore-level integration tests for TaskIR.

Tests:
- TaskIRStore round-trip for GovernanceContext and PhaseIR actuation fields.
- TaskIRStore.replace_task_ir() atomic upsert.
- PipelineCore._extract_handoff_in() dict/model/None paths.
- MeetingIRCompilerMixin -> TaskIRStore chain.
"""

import pytest
import asyncio
import tempfile
import os
from unittest.mock import AsyncMock, MagicMock, patch

from backend.app.models.task_ir import (
    TaskIR,
    PhaseIR,
    PhaseStatus,
    TaskStatus,
    ExecutionMetadata,
    GovernanceContext,
    GOVERNANCE_SCHEMA_VERSION,
)
from backend.app.models.handoff import HandoffIn, HandoffConstraints
from backend.app.services.stores.task_ir_store import TaskIRStore
from backend.app.services.orchestration.meeting._ir_compiler import (
    MeetingIRCompilerMixin,
)


class TestTaskIRStoreGovernanceRoundTrip:
    """Verify governance fields survive create → read cycle through TaskIRStore."""

    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "test.db")
        self.store = TaskIRStore(db_path=self.db_path)

    def _make_task_ir_with_governance(self, task_id="task_test001"):
        gov = GovernanceContext(
            goals=["Deploy landing page", "Include hero banner"],
            non_goals=["No video content"],
            deliverables=[{"name": "page.html", "mime_type": "text/html"}],
            constraints={"action_space": "WRITE_WS"},
            acceptance_tests=["Page loads under 2s"],
            risk_profile={"risk_notes": ["CDN latency"]},
            handoff_id="h-roundtrip-001",
        )
        metadata = ExecutionMetadata()
        metadata.set_governance(gov)

        return TaskIR(
            task_id=task_id,
            intent_instance_id="ii-test",
            workspace_id="ws-test",
            actor_id="user-test",
            current_phase="phase_0",
            status=TaskStatus.PENDING,
            phases=[
                PhaseIR(id="phase_0", name="Build page", status=PhaseStatus.PENDING)
            ],
            artifacts=[],
            metadata=metadata,
        )

    def test_governance_survives_store_roundtrip(self):
        """Create TaskIR with governance → read back → verify GovernanceContext intact."""
        task_ir = self._make_task_ir_with_governance()
        self.store.create_task_ir(task_ir)

        restored = self.store.get_task_ir(task_ir.task_id)
        assert restored is not None

        gov = restored.metadata.get_governance()
        assert gov is not None
        assert gov.schema_version == GOVERNANCE_SCHEMA_VERSION
        assert gov.goals == ["Deploy landing page", "Include hero banner"]
        assert gov.non_goals == ["No video content"]
        assert gov.handoff_id == "h-roundtrip-001"
        assert gov.constraints == {"action_space": "WRITE_WS"}
        assert gov.acceptance_tests == ["Page loads under 2s"]

    def test_upsert_delete_create_preserves_governance(self):
        """Simulate upsert: create → delete → create with updated governance."""
        task_id = "task_upsert001"
        original = self._make_task_ir_with_governance(task_id=task_id)
        self.store.create_task_ir(original)

        # Simulate re-compilation with updated goals
        updated = self._make_task_ir_with_governance(task_id=task_id)
        updated_gov = updated.metadata.get_governance()
        updated_gov.goals = ["Updated goal A", "Updated goal B"]
        updated.metadata.set_governance(updated_gov)

        # Delete + create (upsert)
        self.store.delete_task_ir(task_id)
        self.store.create_task_ir(updated)

        restored = self.store.get_task_ir(task_id)
        assert restored is not None
        gov = restored.metadata.get_governance()
        assert gov.goals == ["Updated goal A", "Updated goal B"]

    def test_upsert_idempotent_no_crash(self):
        """Double persist with same task_id should not crash."""
        task_id = "task_idempotent"
        task_ir = self._make_task_ir_with_governance(task_id=task_id)

        # First persist
        self.store.create_task_ir(task_ir)

        # Second persist (upsert: delete + create)
        existing = self.store.get_task_ir(task_id)
        assert existing is not None
        self.store.delete_task_ir(task_id)
        self.store.create_task_ir(task_ir)

        restored = self.store.get_task_ir(task_id)
        assert restored is not None
        assert restored.metadata.get_governance() is not None

    def test_phaseir_actuation_fields_survive_roundtrip(self):
        """PhaseIR actuation fields (gate, checkpoint, etc.) persisted via phases JSON."""
        task_ir = self._make_task_ir_with_governance()
        task_ir.phases = [
            PhaseIR(
                id="p1",
                name="Deploy",
                status=PhaseStatus.PENDING,
                gate="hitl_approval",
                checkpoint_label="pre_deploy",
                action_space="PUBLISH",
                rollback_strategy="revert",
                input_artifacts=["art-001"],
            )
        ]
        self.store.create_task_ir(task_ir)

        restored = self.store.get_task_ir(task_ir.task_id)
        p = restored.phases[0]
        assert p.gate == "hitl_approval"
        assert p.checkpoint_label == "pre_deploy"
        assert p.action_space == "PUBLISH"
        assert p.rollback_strategy == "revert"
        assert p.input_artifacts == ["art-001"]


class TestCompilerToStoreChain:
    """Test MeetingIRCompilerMixin output can be stored and read back."""

    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "test.db")
        self.store = TaskIRStore(db_path=self.db_path)

    def test_compiled_ir_with_handoff_stores_correctly(self):
        """Compiler output (with HandoffIn) → store → read → governance intact."""

        class FakeEngine(MeetingIRCompilerMixin):
            def __init__(self):
                self.session = MagicMock()
                self.session.id = "sess-chain"
                self.session.workspace_id = "ws-chain"
                self.profile_id = "user-chain"

        engine = FakeEngine()
        handoff = HandoffIn(
            handoff_id="h-chain-001",
            workspace_id="ws-chain",
            intent_summary="Build report",
            goals=["Generate PDF", "Include charts"],
            acceptance_tests=["PDF valid"],
            constraints=HandoffConstraints(action_space="WRITE_WS"),
        )
        compiled = engine._compile_to_task_ir(
            decision="Approved",
            action_items=[
                {"title": "Research", "description": "Gather data"},
                {"title": "Compile", "description": "Build PDF"},
            ],
            handoff_in=handoff,
        )

        # Store it
        self.store.create_task_ir(compiled)

        # Read back
        restored = self.store.get_task_ir(compiled.task_id)
        assert restored is not None
        assert len(restored.phases) == 2
        assert restored.phases[0].name == "Research"
        assert restored.phases[1].depends_on == ["action_0"]

        gov = restored.metadata.get_governance()
        assert gov is not None
        assert gov.goals == ["Generate PDF", "Include charts"]
        assert gov.handoff_id == "h-chain-001"
        assert gov.acceptance_tests == ["PDF valid"]
        assert gov.constraints["action_space"] == "WRITE_WS"
        assert gov.schema_version == GOVERNANCE_SCHEMA_VERSION

    def test_compiled_ir_without_handoff_stores_correctly(self):
        """Pure meeting (no HandoffIn) → store → read → no governance."""

        class FakeEngine(MeetingIRCompilerMixin):
            def __init__(self):
                self.session = MagicMock()
                self.session.id = "sess-pure"
                self.session.workspace_id = "ws-pure"
                self.profile_id = "user-pure"

        engine = FakeEngine()
        compiled = engine._compile_to_task_ir(
            decision="Do nothing",
            action_items=[],
            handoff_in=None,
        )

        self.store.create_task_ir(compiled)
        restored = self.store.get_task_ir(compiled.task_id)
        assert restored is not None
        assert restored.metadata.get_governance() is None
        assert len(restored.phases) == 1
        assert restored.phases[0].name == "Execute Decision"


class TestAtomicReplaceTaskIR:
    """Verify TaskIRStore.replace_task_ir() operates atomically."""

    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "test.db")
        self.store = TaskIRStore(db_path=self.db_path)

    def _make_task_ir(self, task_id="task_atomic", goal="Original goal"):
        gov = GovernanceContext(goals=[goal], handoff_id="h-atomic")
        metadata = ExecutionMetadata()
        metadata.set_governance(gov)
        return TaskIR(
            task_id=task_id,
            intent_instance_id="ii-atomic",
            workspace_id="ws-atomic",
            actor_id="u-atomic",
            current_phase="p0",
            status=TaskStatus.PENDING,
            phases=[PhaseIR(id="p0", name="Do", status=PhaseStatus.PENDING)],
            artifacts=[],
            metadata=metadata,
        )

    def test_replace_on_empty_db_inserts(self):
        """replace_task_ir on non-existent row behaves like create."""
        task_ir = self._make_task_ir()
        replaced = self.store.replace_task_ir(task_ir)
        assert replaced is False

        restored = self.store.get_task_ir(task_ir.task_id)
        assert restored is not None
        assert restored.metadata.get_governance().goals == ["Original goal"]

    def test_replace_on_existing_row_replaces(self):
        """replace_task_ir on existing row replaces all fields."""
        original = self._make_task_ir(goal="Original goal")
        self.store.create_task_ir(original)

        updated = self._make_task_ir(goal="Updated goal")
        replaced = self.store.replace_task_ir(updated)
        assert replaced is True

        restored = self.store.get_task_ir(original.task_id)
        assert restored.metadata.get_governance().goals == ["Updated goal"]

    def test_replace_idempotent(self):
        """Double replace_task_ir should not crash."""
        task_ir = self._make_task_ir()
        self.store.replace_task_ir(task_ir)
        self.store.replace_task_ir(task_ir)

        restored = self.store.get_task_ir(task_ir.task_id)
        assert restored is not None


class TestExtractHandoffIn:
    """Verify extract_handoff_in() handles all input forms."""

    def setup_method(self):
        from backend.app.services.conversation.pipeline_meeting import (
            extract_handoff_in,
        )

        self._extract = extract_handoff_in

    def test_none_request_returns_none(self):
        assert self._extract(None) is None

    def test_request_without_handoff_in_attr_returns_none(self):
        req = MagicMock(spec=[])
        assert self._extract(req) is None

    def test_dict_input_returns_handoff_in_model(self):
        req = MagicMock()
        req.handoff_in = {
            "handoff_id": "h-dict",
            "workspace_id": "ws-dict",
            "intent_summary": "Test",
            "goals": ["A"],
        }
        result = self._extract(req)
        assert result is not None
        assert result.handoff_id == "h-dict"
        assert result.goals == ["A"]

    def test_model_input_passes_through(self):
        handoff = HandoffIn(
            handoff_id="h-model",
            workspace_id="ws-model",
            intent_summary="Test",
            goals=["B"],
        )
        req = MagicMock()
        req.handoff_in = handoff
        result = self._extract(req)
        assert result is handoff

    def test_falsy_handoff_in_returns_none(self):
        req = MagicMock()
        req.handoff_in = {}
        assert self._extract(req) is None


class TestPipelineCoreHandoffInPath:
    """Full-path test: request.handoff_in -> _extract -> engine.run(handoff_in=...) -> persist."""

    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "test.db")
        self.store = TaskIRStore(db_path=self.db_path)

    def test_handoff_in_reaches_meeting_engine_and_persists(self):
        """Verify handoff_in passes through the full chain and is persisted."""
        from backend.app.services.conversation.pipeline_meeting import (
            extract_handoff_in,
        )

        # Build a request with handoff_in
        request = MagicMock()
        request.handoff_in = {
            "handoff_id": "h-fullpath-001",
            "workspace_id": "ws-fullpath",
            "intent_summary": "Build landing page",
            "goals": ["Hero banner", "Contact form"],
            "acceptance_tests": ["Loads under 2s"],
        }

        # Extract handoff_in
        handoff = extract_handoff_in(request)
        assert handoff is not None
        assert handoff.handoff_id == "h-fullpath-001"
        assert handoff.goals == ["Hero banner", "Contact form"]

        # Simulate the compiler step (what engine.run does internally)
        class FakeEngine(MeetingIRCompilerMixin):
            def __init__(self):
                self.session = MagicMock()
                self.session.id = "sess-fullpath"
                self.session.workspace_id = "ws-fullpath"
                self.profile_id = "user-fullpath"

        engine = FakeEngine()
        task_ir = engine._compile_to_task_ir(
            decision="Build it",
            action_items=[{"title": "Design", "description": "Create mockup"}],
            handoff_in=handoff,
        )

        # Persist (simulates _persist_meeting_task_ir)
        self.store.replace_task_ir(task_ir)

        # Verify
        restored = self.store.get_task_ir(task_ir.task_id)
        assert restored is not None
        gov = restored.metadata.get_governance()
        assert gov.handoff_id == "h-fullpath-001"
        assert gov.goals == ["Hero banner", "Contact form"]
        assert gov.acceptance_tests == ["Loads under 2s"]
