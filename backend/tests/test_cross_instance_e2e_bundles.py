"""Signed handoff bundle roundtrip tests."""

import uuid

from cross_instance_e2e_test_support import (
    Commitment,
    HandoffIn,
    SignedHandoffBundle,
)


class TestSignedBundleRoundtrip:
    """Create, sign, transport, verify, and extract portable handoff bundles."""

    def test_handoff_bundle_create_verify(self) -> None:
        handoff_in = HandoffIn(
            handoff_id=str(uuid.uuid4()),
            workspace_id="ws-1",
            intent_summary="Build landing page",
            goals=["responsive design", "dark mode"],
            source_device_id="dev-A",
            target_device_id="dev-B",
        )

        signing_key = "fixture-shared-signing-key"
        bundle = SignedHandoffBundle.create(
            payload_type="handoff_in",
            payload=handoff_in.model_dump(mode="json"),
            source_device_id="dev-A",
            secret_key=signing_key,
            target_device_id="dev-B",
        )

        assert bundle.payload_type == "handoff_in"
        assert bundle.source_device_id == "dev-A"
        assert bundle.target_device_id == "dev-B"
        assert len(bundle.content_hash) == 64
        assert len(bundle.signature) == 64

        assert bundle.verify(signing_key) is True

        bundle_copy = bundle.model_copy(deep=True)
        bundle_copy.payload["intent_summary"] = "TAMPERED"
        assert bundle_copy.verify(signing_key) is False

        assert bundle.verify("wrong-secret") is False

    def test_commitment_bundle_roundtrip(self) -> None:
        commitment = Commitment(
            commitment_id=str(uuid.uuid4()),
            handoff_id=str(uuid.uuid4()),
            accepted=True,
            scope_summary="Will deliver responsive landing page",
            task_ir_id="ir-001",
        )

        signing_key = "fixture-signing-key"
        bundle = SignedHandoffBundle.create(
            payload_type="commitment",
            payload=commitment.model_dump(mode="json"),
            source_device_id="dev-B",
            secret_key=signing_key,
            target_device_id="dev-A",
        )

        assert bundle.verify(signing_key) is True
        assert bundle.payload_type == "commitment"
        assert bundle.payload["accepted"] is True
