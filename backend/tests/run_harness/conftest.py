import pytest

from backend.app.models.run_harness import (
    RunHarnessCapabilitySnapshotRef,
    RunHarnessPermissionProfileRef,
    RunHarnessPolicyBundleRef,
    RunIntentEnvelope,
    RunIntentSource,
)


@pytest.fixture
def run_intent() -> RunIntentEnvelope:
    return RunIntentEnvelope(
        decision_id="decision-1",
        workspace_id="workspace-1",
        profile_id="profile-1",
        origin_surface=RunIntentSource.CHAT,
        intent_text="Execute the requested operation.",
        capability_snapshot_ref=RunHarnessCapabilitySnapshotRef(ref="capabilities:1"),
        permission_profile_ref=RunHarnessPermissionProfileRef(ref="permissions:1"),
        policy_bundle_ref=RunHarnessPolicyBundleRef(ref="policies:1"),
        idempotency_key="idempotency-1",
        trace_id="trace-1",
    )

