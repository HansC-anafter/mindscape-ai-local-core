"""Canonical runtime database mutation decision evaluator."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Optional

from .journal import IncidentJournalUnavailable, RuntimeDatabaseIncidentJournal
from .models import IncidentState, MutationDecision, _parse_timestamp
from .mutation_context import current_mutation_evidence


class RuntimeDatabaseMutationBlocked(RuntimeError):
    """Raised when a high-risk mutation is blocked by the incident gate."""

    def __init__(self, decision: MutationDecision):
        self.decision = decision
        super().__init__(decision.reason)


class RuntimeDatabaseMutationGate:
    """Return one stable decision for every high-risk mutation caller."""

    def __init__(self, journal_root: Optional[Path] = None):
        self.journal = RuntimeDatabaseIncidentJournal(journal_root)

    @staticmethod
    def operation_key(
        operation: str,
        evidence: Optional[Mapping[str, str]] = None,
    ) -> str:
        operation_name = str(operation).strip() or "unspecified_mutation"
        if operation_name.startswith("capability_install_job:"):
            operation_name = "capability_install_job"
        merged = current_mutation_evidence()
        merged.update(
            {
                str(key): str(value).strip()
                for key, value in (evidence or {}).items()
                if value is not None and str(value).strip()
            }
        )
        artifact_sha256 = merged.get("artifact_sha256", "").lower()
        if artifact_sha256:
            return f"{operation_name}@sha256:{artifact_sha256}"
        return operation_name

    def evaluate(
        self,
        operation: str,
        evidence: Optional[Mapping[str, str]] = None,
    ) -> MutationDecision:
        operation_name = str(operation).strip() or "unspecified_mutation"
        try:
            current = self.journal.current()
        except IncidentJournalUnavailable:
            return MutationDecision(
                allowed=False,
                operation=operation_name,
                reason="incident_journal_unavailable",
            )
        if current is None or current.state is IncidentState.CLOSED:
            return MutationDecision(
                allowed=True,
                operation=operation_name,
                reason="allowed",
                retry_after_seconds=0,
            )
        operation_key = self.operation_key(operation_name, evidence)
        for permit in reversed(current.pack_install_permits):
            allowed_keys = set(permit.get("allowed_operation_keys") or ())
            if operation_key not in allowed_keys:
                continue
            expires_at = permit.get("expires_at")
            try:
                permit_active = bool(expires_at) and _parse_timestamp(
                    str(expires_at),
                    field_name="pack_install_permit_expires_at",
                ) > datetime.now(timezone.utc)
            except ValueError:
                permit_active = False
            if permit_active:
                return MutationDecision(
                    allowed=True,
                    operation=operation_name,
                    reason="owner_authorized_pack_install_permit",
                    incident_id=current.incident_id,
                    retry_after_seconds=0,
                    details={
                        "incident_state": current.state.value,
                        "permit_id": permit.get("permit_id"),
                        "operation_key": operation_key,
                        "capability_code": permit.get("capability_code"),
                        "candidate_version": permit.get("candidate_version"),
                    },
                )
            return MutationDecision(
                allowed=False,
                operation=operation_name,
                reason="pack_install_permit_expired",
                incident_id=current.incident_id,
                details={
                    "incident_state": current.state.value,
                    "permit_id": permit.get("permit_id"),
                    "operation_key": operation_key,
                },
            )
        for permit in reversed(current.targeted_migration_permits):
            if operation_key != str(permit.get("allowed_operation_key") or ""):
                continue
            expires_at = permit.get("expires_at")
            try:
                permit_active = bool(expires_at) and _parse_timestamp(
                    str(expires_at),
                    field_name="targeted_migration_permit_expires_at",
                ) > datetime.now(timezone.utc)
            except ValueError:
                permit_active = False
            if permit_active:
                return MutationDecision(
                    allowed=True,
                    operation=operation_name,
                    reason="owner_authorized_targeted_migration_permit",
                    incident_id=current.incident_id,
                    retry_after_seconds=0,
                    details={
                        "incident_state": current.state.value,
                        "permit_id": permit.get("permit_id"),
                        "operation_key": operation_key,
                        "revision": permit.get("revision"),
                        "migration_mode": permit.get("migration_mode"),
                    },
                )
            return MutationDecision(
                allowed=False,
                operation=operation_name,
                reason="targeted_migration_permit_expired",
                incident_id=current.incident_id,
                details={
                    "incident_state": current.state.value,
                    "permit_id": permit.get("permit_id"),
                    "operation_key": operation_key,
                },
            )
        if current.state is IncidentState.CONTAINED_PENDING_SOAK:
            containment = dict(current.containment_receipt or {})
            allowed_keys = set(containment.get("allowed_operation_keys") or ())
            expires_at = containment.get("expires_at")
            permit_active = False
            if expires_at:
                try:
                    permit_active = _parse_timestamp(
                        str(expires_at),
                        field_name="containment_expires_at",
                    ) > datetime.now(timezone.utc)
                except ValueError:
                    permit_active = False
            if permit_active and operation_key in allowed_keys:
                return MutationDecision(
                    allowed=True,
                    operation=operation_name,
                    reason="containment_repair_permit",
                    incident_id=current.incident_id,
                    retry_after_seconds=0,
                    details={
                        "incident_state": current.state.value,
                        "permit_id": containment.get("permit_id"),
                        "operation_key": operation_key,
                    },
                )
            return MutationDecision(
                allowed=False,
                operation=operation_name,
                reason=(
                    "containment_repair_permit_expired"
                    if expires_at and not permit_active
                    else "runtime_database_incident_contained"
                ),
                incident_id=current.incident_id,
                details={
                    "incident_state": current.state.value,
                    "permit_id": containment.get("permit_id"),
                    "operation_key": operation_key,
                },
            )
        return MutationDecision(
            allowed=False,
            operation=operation_name,
            reason="runtime_database_incident_open",
            incident_id=current.incident_id,
            details={"incident_state": current.state.value},
        )

    def require_allowed(
        self,
        operation: str,
        evidence: Optional[Mapping[str, str]] = None,
    ) -> MutationDecision:
        decision = self.evaluate(operation, evidence)
        if not decision.allowed:
            raise RuntimeDatabaseMutationBlocked(decision)
        return decision
