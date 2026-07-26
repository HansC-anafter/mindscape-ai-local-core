"""Pure composite host admission truth table and blocker ordering."""

from __future__ import annotations

from datetime import datetime, timezone

from .contracts import (
    DeviceHostBindingProjection,
    EffectiveHostAdmissionProjection,
    HostOperation,
    REQUIRED_CONDITION_TYPES,
    WorkspaceHostGrantProjection,
)
from .grant_policy import attestation_is_fresh


BLOCKER_ORDER = (
    "binding_missing",
    "binding_not_active",
    "operation_not_declared",
    "runtime_not_materialized",
    "attestation_missing",
    "attestation_generation_mismatch",
    "attestation_digest_mismatch",
    "attestation_stale",
    "attestation_condition_not_ready",
    "grant_missing",
    "grant_not_active",
    "grant_expired",
    "grant_generation_mismatch",
    "grant_attestation_revision_mismatch",
    "grant_policy_revision_mismatch",
)


def evaluate_effective_host_admission(
    *,
    workspace_id: str,
    operation: HostOperation,
    binding: DeviceHostBindingProjection | None,
    grant: WorkspaceHostGrantProjection | None,
    now: datetime | None = None,
) -> EffectiveHostAdmissionProjection:
    blockers: set[str] = set()
    observed_now = now or datetime.now(timezone.utc)
    if binding is None:
        blockers.add("binding_missing")
    else:
        if binding.desired_state != "active":
            blockers.add("binding_not_active")
        if operation not in binding.operations:
            blockers.add("operation_not_declared")
        if binding.materialized_root is None:
            blockers.add("runtime_not_materialized")
        attestation = binding.attestation
        if attestation is None:
            blockers.add("attestation_missing")
        else:
            if attestation.observed_generation != binding.generation:
                blockers.add("attestation_generation_mismatch")
            if attestation.runtime_digest != binding.runtime_digest:
                blockers.add("attestation_digest_mismatch")
            if not attestation_is_fresh(
                attestation.observed_at,
                now=observed_now,
            ):
                blockers.add("attestation_stale")
            if (
                {condition.type for condition in attestation.conditions}
                != REQUIRED_CONDITION_TYPES
                or any(
                condition.status != "true"
                for condition in attestation.conditions
                )
            ):
                blockers.add("attestation_condition_not_ready")
    if grant is None:
        blockers.add("grant_missing")
    else:
        if grant.workspace_id != workspace_id or grant.operation != operation:
            blockers.add("grant_not_active")
        if grant.status != "active":
            blockers.add("grant_not_active")
        if grant.expires_at <= observed_now:
            blockers.add("grant_expired")
        if binding is not None:
            if grant.binding_generation != binding.generation:
                blockers.add("grant_generation_mismatch")
            if (
                binding.attestation is not None
                and grant.attestation_revision > binding.attestation.revision
            ):
                blockers.add("grant_attestation_revision_mismatch")
            if (
                binding.attestation is not None
                and grant.policy_revision
                != binding.attestation.permission_revision
            ):
                blockers.add("grant_policy_revision_mismatch")
    ordered = [code for code in BLOCKER_ORDER if code in blockers]
    return EffectiveHostAdmissionProjection(
        admitted=not ordered,
        workspace_id=workspace_id,
        binding_id=binding.binding_id if binding else None,
        binding_generation=binding.generation if binding else None,
        operation=operation,
        grant_id=grant.grant_id if grant else None,
        attestation_revision=(
            binding.attestation.revision
            if binding and binding.attestation
            else None
        ),
        policy_revision=grant.policy_revision if grant else None,
        blockers=ordered,
    )
