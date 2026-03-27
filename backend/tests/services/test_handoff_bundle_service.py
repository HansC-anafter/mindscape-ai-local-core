"""
Tests for HandoffBundleService.

Covers package/verify/extract lifecycle for both HandoffIn and Commitment
payloads, including signature validation, rejection scenarios, and
happy-path intake_and_compile integration (mocked MeetingEngine).
"""

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from backend.app.models.handoff import (
    Commitment,
    DeliverableSpec,
    HandoffConstraints,
    HandoffIn,
)
from backend.app.models.signed_bundle import SignedHandoffBundle
from backend.app.services.handoff_bundle_service import HandoffBundleService

SIGNING_KEY_FIXTURE = "fixture-service-signing-key-32!"


class TestPackageHandoffIn:
    """Package HandoffIn into signed bundle."""

    def test_package_and_verify(self):
        handoff = HandoffIn(
            handoff_id="h_svc_001",
            workspace_id="ws_001",
            intent_summary="Build landing page",
            goals=["responsive", "SEO"],
            deliverables=[DeliverableSpec(name="index.html", mime_type="text/html")],
        )
        svc = HandoffBundleService()
        bundle = svc.package_handoff(
            handoff_in=handoff,
            source_device_id="dev_A",
            secret_key=SIGNING_KEY_FIXTURE,
            target_device_id="dev_B",
        )

        assert isinstance(bundle, SignedHandoffBundle)
        assert bundle.payload_type == "handoff_in"
        assert bundle.source_device_id == "dev_A"
        assert bundle.target_device_id == "dev_B"
        assert bundle.verify(SIGNING_KEY_FIXTURE) is True

    def test_payload_contains_handoff_fields(self):
        handoff = HandoffIn(
            handoff_id="h_svc_002",
            workspace_id="ws_002",
            intent_summary="Test payload fields",
            constraints=HandoffConstraints(action_space="READ_ONLY"),
        )
        svc = HandoffBundleService()
        bundle = svc.package_handoff(
            handoff_in=handoff,
            source_device_id="dev_A",
            secret_key=SIGNING_KEY_FIXTURE,
        )

        assert bundle.payload["handoff_id"] == "h_svc_002"
        assert bundle.payload["constraints"]["action_space"] == "READ_ONLY"


class TestPackageCommitment:
    """Package Commitment into signed bundle."""

    def test_package_and_verify(self):
        commitment = Commitment(
            commitment_id="c_001",
            handoff_id="h_001",
            accepted=True,
            scope_summary="Will build landing page with responsive design",
            estimated_phases=3,
        )
        svc = HandoffBundleService()
        bundle = svc.package_commitment(
            commitment=commitment,
            source_device_id="dev_B",
            secret_key=SIGNING_KEY_FIXTURE,
        )

        assert bundle.payload_type == "commitment"
        assert bundle.verify(SIGNING_KEY_FIXTURE) is True
        assert bundle.payload["accepted"] is True


class TestVerifyBundle:
    """Verify bundle integrity."""

    def test_verify_valid(self):
        handoff = HandoffIn(
            handoff_id="h_v_001",
            workspace_id="ws_001",
            intent_summary="verify test",
        )
        svc = HandoffBundleService()
        bundle = svc.package_handoff(
            handoff_in=handoff,
            source_device_id="dev_A",
            secret_key=SIGNING_KEY_FIXTURE,
        )
        assert svc.verify_bundle(bundle, secret_key=SIGNING_KEY_FIXTURE) is True

    def test_verify_tampered_fails(self):
        handoff = HandoffIn(
            handoff_id="h_v_002",
            workspace_id="ws_001",
            intent_summary="tamper test",
        )
        svc = HandoffBundleService()
        bundle = svc.package_handoff(
            handoff_in=handoff,
            source_device_id="dev_A",
            secret_key=SIGNING_KEY_FIXTURE,
        )
        bundle.payload["intent_summary"] = "TAMPERED"
        assert svc.verify_bundle(bundle, secret_key=SIGNING_KEY_FIXTURE) is False


