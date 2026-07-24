"""Verify CRS EED signature, expiry and exact Local Core request pins."""

from __future__ import annotations

import base64
from datetime import datetime, timezone
import json
import os

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .external_execution_contracts import (
    ExternalExecutionAuthorizationRequest,
    SignedExternalExecutionDecision,
)


MAX_EED_BYTES = 64 * 1024


class ExternalExecutionDecisionInvalid(RuntimeError):
    pass


class ExternalDecisionTrustRoot(BaseModel):
    issuer: str = Field(min_length=2, max_length=128)
    kid: str = Field(min_length=2, max_length=128)
    alg: str = Field(pattern="^EdDSA$")
    public_key: str = Field(min_length=40, max_length=128)
    not_before: datetime | None = None
    not_after: datetime | None = None

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @model_validator(mode="after")
    def validate_window(self):
        for value in (self.not_before, self.not_after):
            if value is not None and value.tzinfo is None:
                raise ValueError("eed_trust_root_requires_timezone")
        if (
            self.not_before is not None
            and self.not_after is not None
            and self.not_before >= self.not_after
        ):
            raise ValueError("eed_trust_root_window_invalid")
        return self


def canonical_json_bytes(payload: object) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _decode_base64url(value: str) -> bytes:
    try:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (TypeError, ValueError) as exc:
        raise ExternalExecutionDecisionInvalid(
            "eed_base64_invalid"
        ) from exc


class ExternalExecutionDecisionVerifier:
    ENV_NAME = "MINDSCAPE_CRS_EXTERNAL_DECISION_TRUST_ROOTS_JSON"

    def __init__(self, roots: list[ExternalDecisionTrustRoot]) -> None:
        identities = [(root.issuer, root.kid, root.alg) for root in roots]
        if len(identities) != len(set(identities)):
            raise ExternalExecutionDecisionInvalid(
                "duplicate_eed_trust_root"
            )
        self._roots = {
            (root.issuer, root.kid, root.alg): root for root in roots
        }

    @classmethod
    def from_environment(cls) -> "ExternalExecutionDecisionVerifier":
        try:
            payload = json.loads(os.getenv(cls.ENV_NAME, "[]"))
            if not isinstance(payload, list):
                raise ValueError("trust roots must be a list")
            roots = [
                ExternalDecisionTrustRoot.model_validate(item)
                for item in payload
            ]
        except (TypeError, ValueError) as exc:
            raise ExternalExecutionDecisionInvalid(
                "eed_trust_root_configuration_invalid"
            ) from exc
        return cls(roots)

    def verify(
        self,
        decision: SignedExternalExecutionDecision,
        *,
        request: ExternalExecutionAuthorizationRequest,
        now: datetime | None = None,
    ) -> None:
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            raise ExternalExecutionDecisionInvalid(
                "eed_verification_time_requires_timezone"
            )
        encoded = canonical_json_bytes(decision.model_dump(mode="json"))
        if len(encoded) > MAX_EED_BYTES:
            raise ExternalExecutionDecisionInvalid("eed_too_large")
        claims = decision.claims
        for value in (claims.issued_at, claims.expires_at):
            if value.tzinfo is None:
                raise ExternalExecutionDecisionInvalid(
                    "eed_timestamp_requires_timezone"
                )
        if claims.expires_at <= claims.issued_at:
            raise ExternalExecutionDecisionInvalid("eed_window_invalid")
        if current < claims.issued_at or current >= claims.expires_at:
            raise ExternalExecutionDecisionInvalid("eed_not_current")

        expected = {
            "audience": f"mindscape-local-core:{request.source_runtime_id}",
            "source_runtime_id": request.source_runtime_id,
            "workspace_id": request.workspace_id,
            "active_group_id": request.active_group_id,
            "topology_snapshot_id": request.topology_snapshot_id,
            "topology_snapshot_hash": request.topology_snapshot_hash,
            "wpcs_hash": request.wpcs_hash,
            "catalog_hash": request.catalog_hash,
            "product_surface_id": request.product_surface_id,
            "deployment_mode": request.deployment_mode,
            "dce_hash": request.dce_hash,
            "trace_id": request.trace_id,
            "root_execution_id": request.root_execution_id,
        }
        for field, value in expected.items():
            if getattr(claims, field) != value:
                raise ExternalExecutionDecisionInvalid(
                    f"eed_{field}_mismatch"
                )
        if (
            claims.exact_capability_closure
            != request.exact_capability_closure
            or claims.exact_pack_closure != request.exact_pack_closure
        ):
            raise ExternalExecutionDecisionInvalid("eed_closure_mismatch")

        root = self._roots.get((claims.issuer, decision.kid, decision.alg))
        if root is None:
            raise ExternalExecutionDecisionInvalid("eed_trust_root_unknown")
        if root.not_before is not None and current < root.not_before:
            raise ExternalExecutionDecisionInvalid(
                "eed_trust_root_not_yet_valid"
            )
        if root.not_after is not None and current >= root.not_after:
            raise ExternalExecutionDecisionInvalid(
                "eed_trust_root_expired"
            )
        public_key = _decode_base64url(root.public_key)
        signature = _decode_base64url(decision.signature)
        if len(public_key) != 32 or len(signature) != 64:
            raise ExternalExecutionDecisionInvalid(
                "eed_key_or_signature_size_invalid"
            )
        try:
            Ed25519PublicKey.from_public_bytes(public_key).verify(
                signature,
                canonical_json_bytes(claims.model_dump(mode="json")),
            )
        except (InvalidSignature, ValueError) as exc:
            raise ExternalExecutionDecisionInvalid(
                "eed_signature_invalid"
            ) from exc
