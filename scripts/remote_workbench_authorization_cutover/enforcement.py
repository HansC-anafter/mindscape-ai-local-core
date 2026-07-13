"""Shared enforced-policy projection and outsider grant checks."""

from __future__ import annotations

from typing import Any

from .io import CutoverError
from .secure_inputs import SecureInputs


def enforced_body(inputs: SecureInputs, revision: int) -> dict[str, Any]:
    """Build the one exact enforced policy transition body."""

    body = dict(inputs.policy)
    body["expected_revision"] = revision
    body["remote_access_state"] = "enforced"
    return body


def verify_outsider_zero_grant(
    inputs: SecureInputs,
    *effective_policies: dict[str, Any],
) -> None:
    """Require the signed outsider to remain absent from every effective grant."""

    outsider = inputs.jwt_claims.get("outsider")
    if outsider is None:
        raise CutoverError("Outsider assertion is required before enforcement")
    outsider_email = str(outsider.get("email") or "").strip().lower()
    outsider_subject = str(outsider.get("sub") or "").strip()
    for payload in effective_policies:
        principals = payload.get("effective_principals")
        admins = payload.get("local_core_super_admins")
        if not isinstance(principals, list) or not isinstance(admins, list):
            raise CutoverError("Effective policy grant projection is malformed")
        for row in [*principals, *admins]:
            if not isinstance(row, dict):
                raise CutoverError("Effective policy grant principal is malformed")
            if (
                str(row.get("email") or "").strip().lower() == outsider_email
                or str(row.get("subject") or "").strip() == outsider_subject
            ):
                raise CutoverError("Outsider unexpectedly has an effective grant")