class TestExtractPayload:
    """Extract typed payload from verified bundle."""

    def test_extract_handoff_in(self):
        handoff = HandoffIn(
            handoff_id="h_e_001",
            workspace_id="ws_001",
            intent_summary="extract test",
            goals=["goal1", "goal2"],
        )
        svc = HandoffBundleService()
        bundle = svc.package_handoff(
            handoff_in=handoff,
            source_device_id="dev_A",
            secret_key=SIGNING_KEY_FIXTURE,
        )

        result = svc.extract_payload(bundle, secret_key=SIGNING_KEY_FIXTURE)
        assert result["payload_type"] == "handoff_in"
        extracted = result["payload"]
        assert isinstance(extracted, HandoffIn)
        assert extracted.handoff_id == "h_e_001"
        assert extracted.goals == ["goal1", "goal2"]

    def test_extract_commitment(self):
        commitment = Commitment(
            commitment_id="c_e_001",
            handoff_id="h_001",
            accepted=False,
            scope_summary="Rejected due to timeline",
            open_questions=["Can deadline be extended?"],
        )
        svc = HandoffBundleService()
        bundle = svc.package_commitment(
            commitment=commitment,
            source_device_id="dev_B",
            secret_key=SIGNING_KEY_FIXTURE,
        )

        result = svc.extract_payload(bundle, secret_key=SIGNING_KEY_FIXTURE)
        assert result["payload_type"] == "commitment"
        extracted = result["payload"]
        assert isinstance(extracted, Commitment)
        assert extracted.accepted is False

    def test_extract_invalid_signature_rejected(self):
        handoff = HandoffIn(
            handoff_id="h_e_003",
            workspace_id="ws_001",
            intent_summary="reject test",
        )
        svc = HandoffBundleService()
        bundle = svc.package_handoff(
            handoff_in=handoff,
            source_device_id="dev_A",
            secret_key=SIGNING_KEY_FIXTURE,
        )
        bundle.payload["intent_summary"] = "TAMPERED"

        with pytest.raises(ValueError, match="verification failed"):
            svc.extract_payload(bundle, secret_key=SIGNING_KEY_FIXTURE)

    def test_extract_wrong_key_rejected(self):
        handoff = HandoffIn(
            handoff_id="h_e_004",
            workspace_id="ws_001",
            intent_summary="wrong key test",
        )
        svc = HandoffBundleService()
        bundle = svc.package_handoff(
            handoff_in=handoff,
            source_device_id="dev_A",
            secret_key=SIGNING_KEY_FIXTURE,
        )

        with pytest.raises(ValueError, match="verification failed"):
            svc.extract_payload(bundle, secret_key="wrong-key")


class TestSecretKeyResolution:
    """Test secret key from env var fallback."""

    def test_env_var_fallback(self, monkeypatch):
        monkeypatch.setenv("HANDOFF_BUNDLE_SECRET", "fixture-bundle-key-123456")
        handoff = HandoffIn(
            handoff_id="h_env_001",
            workspace_id="ws_001",
            intent_summary="env test",
        )
        svc = HandoffBundleService()
        bundle = svc.package_handoff(
            handoff_in=handoff,
            source_device_id="dev_A",
        )
        assert bundle.verify("fixture-bundle-key-123456") is True

    def test_no_secret_raises(self, monkeypatch):
        monkeypatch.delenv("HANDOFF_BUNDLE_SECRET", raising=False)
        handoff = HandoffIn(
            handoff_id="h_env_002",
            workspace_id="ws_001",
            intent_summary="no secret test",
        )
        svc = HandoffBundleService()
        with pytest.raises(ValueError, match="not configured"):
            svc.package_handoff(
                handoff_in=handoff,
                source_device_id="dev_A",
            )


