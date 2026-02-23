"""
Tests for Phase 0.5b gaps: actuation lowering, checkpoint, signed bundle,
defensive routing, and dispatch bridge.
"""

import pytest
import tempfile
import os
from unittest.mock import MagicMock, AsyncMock, patch

from backend.app.models.task_ir import (
    TaskIR,
    PhaseIR,
    PhaseStatus,
    TaskStatus,
    ExecutionMetadata,
    CheckpointSnapshot,
)
from backend.app.models.signed_bundle import SignedHandoffBundle
from backend.app.models.handoff import HandoffIn


class TestLowerToActuationPlan:
    """Gap 4: TaskIR.lower_to_actuation_plan()."""

    def _make_task_ir(self):
        return TaskIR(
            task_id="t-lower",
            intent_instance_id="ii-lower",
            workspace_id="ws-lower",
            actor_id="u-lower",
            current_phase="p0",
            status=TaskStatus.PENDING,
            phases=[
                PhaseIR(id="p0", name="Design", status=PhaseStatus.PENDING),
                PhaseIR(
                    id="p1",
                    name="Build",
                    status=PhaseStatus.PENDING,
                    preferred_engine="skill:codegen",
                ),
                PhaseIR(id="p2", name="Done", status=PhaseStatus.COMPLETED),
            ],
            artifacts=[],
            metadata=ExecutionMetadata(),
        )

    def test_fills_missing_engine(self):
        ir = self._make_task_ir()
        ir.lower_to_actuation_plan(default_engine="playbook:landing")
        assert ir.phases[0].preferred_engine == "playbook:landing"

    def test_respects_existing_engine(self):
        ir = self._make_task_ir()
        ir.lower_to_actuation_plan(default_engine="playbook:landing")
        assert ir.phases[1].preferred_engine == "skill:codegen"

    def test_skips_completed_phases(self):
        ir = self._make_task_ir()
        ir.lower_to_actuation_plan()
        assert ir.phases[2].preferred_engine is None

    def test_fills_checkpoint_label(self):
        ir = self._make_task_ir()
        ir.lower_to_actuation_plan()
        assert ir.phases[0].checkpoint_label == "pre_p0"

    def test_fills_default_gate(self):
        ir = self._make_task_ir()
        ir.lower_to_actuation_plan(default_gate="hitl_review")
        assert ir.phases[0].gate == "hitl_review"

    def test_returns_self_for_chaining(self):
        ir = self._make_task_ir()
        result = ir.lower_to_actuation_plan()
        assert result is ir


class TestCheckpointSnapshot:
    """Gap 8: create_checkpoint + rollback_to_checkpoint."""

    def _make_task_ir(self):
        return TaskIR(
            task_id="t-ckpt",
            intent_instance_id="ii-ckpt",
            workspace_id="ws-ckpt",
            actor_id="u-ckpt",
            current_phase="p0",
            status=TaskStatus.PENDING,
            phases=[
                PhaseIR(
                    id="p0",
                    name="Build",
                    status=PhaseStatus.PENDING,
                    checkpoint_label="pre_build",
                ),
            ],
            artifacts=[],
            metadata=ExecutionMetadata(),
        )

    def test_create_checkpoint_captures_state(self):
        ir = self._make_task_ir()
        ckpt = ir.create_checkpoint("p0")
        assert ckpt.label == "pre_build"
        assert ckpt.task_id == "t-ckpt"
        assert ckpt.phase_id == "p0"
        assert "task_id" in ckpt.snapshot

    def test_create_checkpoint_updates_timestamp(self):
        ir = self._make_task_ir()
        assert ir.last_checkpoint_at is None
        ir.create_checkpoint("p0")
        assert ir.last_checkpoint_at is not None

    def test_rollback_restores_state(self):
        ir = self._make_task_ir()
        ckpt = ir.create_checkpoint("p0")

        # Mutate the IR
        ir.status = TaskStatus.FAILED
        ir.phases[0].status = PhaseStatus.FAILED

        # Rollback
        restored = TaskIR.rollback_to_checkpoint(ckpt)
        assert restored.status == TaskStatus.PENDING
        assert restored.phases[0].status == PhaseStatus.PENDING

    def test_checkpoint_for_missing_phase_uses_fallback_label(self):
        ir = self._make_task_ir()
        ckpt = ir.create_checkpoint("nonexistent")
        assert ckpt.label == "pre_nonexistent"


