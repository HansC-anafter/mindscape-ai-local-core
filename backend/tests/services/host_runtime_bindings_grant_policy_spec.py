from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.app.services.host_runtime_bindings.contracts import (
    DeviceHostBindingProjection,
    GrantWorkspaceCommand,
    HostRuntimeAttestationProjection,
    HostRuntimeCondition,
)
from backend.app.services.host_runtime_bindings.grant_policy import (
    validate_grant_command,
)


NOW = datetime(2026, 7, 27, tzinfo=timezone.utc)
DIGEST = "a" * 64


def _attestation(
    *,
    observed_at: datetime = NOW,
    permission_revision: int = 3,
) -> HostRuntimeAttestationProjection:
    return HostRuntimeAttestationProjection(
        revision=4,
        observed_generation=2,
        runtime_digest=DIGEST,
        executor_identity_digest="b" * 64,
        permission_revision=permission_revision,
        conditions=[
            HostRuntimeCondition(
                type=condition_type,
                status="true",
                reason="verified",
                observed_generation=2,
                observed_at=observed_at,
            )
            for condition_type in (
                "Materialized",
                "RuntimeDigestVerified",
                "SupervisorReady",
                "PermissionsReady",
                "ResourceLaneReady",
            )
        ],
        observed_at=observed_at,
    )


def _binding(attestation: HostRuntimeAttestationProjection) -> DeviceHostBindingProjection:
    return DeviceHostBindingProjection(
        binding_id="binding-a",
        device_id="device-a",
        capability_code="demo_pack",
        requirement_code="demo_runtime",
        capability_version="1.2.3",
        runtime_digest=DIGEST,
        host_assets_digest=DIGEST,
        entrypoint="scripts/host_runtime_entry.py",
        entrypoint_digest="c" * 64,
        desired_state="active",
        generation=2,
        observed_generation=2,
        share_policy="workspace_grants",
        operations=["custom.operation"],
        permission_classes=["filesystem.read"],
        resource_lane="host.io.light",
        materialized_root="/runtime/demo",
        attestation=attestation,
    )


def _command(**overrides) -> GrantWorkspaceCommand:
    values = {
        "workspace_id": "workspace-a",
        "binding_id": "binding-a",
        "binding_generation": 2,
        "operation": "custom.operation",
        "operation_args_sha256": "d" * 64,
        "policy_revision": 3,
        "attestation_revision": 4,
        "expires_at": NOW + timedelta(minutes=10),
    }
    values.update(overrides)
    return GrantWorkspaceCommand.model_validate(values)


def test_grant_accepts_pack_declared_operation_and_exact_current_policy() -> None:
    attestation = _attestation()

    validate_grant_command(
        binding=_binding(attestation),
        attestation=attestation,
        command=_command(),
        now=NOW,
    )


@pytest.mark.parametrize(
    ("attestation", "command", "error"),
    [
        (
            _attestation(permission_revision=4),
            _command(),
            "policy_revision_mismatch",
        ),
        (
            _attestation(observed_at=NOW - timedelta(seconds=301)),
            _command(),
            "attestation_stale",
        ),
    ],
)
def test_grant_causal_policy_and_freshness_fail_closed(
    attestation: HostRuntimeAttestationProjection,
    command: GrantWorkspaceCommand,
    error: str,
) -> None:
    with pytest.raises(ValueError, match=error):
        validate_grant_command(
            binding=_binding(attestation),
            attestation=attestation,
            command=command,
            now=NOW,
        )
