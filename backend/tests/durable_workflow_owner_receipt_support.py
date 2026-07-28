"""Signed neutral owner-receipt fixtures for durable workflow tests."""

from __future__ import annotations

import base64
import hashlib
from datetime import datetime, timezone

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.services.workflow.durable_state.canonical_json import encode

H = "0" * 64
H1 = "1" * 64
NOW = datetime(2026, 7, 26, 10, 0, tzinfo=timezone.utc)


class OwnerReceiptFactory:
    def __init__(self) -> None:
        self._canary_key = Ed25519PrivateKey.generate()
        self._cas_key = Ed25519PrivateKey.generate()
        self.registry = {
            "schema_id": (
                "mindscape.durable-workflow-runtime-owner-trusted-keys.v1"
            ),
            "registry_revision": "trusted-keys:r1",
            "keys": [
                self._trusted_key(
                    key=self._canary_key,
                    key_id="key:canary",
                    owner_id="owner:canary",
                    owner_role="runtime_canary_owner",
                    receipt_type="exact_canary_admission",
                    authority_ref="authority/canary/r1",
                    revocation_ref="authority/canary/revocations",
                ),
                self._trusted_key(
                    key=self._cas_key,
                    key_id="key:cas",
                    owner_id="owner:cas",
                    owner_role="runtime_release_owner",
                    receipt_type="durable_release_policy_cas",
                    authority_ref="authority/release-policy/r1",
                    revocation_ref="authority/release-policy/revocations",
                ),
            ],
        }
        self.registry_sha256 = hashlib.sha256(
            encode(self.registry, max_bytes=4 * 1024 * 1024)
        ).hexdigest()

    def canary(
        self,
        *,
        workspace_id: str = "workspace:policy",
        authorization_scopes: list[str] | None = None,
        backout_owner_id: str = "owner:backout",
    ) -> dict:
        payload = {
            "workspace_id": workspace_id,
            "authorization_scopes": authorization_scopes or [
                "durable_workflow:shadow",
                "durable_workflow:enforced",
                "durable_workflow:disable",
            ],
            "pilot_cohort_hash": H,
            "window": {
                "starts_at": "2026-07-26T09:00:00Z",
                "ends_at": "2026-07-26T12:00:00Z",
            },
            "backout_owner_id": backout_owner_id,
            "candidate_attestations": [
                {
                    "attestation_id": "attestation:candidate",
                    "attestation_sha256": H,
                }
            ],
            "fixture_descriptors": [
                {
                    "descriptor_id": "descriptor:alpha",
                    "descriptor_hash": H,
                },
                {
                    "descriptor_id": "descriptor:beta",
                    "descriptor_hash": H1,
                },
            ],
        }
        return self._receipt(
            key=self._canary_key,
            key_id="key:canary",
            receipt_id="receipt:canary",
            receipt_type="exact_canary_admission",
            decision_revision="canary:r1",
            owner_id="owner:canary",
            owner_role="runtime_canary_owner",
            authority_ref="authority/canary/r1",
            revocation_ref="authority/canary/revocations",
            payload=payload,
        )

    def cas(
        self,
        canary_receipt: dict,
        *,
        workflow_kind: str = "execution",
        expected_revision: int = 0,
        from_mode: str = "absent",
        to_mode: str = "shadow",
        receipt_id: str | None = None,
        cas_authority_id: str = "owner:cas",
    ) -> dict:
        workspace_id = canary_receipt["payload"]["workspace_id"]
        resolved_receipt_id = receipt_id or (
            f"receipt:cas:{workspace_id}:{expected_revision + 1}"
        )
        policy = {
            "schema_id": "mindscape.durable-workflow-release-policy.v1",
            "workspace_id": workspace_id,
            "workflow_kind": workflow_kind,
            "mode": to_mode,
            "canary_receipt_id": canary_receipt["receipt_id"],
            "canary_receipt_sha256": hashlib.sha256(
                encode(canary_receipt, max_bytes=64 * 1024)
            ).hexdigest(),
            "canary": canary_receipt["payload"],
        }
        payload = {
            "workspace_id": workspace_id,
            "workflow_kind": workflow_kind,
            "expected_revision": expected_revision,
            "target_revision": expected_revision + 1,
            "from_mode": from_mode,
            "to_mode": to_mode,
            "policy": policy,
            "policy_hash": hashlib.sha256(encode(policy)).hexdigest(),
            "cas_authority_id": cas_authority_id,
        }
        return self._receipt(
            key=self._cas_key,
            key_id="key:cas",
            receipt_id=resolved_receipt_id,
            receipt_type="durable_release_policy_cas",
            decision_revision=f"policy:r{expected_revision + 1}",
            owner_id="owner:cas",
            owner_role="runtime_release_owner",
            authority_ref="authority/release-policy/r1",
            revocation_ref="authority/release-policy/revocations",
            payload=payload,
        )

    @staticmethod
    def _trusted_key(
        *,
        key: Ed25519PrivateKey,
        key_id: str,
        owner_id: str,
        owner_role: str,
        receipt_type: str,
        authority_ref: str,
        revocation_ref: str,
    ) -> dict:
        public = key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        return {
            "key_id": key_id,
            "owner_id": owner_id,
            "owner_role": owner_role,
            "authorized_receipt_types": [receipt_type],
            "authority_refs": [authority_ref],
            "revocation_ref": revocation_ref,
            "public_key_base64": base64.b64encode(public).decode("ascii"),
            "fingerprint_sha256": hashlib.sha256(public).hexdigest(),
            "not_before": "2026-07-01T00:00:00Z",
            "not_after": "2027-07-01T00:00:00Z",
            "revoked_at": None,
        }

    @staticmethod
    def _receipt(
        *,
        key: Ed25519PrivateKey,
        key_id: str,
        receipt_id: str,
        receipt_type: str,
        decision_revision: str,
        owner_id: str,
        owner_role: str,
        authority_ref: str,
        revocation_ref: str,
        payload: dict,
    ) -> dict:
        public = key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        receipt = {
            "schema_id": (
                "mindscape.durable-workflow-runtime-owner-decision-receipt.v1"
            ),
            "receipt_id": receipt_id,
            "receipt_type": receipt_type,
            "contract_id": "mindscape.durable-product-semantic-workflow.v1",
            "decision_revision": decision_revision,
            "owner_id": owner_id,
            "owner_role": owner_role,
            "authority_ref": authority_ref,
            "issued_at": "2026-07-26T09:55:00Z",
            "expires_at": "2026-07-27T09:55:00Z",
            "revocation_ref": revocation_ref,
            "payload": payload,
            "payload_sha256": hashlib.sha256(
                encode(payload, max_bytes=64 * 1024)
            ).hexdigest(),
            "key_id": key_id,
            "public_key_fingerprint_sha256": hashlib.sha256(
                public
            ).hexdigest(),
        }
        receipt["signature"] = base64.b64encode(
            key.sign(encode(receipt, max_bytes=64 * 1024))
        ).decode("ascii")
        return receipt