class TestIntakeAndCompileValidation:
    """Test intake_and_compile guard clauses (no MeetingEngine needed)."""

    @pytest.mark.asyncio
    async def test_tampered_bundle_rejected(self):
        handoff = HandoffIn(
            handoff_id="h_ic_001",
            workspace_id="ws_001",
            intent_summary="tamper test",
            goals=["goal1"],
        )
        svc = HandoffBundleService()
        bundle = svc.package_handoff(
            handoff_in=handoff,
            source_device_id="dev_A",
            secret_key=SIGNING_KEY_FIXTURE,
        )
        bundle.payload["intent_summary"] = "TAMPERED"

        with pytest.raises(ValueError, match="verification failed"):
            await svc.intake_and_compile(
                bundle=bundle,
                workspace=None,
                runtime_profile=None,
                profile_id="test",
                thread_id="t1",
                project_id="p1",
                secret_key=SIGNING_KEY_FIXTURE,
            )

    @pytest.mark.asyncio
    async def test_wrong_payload_type_rejected(self):
        commitment = Commitment(
            commitment_id="c_ic_001",
            handoff_id="h_001",
            accepted=True,
            scope_summary="test",
        )
        svc = HandoffBundleService()
        bundle = svc.package_commitment(
            commitment=commitment,
            source_device_id="dev_B",
            secret_key=SIGNING_KEY_FIXTURE,
        )

        with pytest.raises(ValueError, match="requires handoff_in bundle"):
            await svc.intake_and_compile(
                bundle=bundle,
                workspace=None,
                runtime_profile=None,
                profile_id="test",
                thread_id="t1",
                project_id="p1",
                secret_key=SIGNING_KEY_FIXTURE,
            )

    @pytest.mark.asyncio
    async def test_wrong_secret_rejected(self):
        handoff = HandoffIn(
            handoff_id="h_ic_003",
            workspace_id="ws_001",
            intent_summary="wrong key test",
            goals=["goal1"],
        )
        svc = HandoffBundleService()
        bundle = svc.package_handoff(
            handoff_in=handoff,
            source_device_id="dev_A",
            secret_key=SIGNING_KEY_FIXTURE,
        )

        with pytest.raises(ValueError, match="verification failed"):
            await svc.intake_and_compile(
                bundle=bundle,
                workspace=None,
                runtime_profile=None,
                profile_id="test",
                thread_id="t1",
                project_id="p1",
                secret_key="wrong-key-here",
            )


# ---------------------------------------------------------------------------
# Helper: lightweight MeetingResult stand-in (mirrors engine.py dataclass)
# ---------------------------------------------------------------------------


@dataclass
class _FakeMeetingResult:
    session_id: str = "sess-test-001"
    minutes_md: str = "Test minutes"
    decision: str = "Approve the plan"
    action_items: List[Dict[str, Any]] = field(default_factory=list)
    event_ids: List[str] = field(default_factory=list)
    task_ir: Optional[Any] = None


