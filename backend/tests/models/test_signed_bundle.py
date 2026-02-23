"""
Unit tests for SignedHandoffBundle model.

Covers create/verify cycle, tamper detection, wrong-key rejection,
and JSON serialization roundtrip.
"""

import copy
import json

import pytest

from backend.app.models.signed_bundle import SignedHandoffBundle


SECRET = "test-secret-key-32bytes-long!!"
PAYLOAD = {
    "handoff_id": "h_001",
    "workspace_id": "ws_001",
    "intent_summary": "Build a landing page",
    "goals": ["responsive design", "SEO optimized"],
}


class TestSignedBundleCreateVerify:
    """Create and verify cycle."""

    def test_create_and_verify_success(self):
        bundle = SignedHandoffBundle.create(
            payload_type="handoff_in",
            payload=PAYLOAD,
            source_device_id="device_A",
            secret_key=SECRET,
        )
        assert bundle.verify(SECRET) is True
        assert bundle.payload_type == "handoff_in"
        assert bundle.source_device_id == "device_A"
        assert bundle.content_hash
        assert bundle.signature

    def test_with_target_device(self):
        bundle = SignedHandoffBundle.create(
            payload_type="handoff_in",
            payload=PAYLOAD,
            source_device_id="device_A",
            secret_key=SECRET,
            target_device_id="device_B",
        )
        assert bundle.verify(SECRET) is True
        assert bundle.target_device_id == "device_B"


class TestSignedBundleTamperDetection:
    """Tampered bundles must fail verification."""

    def test_tampered_payload_fails(self):
        bundle = SignedHandoffBundle.create(
            payload_type="handoff_in",
            payload=PAYLOAD,
            source_device_id="device_A",
            secret_key=SECRET,
        )
        bundle.payload["intent_summary"] = "TAMPERED"
        assert bundle.verify(SECRET) is False

    def test_tampered_payload_type_fails(self):
        bundle = SignedHandoffBundle.create(
            payload_type="handoff_in",
            payload=PAYLOAD,
            source_device_id="device_A",
            secret_key=SECRET,
        )
        bundle.payload_type = "commitment"
        assert bundle.verify(SECRET) is False

    def test_wrong_key_fails(self):
        bundle = SignedHandoffBundle.create(
            payload_type="handoff_in",
            payload=PAYLOAD,
            source_device_id="device_A",
            secret_key=SECRET,
        )
        assert bundle.verify("wrong-key") is False


class TestSignedBundleRoundtrip:
    """JSON serialization roundtrip preserves verifiability."""

    def test_roundtrip_json(self):
        bundle = SignedHandoffBundle.create(
            payload_type="commitment",
            payload=PAYLOAD,
            source_device_id="device_B",
            secret_key=SECRET,
            target_device_id="device_A",
        )

        json_str = bundle.model_dump_json()
        restored = SignedHandoffBundle.model_validate_json(json_str)

        assert restored.verify(SECRET) is True
        assert restored.payload == PAYLOAD
        assert restored.source_device_id == "device_B"
        assert restored.target_device_id == "device_A"

    def test_roundtrip_dict(self):
        bundle = SignedHandoffBundle.create(
            payload_type="handoff_in",
            payload=PAYLOAD,
            source_device_id="device_A",
            secret_key=SECRET,
        )

        data = bundle.model_dump(mode="json")
        restored = SignedHandoffBundle(**data)

        assert restored.verify(SECRET) is True
