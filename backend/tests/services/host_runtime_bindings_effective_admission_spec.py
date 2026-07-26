from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.app.services.host_runtime_bindings.contracts import (
    DeviceHostBindingProjection,
    HostRuntimeAttestationProjection,
    HostRuntimeCondition,
    WorkspaceHostGrantProjection,
)
from backend.app.services.host_runtime_bindings.effective_admission import (
    evaluate_effective_host_admission,
)


NOW = datetime(2026, 7, 27, tzinfo=timezone.utc)
DIGEST = "a" * 64


def _binding(
    *,
    generation: int = 2,
    observed_generation: int = 2,
    condition_status: str = "true",
) -> DeviceHostBindingProjection:
    conditions = [
        HostRuntimeCondition(
            type=kind,
            status=condition_status,
            reason="verified",
            observed_generation=observed_generation,
            observed_at=NOW,
        )
        for kind in (
            "Materialized",
            "RuntimeDigestVerified",
            "SupervisorReady",
            "PermissionsReady",
            "ResourceLaneReady",
        )
    ]
    return DeviceHostBindingProjection(
        binding_id="binding-a",
        device_id="device-a",
        capability_code="live_interface_interpreter",
        requirement_code="live_interface_automation",
        capability_version="0.1.36",
        runtime_digest=DIGEST,
        host_assets_digest=DIGEST,
        entrypoint="scripts/host_runtime_entry.py",
        entrypoint_digest="d" * 64,
        desired_state="active",
        generation=generation,
        observed_generation=observed_generation,
        share_policy="workspace_grants",
        operations=["watch-screenshots", "mobile-upload-funnel"],
        permission_classes=["filesystem.read"],
        resource_lane="host.io.light",
        materialized_root="/runtime/live-interface",
        finalizers=["mindscape.ai/host-runtime-cleanup"],
        attestation=HostRuntimeAttestationProjection(
            revision=4,
            observed_generation=observed_generation,
            runtime_digest=DIGEST,
            executor_identity_digest="c" * 64,
            permission_revision=3,
            conditions=conditions,
            observed_at=NOW,
        ),
    )


def _grant(
    *,
    workspace_id: str = "workspace-a",
    generation: int = 2,
    attestation_revision: int = 4,
    status: str = "active",
) -> WorkspaceHostGrantProjection:
    return WorkspaceHostGrantProjection(
        grant_id="grant-a",
        workspace_id=workspace_id,
        binding_id="binding-a",
        binding_generation=generation,
        operation="watch-screenshots",
        operation_args_sha256="d" * 64,
        policy_revision=3,
        attestation_revision=attestation_revision,
        expires_at=NOW + timedelta(hours=1),
        status=status,
    )


def test_effective_host_admission_requires_complete_exact_closure():
    result = evaluate_effective_host_admission(
        workspace_id="workspace-a",
        operation="watch-screenshots",
        binding=_binding(),
        grant=_grant(),
        now=NOW,
    )

    assert result.admitted is True
    assert result.blockers == []
    assert result.binding_generation == 2
    assert result.attestation_revision == 4
    assert result.policy_revision == 3


def test_workspace_grant_does_not_leak_to_other_workspace():
    result = evaluate_effective_host_admission(
        workspace_id="workspace-b",
        operation="watch-screenshots",
        binding=_binding(),
        grant=_grant(workspace_id="workspace-a"),
        now=NOW,
    )

    assert result.admitted is False
    assert result.blockers == ["grant_not_active"]


def test_generation_and_condition_mismatch_fail_closed_in_stable_order():
    result = evaluate_effective_host_admission(
        workspace_id="workspace-a",
        operation="watch-screenshots",
        binding=_binding(observed_generation=1, condition_status="unknown"),
        grant=_grant(generation=1, attestation_revision=3),
        now=NOW,
    )

    assert result.admitted is False
    assert result.blockers == [
        "attestation_generation_mismatch",
        "attestation_condition_not_ready",
        "grant_generation_mismatch",
    ]


def test_pack_or_binding_absence_never_falls_back_to_grant_only():
    result = evaluate_effective_host_admission(
        workspace_id="workspace-a",
        operation="watch-screenshots",
        binding=None,
        grant=_grant(),
        now=NOW,
    )

    assert result.admitted is False
    assert result.blockers == ["binding_missing"]


def test_stale_attestation_and_policy_revision_fail_closed():
    binding = _binding()
    binding.attestation.observed_at = NOW - timedelta(minutes=6)
    grant = _grant()
    grant.policy_revision = 4

    result = evaluate_effective_host_admission(
        workspace_id="workspace-a",
        operation="watch-screenshots",
        binding=binding,
        grant=grant,
        now=NOW,
    )

    assert result.admitted is False
    assert result.blockers == [
        "attestation_stale",
        "grant_policy_revision_mismatch",
    ]


def test_newer_health_attestation_preserves_grant_but_future_revision_fails():
    assert evaluate_effective_host_admission(
        workspace_id="workspace-a",
        operation="watch-screenshots",
        binding=_binding(),
        grant=_grant(attestation_revision=3),
        now=NOW,
    ).admitted is True

    result = evaluate_effective_host_admission(
        workspace_id="workspace-a",
        operation="watch-screenshots",
        binding=_binding(),
        grant=_grant(attestation_revision=5),
        now=NOW,
    )
    assert result.admitted is False
    assert result.blockers == ["grant_attestation_revision_mismatch"]
