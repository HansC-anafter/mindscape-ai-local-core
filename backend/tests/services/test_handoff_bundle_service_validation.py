"""HandoffBundleService intake guard-clause tests."""

import pytest

from backend.app.models.handoff import Commitment, HandoffIn
from backend.app.services.handoff_bundle_service import HandoffBundleService

from handoff_bundle_service_test_support import SIGNING_KEY_FIXTURE


class TestIntakeAndCompileValidation:
    """Test intake_and_compile guard clauses without MeetingEngine."""

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