class TestSignedHandoffBundle:
    """Gap 5: sign/verify integrity."""

    def test_create_and_verify(self):
        payload = {"handoff_id": "h-1", "goals": ["A", "B"]}
        bundle = SignedHandoffBundle.create(
            payload_type="handoff_in",
            payload=payload,
            source_device_id="dev-A",
            secret_key="test-secret-key",
        )
        assert bundle.payload_type == "handoff_in"
        assert bundle.verify("test-secret-key")

    def test_wrong_key_fails_verify(self):
        payload = {"handoff_id": "h-2"}
        bundle = SignedHandoffBundle.create(
            payload_type="handoff_in",
            payload=payload,
            source_device_id="dev-A",
            secret_key="correct-key",
        )
        assert not bundle.verify("wrong-key")

    def test_tampered_payload_fails_verify(self):
        payload = {"handoff_id": "h-3", "goals": ["Original"]}
        bundle = SignedHandoffBundle.create(
            payload_type="handoff_in",
            payload=payload,
            source_device_id="dev-A",
            secret_key="test-key",
        )
        # Tamper with payload
        bundle.payload["goals"] = ["Tampered"]
        assert not bundle.verify("test-key")

    def test_target_device_optional(self):
        payload = {"handoff_id": "h-4"}
        bundle = SignedHandoffBundle.create(
            payload_type="commitment",
            payload=payload,
            source_device_id="dev-A",
            secret_key="key",
            target_device_id="dev-B",
        )
        assert bundle.target_device_id == "dev-B"
        assert bundle.verify("key")

    def test_content_hash_deterministic(self):
        payload = {"b": 2, "a": 1}
        b1 = SignedHandoffBundle.create("result", payload, "d", "k")
        b2 = SignedHandoffBundle.create("result", payload, "d", "k")
        assert b1.content_hash == b2.content_hash


class TestHandoffHandlerDefensiveRouting:
    """Gap 7: unknown engine returns error dict, not crash."""

    @pytest.mark.asyncio
    async def test_unknown_engine_returns_error(self):
        from backend.app.services.handoff_handler import HandoffHandler

        mock_store = MagicMock()
        mock_store.get_task_ir.return_value = MagicMock()
        handler = HandoffHandler(
            task_ir_store=mock_store,
            artifact_registry=MagicMock(),
        )

        event = MagicMock()
        event.event_type = "handoff.to_unknown"
        event.from_engine = "system"
        event.to_engine = "unknown_engine:v1"
        event.task_ir = MagicMock()
        event.task_ir.task_id = "t-unknown"

        result = await handler.handle_handoff(event)
        assert result["success"] is False
        assert "Unsupported engine" in result["error"]

    @pytest.mark.asyncio
    async def test_meeting_engine_returns_deferred(self):
        from backend.app.services.handoff_handler import HandoffHandler

        mock_store = MagicMock()
        mock_store.get_task_ir.return_value = MagicMock()
        handler = HandoffHandler(
            task_ir_store=mock_store,
            artifact_registry=MagicMock(),
        )

        event = MagicMock()
        event.event_type = "handoff.to_meeting"
        event.from_engine = "system"
        event.to_engine = "meeting:review"
        event.task_ir = MagicMock()
        event.task_ir.task_id = "t-meeting"

        result = await handler.handle_handoff(event)
        assert result["success"] is True
        assert result["deferred"] is True
