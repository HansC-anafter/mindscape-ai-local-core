"""Pure narrowing policy for workspace host grants."""

from __future__ import annotations

from datetime import datetime, timezone

from .contracts import (
    DeviceHostBindingProjection,
    GrantWorkspaceCommand,
    HostRuntimeAttestationProjection,
    REQUIRED_CONDITION_TYPES,
)


ATTESTATION_MAX_AGE_SECONDS = 300
ATTESTATION_FUTURE_SKEW_SECONDS = 5


def validate_grant_command(
    *,
    binding: DeviceHostBindingProjection,
    attestation: HostRuntimeAttestationProjection | None,
    command: GrantWorkspaceCommand,
    now: datetime | None = None,
) -> None:
    observed_now = now or datetime.now(timezone.utc)
    if command.binding_id != binding.binding_id:
        raise ValueError("host_grant_binding_mismatch")
    if command.binding_generation != binding.generation:
        raise ValueError("host_grant_binding_generation_mismatch")
    if binding.desired_state != "active":
        raise ValueError("host_grant_binding_not_active")
    if command.operation not in binding.operations:
        raise ValueError("host_grant_operation_not_allowed")
    if command.expires_at <= observed_now:
        raise ValueError("host_grant_expiry_not_future")
    if attestation is None:
        raise ValueError("host_grant_attestation_missing")
    if attestation.observed_generation != binding.generation:
        raise ValueError("host_grant_attestation_generation_mismatch")
    if attestation.runtime_digest != binding.runtime_digest:
        raise ValueError("host_grant_attestation_digest_mismatch")
    if command.attestation_revision != attestation.revision:
        raise ValueError("host_grant_attestation_revision_mismatch")
    if command.policy_revision != attestation.permission_revision:
        raise ValueError("host_grant_policy_revision_mismatch")
    if not attestation_is_fresh(attestation.observed_at, now=observed_now):
        raise ValueError("host_grant_attestation_stale")
    if (
        {condition.type for condition in attestation.conditions}
        != REQUIRED_CONDITION_TYPES
        or any(condition.status != "true" for condition in attestation.conditions)
    ):
        raise ValueError("host_grant_attestation_conditions_not_ready")


def attestation_is_fresh(observed_at: datetime, *, now: datetime) -> bool:
    age_seconds = (now - observed_at).total_seconds()
    return (
        -ATTESTATION_FUTURE_SKEW_SECONDS
        <= age_seconds
        <= ATTESTATION_MAX_AGE_SECONDS
    )
