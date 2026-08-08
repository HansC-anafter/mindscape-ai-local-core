"""Neutral admission adapter for owner-signed durable workflow policy."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..workflow.durable_state.release_policy import (
    DurableReleasePolicy,
    DurableReleasePolicyInvalid,
    DurableReleasePolicyStore,
)
from ..workflow.durable_state.runtime_owner_receipts import (
    RuntimeOwnerReceiptError,
)


class DurableWorkflowAdmissionUnavailable(RuntimeError):
    """Raised when a persisted release policy cannot be re-verified."""


@dataclass(frozen=True)
class DurableWorkflowAdmissionDecision:
    mode: str
    revision: int
    policy_hash: str | None
    canary_receipt_id: str | None
    pilot_cohort_hash: str | None
    authorization_scopes: tuple[str, ...]
    candidate_attestations: tuple[tuple[str, str], ...]
    fixture_descriptors: tuple[tuple[str, str], ...]
    backout_owner_id: str | None
    window_starts_at: str | None
    window_ends_at: str | None

    @property
    def shadow_enabled(self) -> bool:
        return self.mode == "shadow"

    @property
    def enforced(self) -> bool:
        return self.mode == "enforced"


class DurableWorkflowPolicyAdapter:
    """Resolve only exact neutral fields from a re-verified policy row."""

    def __init__(
        self,
        *,
        policy_store: DurableReleasePolicyStore | None = None,
    ) -> None:
        self._policies = policy_store or DurableReleasePolicyStore()

    def evaluate(
        self,
        *,
        policy: DurableReleasePolicy | None,
        workspace_id: str,
        workflow_kind: str,
        trusted_registry: dict[str, Any],
        expected_registry_sha256: str,
        now: datetime | None = None,
    ) -> DurableWorkflowAdmissionDecision:
        if policy is None:
            return DurableWorkflowAdmissionDecision(
                mode="disabled",
                revision=0,
                policy_hash=None,
                canary_receipt_id=None,
                pilot_cohort_hash=None,
                authorization_scopes=(),
                candidate_attestations=(),
                fixture_descriptors=(),
                backout_owner_id=None,
                window_starts_at=None,
                window_ends_at=None,
            )
        if policy.workspace_id != workspace_id:
            raise DurableWorkflowAdmissionUnavailable(
                "durable_workflow_policy_workspace_mismatch"
            )
        if policy.workflow_kind != workflow_kind:
            raise DurableWorkflowAdmissionUnavailable(
                "durable_workflow_policy_kind_mismatch"
            )
        try:
            self._policies.verify_process_signature(
                policy,
                trusted_registry=trusted_registry,
                expected_registry_sha256=expected_registry_sha256,
                now=now,
            )
        except (DurableReleasePolicyInvalid, RuntimeOwnerReceiptError) as exc:
            raise DurableWorkflowAdmissionUnavailable(str(exc)) from exc

        document = policy.policy
        canary = document["canary"]
        return DurableWorkflowAdmissionDecision(
            mode=policy.mode,
            revision=policy.revision,
            policy_hash=policy.policy_hash,
            canary_receipt_id=document["canary_receipt_id"],
            pilot_cohort_hash=canary["pilot_cohort_hash"],
            authorization_scopes=tuple(canary["authorization_scopes"]),
            candidate_attestations=tuple(
                (
                    item["attestation_id"],
                    item["attestation_sha256"],
                )
                for item in canary["candidate_attestations"]
            ),
            fixture_descriptors=tuple(
                (item["descriptor_id"], item["descriptor_hash"])
                for item in canary["fixture_descriptors"]
            ),
            backout_owner_id=canary["backout_owner_id"],
            window_starts_at=canary["window"]["starts_at"],
            window_ends_at=canary["window"]["ends_at"],
        )
