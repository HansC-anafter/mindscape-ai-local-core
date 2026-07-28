"""Fail-closed verification for runtime owner decision receipts."""

from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .canonical_json import encode
from .contracts.v1 import ContractValidationError, validate_contract

MAX_FUTURE_SKEW = timedelta(minutes=5)
MAX_RECEIPT_BYTES = 64 * 1024
MAX_REGISTRY_BYTES = 4 * 1024 * 1024
POLICY_TRANSITIONS = {
    ("absent", "shadow"),
    ("disabled", "shadow"),
    ("shadow", "enforced"),
    ("shadow", "disabled"),
    ("enforced", "shadow"),
    ("enforced", "disabled"),
}
POLICY_MODE_AUTHORIZATION_SCOPE = {
    "shadow": "durable_workflow:shadow",
    "enforced": "durable_workflow:enforced",
    "disabled": "durable_workflow:disable",
}
RPO_DATA_CLASSES = {
    "ledger_metadata",
    "object_evidence",
    "signing_verification_material",
    "contract_mirror_registry",
    "projection",
}


class RuntimeOwnerReceiptError(ValueError):
    """Raised when a runtime owner decision is not exactly trusted."""


@dataclass(frozen=True)
class VerifiedOwnerDecision:
    receipt: dict[str, Any]
    receipt_sha256: str
    registry_revision: str
    registry_sha256: str
    checked_at: datetime

    @property
    def receipt_id(self) -> str:
        return str(self.receipt["receipt_id"])

    @property
    def receipt_type(self) -> str:
        return str(self.receipt["receipt_type"])

    @property
    def owner_id(self) -> str:
        return str(self.receipt["owner_id"])

    @property
    def key_id(self) -> str:
        return str(self.receipt["key_id"])