class TestCompileHappyPath:
    """Happy-path tests for intake_and_compile (mocked MeetingEngine).

    intake_and_compile() uses inline 'from X import Y' statements.
    In the test environment the deep import chain
    (orchestration.meeting -> stores -> ...) triggers ModuleNotFoundError.
    We inject lightweight fake modules into sys.modules BEFORE calling the
    function so the inline imports resolve to our mocks.
    """

    def _make_bundle(self):
        """Build a valid handoff_in bundle for compile tests."""
        handoff = HandoffIn(
            handoff_id="h_hp_001",
            workspace_id="ws_001",
            intent_summary="Build landing page",
            goals=["responsive", "SEO"],
            deliverables=[DeliverableSpec(name="index.html", mime_type="text/html")],
        )
        svc = HandoffBundleService()
        return svc.package_handoff(
            handoff_in=handoff,
            source_device_id="dev_A",
            secret_key=SIGNING_KEY_FIXTURE,
        )

    @pytest.mark.asyncio
    async def test_compile_happy_path_produces_task_ir(self):
        """Full compile path: bundle -> MeetingEngine -> TaskIR -> persist."""
        import sys
        import types

        bundle = self._make_bundle()

        from backend.app.models.task_ir import TaskIR, TaskStatus

        fake_ir = TaskIR(
            task_id="task_hp_001",
            workspace_id="ws_001",
            intent_instance_id="intent-test-001",
            actor_id="test-user",
            status=TaskStatus.PENDING,
        )
        fake_result = _FakeMeetingResult(
            task_ir=fake_ir,
            action_items=[{"title": "Build"}],
        )

        fake_session = MagicMock()
        fake_session.id = "sess-hp-001"
        fake_session.workspace_id = "ws_001"

        mock_session_store = MagicMock()
        mock_session_store.get_active_session.return_value = None
        mock_session_store.create.return_value = None

        mock_ms_cls = MagicMock()
        mock_ms_cls.new.return_value = fake_session

        async def _fake_run(*a, **kw):
            return fake_result

        mock_engine_cls = MagicMock()
        mock_engine = MagicMock()
        mock_engine.run = _fake_run
        mock_engine_cls.return_value = mock_engine

        mock_ir_store = MagicMock()
        mock_ir_store.replace_task_ir.return_value = True
        mock_ir_store_cls = MagicMock(return_value=mock_ir_store)

        # Build fake modules for inline imports
        mod_meeting = types.ModuleType("backend.app.services.orchestration.meeting")
        mod_meeting.MeetingEngine = mock_engine_cls

        mod_session_store = types.ModuleType(
            "backend.app.services.stores.meeting_session_store"
        )
        mod_session_store.MeetingSessionStore = MagicMock(
            return_value=mock_session_store
        )

        mod_meeting_session = types.ModuleType("backend.app.models.meeting_session")
        mod_meeting_session.MeetingSession = mock_ms_cls

        mod_pg_ir = types.ModuleType(
            "backend.app.services.stores.postgres.task_ir_store"
        )
        mod_pg_ir.PostgresTaskIRStore = mock_ir_store_cls
        mod_mindscape_store = types.ModuleType("backend.app.services.mindscape_store")
        mod_mindscape_store.MindscapeStore = MagicMock(return_value=MagicMock())

        target_modules = {
            "backend.app.services.orchestration.meeting": mod_meeting,
            "backend.app.services.stores.meeting_session_store": mod_session_store,
            "backend.app.models.meeting_session": mod_meeting_session,
            "backend.app.services.stores.postgres.task_ir_store": mod_pg_ir,
            "backend.app.services.mindscape_store": mod_mindscape_store,
        }

        saved = {k: sys.modules.get(k) for k in target_modules}
        sys.modules.update(target_modules)
        try:
            svc = HandoffBundleService()
            result = await svc.intake_and_compile(
                bundle=bundle,
                workspace=MagicMock(id="ws_001"),
                runtime_profile=None,
                profile_id="test-user",
                thread_id="t1",
                project_id="p1",
                secret_key=SIGNING_KEY_FIXTURE,
            )
        finally:
            for k, v in saved.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v

        assert result["status"] == "compiled"
        assert result["task_ir_id"] == "task_hp_001"
        assert result["persisted"] is True
        assert result["action_items_count"] == 1

        # Call contract: MeetingEngine constructed and run() called
        mock_engine_cls.assert_called_once()
        # Call contract: session store queried, new session created
        mock_session_store.get_active_session.assert_called_once()
        mock_session_store.create.assert_called_once_with(fake_session)
        # Call contract: TaskIR persisted via replace_task_ir
        mock_ir_store.replace_task_ir.assert_called_once_with(fake_ir)

    @pytest.mark.asyncio
    async def test_compile_happy_path_no_task_ir(self):
        """Compile path where MeetingEngine produces no TaskIR."""
        import sys
        import types

        bundle = self._make_bundle()

        fake_result = _FakeMeetingResult(task_ir=None)

        fake_session = MagicMock()
        fake_session.id = "sess-hp-002"
        fake_session.workspace_id = "ws_001"

        mock_session_store = MagicMock()
        mock_session_store.get_active_session.return_value = fake_session

        async def _fake_run(*a, **kw):
            return fake_result

        mock_engine_cls = MagicMock()
        mock_engine = MagicMock()
        mock_engine.run = _fake_run
        mock_engine_cls.return_value = mock_engine

        mod_meeting = types.ModuleType("backend.app.services.orchestration.meeting")
        mod_meeting.MeetingEngine = mock_engine_cls

        mod_session_store = types.ModuleType(
            "backend.app.services.stores.meeting_session_store"
        )
        mod_session_store.MeetingSessionStore = MagicMock(
            return_value=mock_session_store
        )
        mod_mindscape_store = types.ModuleType("backend.app.services.mindscape_store")
        mod_mindscape_store.MindscapeStore = MagicMock(return_value=MagicMock())

        target_modules = {
            "backend.app.services.orchestration.meeting": mod_meeting,
            "backend.app.services.stores.meeting_session_store": mod_session_store,
            "backend.app.services.mindscape_store": mod_mindscape_store,
        }

        saved = {k: sys.modules.get(k) for k in target_modules}
        sys.modules.update(target_modules)
        try:
            svc = HandoffBundleService()
            result = await svc.intake_and_compile(
                bundle=bundle,
                workspace=MagicMock(id="ws_001"),
                runtime_profile=None,
                profile_id="test-user",
                thread_id="t1",
                project_id="p1",
                secret_key=SIGNING_KEY_FIXTURE,
            )
        finally:
            for k, v in saved.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v

        assert result["status"] == "compiled"
        assert result["task_ir_id"] is None
        assert result["persisted"] is False

        # Call contract: engine constructed and run() called
        mock_engine_cls.assert_called_once()
        # Call contract: existing session reused, no create
        mock_session_store.get_active_session.assert_called_once()
