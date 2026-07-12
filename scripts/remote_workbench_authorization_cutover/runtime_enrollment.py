"""Signed enrollment discovery for the Remote Workbench cutover."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from .io import CutoverError
from .secure_inputs import EXPECTED_ADMIN_EMAILS, SecureInputs


def _event_time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def validate_enrollment_candidates(
    audit: Mapping[str, Any],
    *,
    inputs: SecureInputs,
    workspace_id: str,
    started_at: datetime,
) -> None:
    """Match exactly one signed-origin candidate to each approved administrator."""

    events = audit.get("events")
    if not isinstance(events, list):
        raise CutoverError("Enrollment audit response is malformed")
    expected = {
        item["email"]: item["subject"]
        for item in inputs.policy["local_core_super_admins"]
    }
    claims_by_email = {
        str(claims.get("email") or "").lower(): claims
        for claims in inputs.jwt_claims.values()
    }
    candidates: dict[str, list[Mapping[str, Any]]] = {
        email: [] for email in EXPECTED_ADMIN_EMAILS
    }
    outsider = inputs.jwt_claims["outsider"]
    outsider_email = str(outsider.get("email") or "").lower()
    outsider_subject = str(outsider.get("sub") or "")
    for event in events:
        if not isinstance(event, Mapping):
            continue
        timestamp = _event_time(event.get("timestamp"))
        if timestamp is None or timestamp < started_at:
            continue
        if event.get("workspace_id") != workspace_id:
            continue
        if event.get("reason_code") != "remote_access_enrollment_only":
            continue
        candidate = event.get("subject_candidate")
        if candidate is None:
            continue
        if not isinstance(candidate, Mapping):
            raise CutoverError("Enrollment subject candidate is malformed")
        email = str(candidate.get("email") or "").lower()
        subject = str(candidate.get("subject") or "")
        if email == outsider_email or subject == outsider_subject:
            raise CutoverError("Outsider unexpectedly produced an enrollment candidate")
        if email not in candidates:
            raise CutoverError("Enrollment audit contains an unknown candidate")
        candidates[email].append(candidate)
    for email in EXPECTED_ADMIN_EMAILS:
        matches = candidates[email]
        if len(matches) != 1:
            raise CutoverError("Enrollment candidate is missing or ambiguous")
        candidate = matches[0]
        claims = claims_by_email[email]
        if (
            candidate.get("issuer") != claims.get("iss")
            or candidate.get("issuer") != inputs.policy["access_issuer"]
            or candidate.get("subject") != claims.get("sub")
            or candidate.get("subject") != expected[email]
            or str(candidate.get("email") or "").lower() != email
        ):
            raise CutoverError("Enrollment candidate does not match signed evidence")


def verify_enrollment_assertions(
    runtime: Any,
    inputs: SecureInputs,
    workspace_id: str,
) -> None:
    """Prove identity verification while enrollment state denies data access."""

    started_at = datetime.now(timezone.utc)
    for path in inputs.jwt_paths.values():
        response = runtime._principal_request(  # noqa: SLF001 - canonical facade
            path,
            workspace_id,
            upgrade=False,
        )
        runtime._assert_principal_response(  # noqa: SLF001
            response,
            allowed=False,
            expected_reason="remote_access_enrollment_only",
            upgrade=False,
        )
    audit = runtime.http.get_json(
        f"{runtime.audit_url}?workspace_id={workspace_id}&origin_type=public_host&limit=20",
        timeout_seconds=5.0,
        max_response_bytes=262_144,
    )
    validate_enrollment_candidates(
        audit,
        inputs=inputs,
        workspace_id=workspace_id,
        started_at=started_at,
    )
