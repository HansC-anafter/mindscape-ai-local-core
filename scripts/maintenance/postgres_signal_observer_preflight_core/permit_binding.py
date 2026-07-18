"""Payload-free incident admission and receipt binding for observer permits."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from backend.app.services.runtime_database_incident_core.journal import (
    IncidentJournalUnavailable,
    RuntimeDatabaseIncidentJournal,
)
from backend.app.services.runtime_database_incident_core.models import IncidentState


QUALIFICATION_SCHEMA = "mindscape.postgres-signal-observer-qualification.v2"
OWNERSHIP_REQUEST_SCHEMA = "mindscape.postgres-signal-observer-ownership-request.v2"
OWNERSHIP_GRANT_SCHEMA = "mindscape.postgres-signal-observer-ownership-grant.v1"
OBSERVER_OWNER = "runtime-db-incident-owner"
OWNERSHIP_SCOPE = (
    "canonical disposable isolated PostgreSQL/PgBouncer/client/observer "
    "sender-attribution drill, fixed resource/privacy budgets, sender-target "
    "correlation, and terminal cleanup/readback only"
)
OWNERSHIP_EXCLUSIONS = (
    "live_postgresql",
    "live_pgbouncer",
    "runners",
    "backend",
    "control",
    "frontend",
    "reload_restart_config",
    "queue_pool_capacity",
    "v52_media_model",
)
ADMISSION_FAILURES = (
    "journal_unavailable",
    "current_missing",
    "state_invalid",
    "permit_conflict",
)
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def _read_receipt(path: Path) -> tuple[dict[str, Any], str]:
    try:
        encoded = path.read_bytes()
        payload = json.loads(encoded)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("diagnostic_receipt_unavailable") from exc
    if type(payload) is not dict:
        raise ValueError("diagnostic_receipt_invalid")
    return payload, hashlib.sha256(encoded).hexdigest()


def _exact_text(value: object, failure: str) -> str:
    if type(value) is not str or not value.strip():
        raise ValueError(failure)
    return value.strip()


def _exact_sha256(value: object, failure: str) -> str:
    exact = _exact_text(value, failure)
    if not _SHA256_PATTERN.fullmatch(exact):
        raise ValueError(failure)
    return exact


def _active_diagnostic_permit(permit: object) -> bool:
    if permit is None:
        return False
    if not isinstance(permit, Mapping):
        return True
    expires_at = permit.get("expires_at")
    if type(expires_at) is not str:
        return True
    try:
        parsed = datetime.fromisoformat(expires_at.strip().replace("Z", "+00:00"))
    except ValueError:
        return True
    if parsed.tzinfo is None:
        return True
    return parsed > datetime.now(timezone.utc)


def _admission_projection(
    *,
    allowed: bool,
    failure_code: str | None,
    incident_id: str | None,
    state: str | None,
    conflicting_permit: bool,
) -> dict[str, Any]:
    return {
        "schema_version": "mindscape.postgres-signal-observer-permit-admission.v1",
        "allowed": allowed,
        "failure_code": failure_code,
        "incident_id": incident_id,
        "state": state,
        "conflicting_permit": conflicting_permit,
        "payload_persisted": False,
    }


def diagnostic_permit_admission(journal_root: Path) -> dict[str, Any]:
    """Project only the identity/state required before an ownership request."""

    try:
        current = RuntimeDatabaseIncidentJournal(journal_root).current()
    except IncidentJournalUnavailable:
        return _admission_projection(
            allowed=False,
            failure_code="journal_unavailable",
            incident_id=None,
            state=None,
            conflicting_permit=False,
        )
    if current is None:
        return _admission_projection(
            allowed=False,
            failure_code="current_missing",
            incident_id=None,
            state=None,
            conflicting_permit=False,
        )
    incident_id = _exact_text(current.incident_id, "current_missing")
    active_permit = _active_diagnostic_permit(current.diagnostic_permit)
    if current.state is not IncidentState.OPEN_UNATTRIBUTED:
        return _admission_projection(
            allowed=False,
            failure_code="state_invalid",
            incident_id=incident_id,
            state=current.state.value,
            conflicting_permit=active_permit,
        )
    if active_permit:
        return _admission_projection(
            allowed=False,
            failure_code="permit_conflict",
            incident_id=incident_id,
            state=current.state.value,
            conflicting_permit=True,
        )
    return _admission_projection(
        allowed=True,
        failure_code=None,
        incident_id=incident_id,
        state=current.state.value,
        conflicting_permit=False,
    )


def build_ownership_request(
    qualification: Mapping[str, Any],
    *,
    qualification_receipt_sha256: str,
    exact_operation: str,
    issued_at: str,
    expires_at: str,
    requested_owner: str,
) -> dict[str, Any]:
    """Build the sole requested-not-granted schema from one passing receipt."""

    if qualification.get("schema_version") != QUALIFICATION_SCHEMA:
        raise ValueError("qualification_schema_invalid")
    if qualification.get("phase") != "qualification":
        raise ValueError("qualification_phase_invalid")
    if qualification.get("gate_pass") is not True:
        raise ValueError("qualification_gate_not_passed")
    if qualification.get("first_failure") is not None:
        raise ValueError("qualification_failure_state_invalid")
    if qualification.get("failures") != []:
        raise ValueError("qualification_failures_invalid")
    if qualification.get("scope") != "postgres_signal_observer_only":
        raise ValueError("qualification_scope_invalid")
    if qualification.get("ownership_scope") != "postgres_signal_observer_only":
        raise ValueError("qualification_ownership_scope_invalid")
    if qualification.get("owner") != OBSERVER_OWNER:
        raise ValueError("qualification_owner_invalid")
    if qualification.get("mutation_permit") is not False:
        raise ValueError("qualification_mutation_permit_invalid")
    if qualification.get("quiet_window_owned") is not False:
        raise ValueError("qualification_quiet_window_invalid")
    checks = qualification.get("checks")
    if type(checks) is not dict:
        raise ValueError("qualification_checks_invalid")
    admission = checks.get("diagnostic_permit_admission")
    if type(admission) is not dict or admission.get("allowed") is not True:
        raise ValueError("qualification_admission_not_passed")
    expected_admission = _admission_projection(
        allowed=True,
        failure_code=None,
        incident_id=admission.get("incident_id"),
        state=IncidentState.OPEN_UNATTRIBUTED.value,
        conflicting_permit=False,
    )
    if admission != expected_admission:
        raise ValueError("qualification_admission_invalid")
    incident_id = _exact_text(admission.get("incident_id"), "qualification_incident_id_missing")
    if qualification.get("incident_id") != incident_id:
        raise ValueError("qualification_incident_id_mismatch")
    artifact_sha256 = _exact_sha256(
        qualification.get("artifact_sha256"), "qualification_artifact_sha256_invalid"
    )
    expected_operation = f"postgres_signal_observer_start@sha256:{artifact_sha256}"
    if _exact_text(exact_operation, "exact_operation_missing") != expected_operation:
        raise ValueError("ownership_operation_mismatch")
    exact_owner = _exact_text(requested_owner, "requested_owner_missing")
    if exact_owner != qualification.get("owner"):
        raise ValueError("requested_owner_invalid")
    return {
        "schema_version": OWNERSHIP_REQUEST_SCHEMA,
        "state": "requested_not_granted",
        "requested_owner": exact_owner,
        "qualification_receipt_sha256": _exact_sha256(
            qualification_receipt_sha256, "qualification_receipt_sha256_invalid"
        ),
        "incident_id": incident_id,
        "artifact_sha256": artifact_sha256,
        "exact_operation": expected_operation,
        "issued_at": _exact_text(issued_at, "ownership_issued_at_missing"),
        "expires_at": _exact_text(expires_at, "ownership_expires_at_missing"),
        "scope": OWNERSHIP_SCOPE,
        "explicit_exclusions": list(OWNERSHIP_EXCLUSIONS),
    }


def build_ownership_grant(
    request: Mapping[str, Any],
    *,
    ownership_request_receipt_sha256: str,
    granted_owner: str,
) -> dict[str, Any]:
    """Bind an explicit grant to the exact requested incident and receipts."""

    if request.get("schema_version") != OWNERSHIP_REQUEST_SCHEMA:
        raise ValueError("ownership_request_schema_invalid")
    if request.get("state") != "requested_not_granted":
        raise ValueError("ownership_request_state_invalid")
    exact_owner = _exact_text(granted_owner, "granted_owner_missing")
    if request.get("requested_owner") != exact_owner:
        raise ValueError("ownership_granted_owner_mismatch")
    if request.get("scope") != OWNERSHIP_SCOPE:
        raise ValueError("ownership_scope_invalid")
    if request.get("explicit_exclusions") != list(OWNERSHIP_EXCLUSIONS):
        raise ValueError("ownership_exclusions_invalid")
    return {
        "schema_version": OWNERSHIP_GRANT_SCHEMA,
        "state": "granted",
        "granted_owner": exact_owner,
        "qualification_receipt_sha256": _exact_sha256(
            request.get("qualification_receipt_sha256"),
            "qualification_receipt_sha256_invalid",
        ),
        "ownership_request_receipt_sha256": _exact_sha256(
            ownership_request_receipt_sha256,
            "ownership_request_receipt_sha256_invalid",
        ),
        "incident_id": _exact_text(request.get("incident_id"), "request_incident_id_missing"),
        "artifact_sha256": _exact_sha256(
            request.get("artifact_sha256"), "request_artifact_sha256_invalid"
        ),
        "exact_operation": _exact_text(request.get("exact_operation"), "request_operation_missing"),
        "issued_at": _exact_text(request.get("issued_at"), "request_issued_at_missing"),
        "expires_at": _exact_text(request.get("expires_at"), "request_expires_at_missing"),
        "scope": OWNERSHIP_SCOPE,
        "explicit_exclusions": list(OWNERSHIP_EXCLUSIONS),
    }


def receipt_bound_incident_id(
    *,
    qualification_path: Path,
    ownership_request_path: Path,
    ownership_grant_path: Path,
    artifact_sha256: str,
    owner: str,
    expires_at: str,
) -> str:
    """Validate all three immutable receipts before returning one incident ID."""

    qualification, qualification_sha256 = _read_receipt(qualification_path)
    request, request_sha256 = _read_receipt(ownership_request_path)
    grant, _grant_sha256 = _read_receipt(ownership_grant_path)
    expected_request = build_ownership_request(
        qualification,
        qualification_receipt_sha256=qualification_sha256,
        exact_operation=request.get("exact_operation"),
        issued_at=request.get("issued_at"),
        expires_at=request.get("expires_at"),
        requested_owner=request.get("requested_owner"),
    )
    if request != expected_request:
        raise ValueError("ownership_request_receipt_invalid")
    expected_grant = build_ownership_grant(
        request,
        ownership_request_receipt_sha256=request_sha256,
        granted_owner=owner,
    )
    if grant != expected_grant:
        raise ValueError("ownership_grant_receipt_invalid")
    if request["artifact_sha256"] != _exact_sha256(
        artifact_sha256, "diagnostic_artifact_sha256_invalid"
    ):
        raise ValueError("diagnostic_artifact_sha256_mismatch")
    if request["expires_at"] != _exact_text(
        expires_at, "diagnostic_expires_at_missing"
    ):
        raise ValueError("diagnostic_expires_at_mismatch")
    return request["incident_id"]
