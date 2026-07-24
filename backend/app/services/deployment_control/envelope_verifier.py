"""Canonical Ed25519 verification for portable deployment envelopes."""

from __future__ import annotations

import base64
from datetime import datetime, timezone
from hashlib import sha256
import json

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .contracts import SignedDeploymentCapabilityEnvelope
from .errors import (
    DeploymentEnvelopeExpired,
    DeploymentEnvelopeInvalid,
    DeploymentEnvelopeNotYetValid,
)
from .trust_store import DeploymentTrustStore


MAX_ENVELOPE_BYTES = 64 * 1024


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
    except (ValueError, TypeError) as exc:
        raise DeploymentEnvelopeInvalid(
            "deployment_envelope_base64_invalid"
        ) from exc


def envelope_hash(envelope: SignedDeploymentCapabilityEnvelope) -> str:
    return sha256(
        canonical_json_bytes(envelope.model_dump(mode="json"))
    ).hexdigest()


class DeploymentEnvelopeVerifier:
    def __init__(self, trust_store: DeploymentTrustStore):
        self.trust_store = trust_store

    def verify(
        self,
        envelope: SignedDeploymentCapabilityEnvelope,
        *,
        expected_audience: str,
        expected_source_runtime_id: str,
        expected_catalog_hash: str,
        now: datetime | None = None,
    ) -> str:
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            raise DeploymentEnvelopeInvalid("verification_time_requires_timezone")
        encoded = canonical_json_bytes(envelope.model_dump(mode="json"))
        if len(encoded) > MAX_ENVELOPE_BYTES:
            raise DeploymentEnvelopeInvalid("deployment_envelope_too_large")

        claims = envelope.claims
        for value in (claims.issued_at, claims.not_before, claims.expires_at):
            if value.tzinfo is None:
                raise DeploymentEnvelopeInvalid(
                    "deployment_envelope_timestamp_requires_timezone"
                )
        if claims.issued_at > claims.not_before:
            raise DeploymentEnvelopeInvalid(
                "deployment_envelope_issued_after_not_before"
            )
        if claims.not_before >= claims.expires_at:
            raise DeploymentEnvelopeInvalid(
                "deployment_envelope_time_window_invalid"
            )
        if current < claims.not_before:
            raise DeploymentEnvelopeNotYetValid()
        if current >= claims.expires_at:
            raise DeploymentEnvelopeExpired()
        if claims.audience != expected_audience:
            raise DeploymentEnvelopeInvalid("deployment_envelope_wrong_audience")
        if claims.source_runtime_id != expected_source_runtime_id:
            raise DeploymentEnvelopeInvalid(
                "deployment_envelope_wrong_source_runtime"
            )
        if claims.catalog_hash != expected_catalog_hash:
            raise DeploymentEnvelopeInvalid(
                "deployment_envelope_wrong_catalog"
            )

        root = self.trust_store.resolve(
            issuer=claims.issuer,
            kid=envelope.kid,
            alg=envelope.alg,
            now=current,
        )
        public_key = _decode_base64url(root.public_key)
        signature = _decode_base64url(envelope.signature)
        if len(public_key) != 32 or len(signature) != 64:
            raise DeploymentEnvelopeInvalid(
                "deployment_envelope_key_or_signature_size_invalid"
            )
        try:
            Ed25519PublicKey.from_public_bytes(public_key).verify(
                signature,
                canonical_json_bytes(claims.model_dump(mode="json")),
            )
        except (InvalidSignature, ValueError) as exc:
            raise DeploymentEnvelopeInvalid(
                "deployment_envelope_signature_invalid"
            ) from exc
        return sha256(encoded).hexdigest()