def _timestamp(value: str, *, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise RuntimeOwnerReceiptError(f"{field}_invalid") from exc
    if parsed.tzinfo is None:
        raise RuntimeOwnerReceiptError(f"{field}_timezone_required")
    return parsed.astimezone(timezone.utc)


def _canonical_sha256(value: Any, *, max_bytes: int) -> str:
    return hashlib.sha256(encode(value, max_bytes=max_bytes)).hexdigest()


def _validate_registry(registry: dict[str, Any]) -> None:
    keys = registry["keys"]
    key_ids = [item["key_id"] for item in keys]
    fingerprints = [item["fingerprint_sha256"] for item in keys]
    if len(key_ids) != len(set(key_ids)):
        raise RuntimeOwnerReceiptError("trusted_key_id_duplicate")
    if len(fingerprints) != len(set(fingerprints)):
        raise RuntimeOwnerReceiptError("trusted_key_fingerprint_duplicate")
    for key in keys:
        not_before = _timestamp(key["not_before"], field="key_not_before")
        not_after = _timestamp(key["not_after"], field="key_not_after")
        if not_after <= not_before:
            raise RuntimeOwnerReceiptError("trusted_key_validity_window_invalid")
        if key["revoked_at"] is not None:
            revoked_at = _timestamp(key["revoked_at"], field="revoked_at")
            if revoked_at < not_before:
                raise RuntimeOwnerReceiptError(
                    "trusted_key_revocation_before_validity"
                )


def _trusted_key(
    receipt: dict[str, Any], registry: dict[str, Any]
) -> dict[str, Any]:
    matches = [
        item for item in registry["keys"] if item["key_id"] == receipt["key_id"]
    ]
    if len(matches) != 1:
        raise RuntimeOwnerReceiptError("trusted_key_not_unique")
    key = matches[0]
    exact_matches = {
        "trusted_key_owner_mismatch": key["owner_id"] == receipt["owner_id"],
        "trusted_key_role_mismatch": key["owner_role"] == receipt["owner_role"],
        "trusted_key_fingerprint_receipt_mismatch": (
            key["fingerprint_sha256"]
            == receipt["public_key_fingerprint_sha256"]
        ),
        "trusted_key_receipt_type_unauthorized": (
            receipt["receipt_type"] in key["authorized_receipt_types"]
        ),
        "trusted_key_authority_ref_unauthorized": (
            receipt["authority_ref"] in key["authority_refs"]
        ),
        "trusted_key_revocation_ref_mismatch": (
            receipt["revocation_ref"] == key["revocation_ref"]
        ),
    }
    for error, matches_exactly in exact_matches.items():
        if not matches_exactly:
            raise RuntimeOwnerReceiptError(error)
    return key


def _validate_payload(receipt: dict[str, Any], *, checked_at: datetime) -> None:
    receipt_type = receipt["receipt_type"]
    payload = receipt["payload"]
    if receipt_type == "exact_canary_admission":
        starts_at = _timestamp(
            payload["window"]["starts_at"], field="canary_starts_at"
        )
        ends_at = _timestamp(
            payload["window"]["ends_at"], field="canary_ends_at"
        )
        if ends_at <= starts_at:
            raise RuntimeOwnerReceiptError("canary_window_invalid")
        if checked_at < starts_at:
            raise RuntimeOwnerReceiptError("canary_window_not_started")
        if checked_at >= ends_at:
            raise RuntimeOwnerReceiptError("canary_window_expired")
        attestation_ids = [
            item["attestation_id"] for item in payload["candidate_attestations"]
        ]
        if len(attestation_ids) != len(set(attestation_ids)):
            raise RuntimeOwnerReceiptError(
                "candidate_attestation_id_duplicate"
            )
        descriptors = payload["fixture_descriptors"]
        if len({item["descriptor_id"] for item in descriptors}) != 2:
            raise RuntimeOwnerReceiptError("fixture_descriptor_id_not_distinct")
        if len({item["descriptor_hash"] for item in descriptors}) != 2:
            raise RuntimeOwnerReceiptError(
                "fixture_descriptor_hash_not_distinct"
            )
    if receipt_type == "durable_release_policy_cas":
        expected = payload["expected_revision"]
        policy = payload["policy"]
        if payload["target_revision"] != expected + 1:
            raise RuntimeOwnerReceiptError(
                "policy_cas_revision_not_contiguous"
            )
        if (expected == 0) != (payload["from_mode"] == "absent"):
            raise RuntimeOwnerReceiptError(
                "policy_cas_absent_revision_mismatch"
            )
        transition = (payload["from_mode"], payload["to_mode"])
        if transition not in POLICY_TRANSITIONS:
            raise RuntimeOwnerReceiptError("policy_cas_transition_invalid")
        if policy["workspace_id"] != payload["workspace_id"]:
            raise RuntimeOwnerReceiptError("policy_cas_workspace_mismatch")
        if policy["workflow_kind"] != payload["workflow_kind"]:
            raise RuntimeOwnerReceiptError(
                "policy_cas_workflow_kind_mismatch"
            )
        if policy["mode"] != payload["to_mode"]:
            raise RuntimeOwnerReceiptError("policy_cas_mode_mismatch")
        policy_sha256 = _canonical_sha256(policy, max_bytes=16_384)
        if policy_sha256 != payload["policy_hash"]:
            raise RuntimeOwnerReceiptError("policy_cas_policy_hash_mismatch")
        required_scope = POLICY_MODE_AUTHORIZATION_SCOPE[payload["to_mode"]]
        if required_scope not in policy["canary"]["authorization_scopes"]:
            raise RuntimeOwnerReceiptError("policy_cas_scope_unauthorized")
        if payload["cas_authority_id"] != receipt["owner_id"]:
            raise RuntimeOwnerReceiptError("policy_cas_authority_mismatch")
        if (
            payload["to_mode"] == "disabled"
            and receipt["owner_id"] != policy["canary"]["backout_owner_id"]
        ):
            raise RuntimeOwnerReceiptError(
                "policy_cas_backout_owner_mismatch"
            )
    if receipt_type == "rpo_rto_policy":
        classes = {item["data_class"] for item in payload["data_classes"]}
        if classes != RPO_DATA_CLASSES:
            raise RuntimeOwnerReceiptError("rpo_rto_data_classes_not_exact")
    if receipt_type == "signing_key_provisioning":
        not_before = _timestamp(
            payload["not_before"], field="workflow_key_not_before"
        )
        not_after = _timestamp(
            payload["not_after"], field="workflow_key_not_after"
        )
        if not_after <= not_before:
            raise RuntimeOwnerReceiptError(
                "workflow_key_validity_window_invalid"
            )


def verify_owner_decision(
    receipt: dict[str, Any],
    registry: dict[str, Any],
    *,
    expected_registry_sha256: str,
    now: datetime | None = None,
) -> VerifiedOwnerDecision:
    """Verify one exact receipt against a caller-pinned trusted registry."""

    try:
        validate_contract("runtime_owner_decision_receipt", receipt)
        validate_contract("runtime_owner_trusted_keys", registry)
    except ContractValidationError as exc:
        raise RuntimeOwnerReceiptError("owner_contract_schema_invalid") from exc
    checked_at = now or datetime.now(timezone.utc)
    if checked_at.tzinfo is None:
        raise RuntimeOwnerReceiptError("verification_clock_timezone_required")
    checked_at = checked_at.astimezone(timezone.utc)
    registry_sha256 = _canonical_sha256(
        registry, max_bytes=MAX_REGISTRY_BYTES
    )
    if registry_sha256 != expected_registry_sha256:
        raise RuntimeOwnerReceiptError("trusted_key_registry_sha256_mismatch")
    _validate_registry(registry)
    _validate_payload(receipt, checked_at=checked_at)

    payload_sha256 = _canonical_sha256(
        receipt["payload"], max_bytes=MAX_RECEIPT_BYTES
    )
    if payload_sha256 != receipt["payload_sha256"]:
        raise RuntimeOwnerReceiptError("payload_sha256_mismatch")
    issued_at = _timestamp(receipt["issued_at"], field="issued_at")
    expires_at = _timestamp(receipt["expires_at"], field="expires_at")
    if issued_at > checked_at + MAX_FUTURE_SKEW:
        raise RuntimeOwnerReceiptError("receipt_issued_in_future")
    if expires_at <= issued_at:
        raise RuntimeOwnerReceiptError("receipt_validity_window_invalid")
    if checked_at >= expires_at:
        raise RuntimeOwnerReceiptError("receipt_expired")

    key = _trusted_key(receipt, registry)
    key_not_before = _timestamp(key["not_before"], field="key_not_before")
    key_not_after = _timestamp(key["not_after"], field="key_not_after")
    if not key_not_before <= issued_at < key_not_after:
        raise RuntimeOwnerReceiptError("receipt_issued_outside_key_window")
    if checked_at >= key_not_after:
        raise RuntimeOwnerReceiptError("trusted_key_expired")
    if key["revoked_at"] is not None:
        revoked_at = _timestamp(key["revoked_at"], field="revoked_at")
        if issued_at >= revoked_at or checked_at >= revoked_at:
            raise RuntimeOwnerReceiptError("trusted_key_revoked")

    try:
        public_key_raw = base64.b64decode(
            key["public_key_base64"], validate=True
        )
    except ValueError as exc:
        raise RuntimeOwnerReceiptError(
            "trusted_public_key_base64_invalid"
        ) from exc
    if len(public_key_raw) != 32:
        raise RuntimeOwnerReceiptError("trusted_public_key_length_invalid")
    if hashlib.sha256(public_key_raw).hexdigest() != key["fingerprint_sha256"]:
        raise RuntimeOwnerReceiptError("trusted_key_fingerprint_invalid")
    try:
        signature = base64.b64decode(receipt["signature"], validate=True)
        signed = dict(receipt)
        signed.pop("signature")
        Ed25519PublicKey.from_public_bytes(public_key_raw).verify(
            signature,
            encode(signed, max_bytes=MAX_RECEIPT_BYTES),
        )
    except (ValueError, InvalidSignature) as exc:
        raise RuntimeOwnerReceiptError("signature_invalid") from exc

    return VerifiedOwnerDecision(
        receipt=receipt,
        receipt_sha256=_canonical_sha256(
            receipt, max_bytes=MAX_RECEIPT_BYTES
        ),
        registry_revision=str(registry["registry_revision"]),
        registry_sha256=registry_sha256,
        checked_at=checked_at,
    )
