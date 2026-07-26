"""Short-lived HMAC envelope for Local Core to Device Node execution."""

from __future__ import annotations

from hashlib import sha256
import hmac
import json

from .contracts import (
    HostRuntimeExecutionPermit,
    HostRuntimeExecutionPermitClaims,
)


def sign_execution_permit(
    claims: HostRuntimeExecutionPermitClaims,
    *,
    secret: str,
) -> HostRuntimeExecutionPermit:
    key = _secret_bytes(secret)
    signature = hmac.new(key, _canonical_bytes(claims), sha256).hexdigest()
    return HostRuntimeExecutionPermit(claims=claims, signature=signature)


def verify_execution_permit(
    permit: HostRuntimeExecutionPermit,
    *,
    secret: str,
) -> None:
    expected = hmac.new(
        _secret_bytes(secret),
        _canonical_bytes(permit.claims),
        sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, permit.signature):
        raise ValueError("host_execution_permit_signature_invalid")


def _canonical_bytes(claims: HostRuntimeExecutionPermitClaims) -> bytes:
    return json.dumps(
        claims.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _secret_bytes(secret: str) -> bytes:
    value = secret.encode("utf-8")
    if len(value) < 32:
        raise ValueError("host_execution_permit_secret_unavailable")
    return value
