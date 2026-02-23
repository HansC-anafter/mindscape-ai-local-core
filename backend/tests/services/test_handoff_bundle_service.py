"""
Tests for HandoffBundleService.

Covers package/verify/extract lifecycle for both HandoffIn and Commitment
payloads, including signature validation and rejection scenarios.
"""

import os

import pytest

from backend.app.models.handoff import (
    Commitment,
    DeliverableSpec,
    HandoffConstraints,
    HandoffIn,
)
from backend.app.models.signed_bundle import SignedHandoffBundle
from backend.app.services.handoff_bundle_service import HandoffBundleService

SECRET = "test-service-secret-key-32bytes!"


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
            secret_key=SECRET,
            target_device_id="dev_B",
        )

        assert isinstance(bundle, SignedHandoffBundle)
        assert bundle.payload_type == "handoff_in"
        assert bundle.source_device_id == "dev_A"
        assert bundle.target_device_id == "dev_B"
        assert bundle.verify(SECRET) is True

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
            secret_key=SECRET,
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
            secret_key=SECRET,
        )

        assert bundle.payload_type == "commitment"
        assert bundle.verify(SECRET) is True
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
            secret_key=SECRET,
        )
        assert svc.verify_bundle(bundle, secret_key=SECRET) is True

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
            secret_key=SECRET,
        )
        bundle.payload["intent_summary"] = "TAMPERED"
        assert svc.verify_bundle(bundle, secret_key=SECRET) is False


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
            secret_key=SECRET,
        )

        result = svc.extract_payload(bundle, secret_key=SECRET)
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
            secret_key=SECRET,
        )

        result = svc.extract_payload(bundle, secret_key=SECRET)
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
            secret_key=SECRET,
        )
        bundle.payload["intent_summary"] = "TAMPERED"

        with pytest.raises(ValueError, match="verification failed"):
            svc.extract_payload(bundle, secret_key=SECRET)

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
            secret_key=SECRET,
        )

        with pytest.raises(ValueError, match="verification failed"):
            svc.extract_payload(bundle, secret_key="wrong-key")


class TestSecretKeyResolution:
    """Test secret key from env var fallback."""

    def test_env_var_fallback(self, monkeypatch):
        monkeypatch.setenv("HANDOFF_BUNDLE_SECRET", "env-secret-key-123456")
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
        assert bundle.verify("env-secret-key-123456") is True

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
