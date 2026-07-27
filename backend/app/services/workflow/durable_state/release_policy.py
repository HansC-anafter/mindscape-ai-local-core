"""Caller-transaction release-policy reads and exact owner-signed CAS."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import text

from .canonical_json import encode
from .runtime_owner_receipts import (
    VerifiedOwnerDecision,
    verify_owner_decision,
)


class DurableReleasePolicyConflict(RuntimeError):
    """Raised when a signed CAS does not match the immutable current row."""

    def __init__(self, *, expected_revision: int, actual_revision: int):
        super().__init__("durable_release_policy_revision_conflict")
        self.expected_revision = expected_revision
        self.actual_revision = actual_revision


class DurableReleasePolicyInvalid(ValueError):
    """Raised when signed receipt relationships are not exact."""


@dataclass(frozen=True)
class DurableReleasePolicy:
    workspace_id: str
    workflow_kind: str
    revision: int
    supersedes_revision: int | None
    mode: str
    policy: dict[str, Any]
    policy_hash: str
    owner_receipt: dict[str, Any] | None
    canary_receipt: dict[str, Any] | None
    owner_receipt_id: str | None
    owner_receipt_sha256: str | None
    trusted_key_registry_revision: str | None
    trusted_key_registry_sha256: str | None
    key_id: str
    signature: str
    created_by: str
    created_at: datetime

    @property
    def has_process_signature(self) -> bool:
        return all(
            (
                self.owner_receipt_id,
                self.owner_receipt,
                self.canary_receipt,
                self.owner_receipt_sha256,
                self.trusted_key_registry_revision,
                self.trusted_key_registry_sha256,
            )
        )


class DurableReleasePolicyStore:
    """Persistence leaf that never creates or commits a transaction."""

    _COLUMNS = """
        workspace_id, workflow_kind, revision, supersedes_revision, mode,
        policy, policy_hash, owner_receipt, canary_receipt, owner_receipt_id,
        owner_receipt_sha256,
        trusted_key_registry_revision, trusted_key_registry_sha256,
        key_id, signature, created_by, created_at
    """

    def read_current(
        self,
        conn,
        *,
        workspace_id: str,
        workflow_kind: str,
        for_update: bool = False,
    ) -> DurableReleasePolicy | None:
        lock = " FOR UPDATE" if for_update else ""
        row = conn.execute(
            text(
                f"""
                SELECT {self._COLUMNS}
                FROM durable_workflow_release_policies
                WHERE workspace_id = :workspace_id
                  AND workflow_kind = :workflow_kind
                ORDER BY revision DESC
                LIMIT 1{lock}
                """
            ),
            {
                "workspace_id": workspace_id,
                "workflow_kind": workflow_kind,
            },
        ).mappings().one_or_none()
        return self._from_row(row) if row is not None else None

    def compare_and_swap(
        self,
        conn,
        *,
        cas_receipt: dict[str, Any],
        canary_receipt: dict[str, Any],
        trusted_registry: dict[str, Any],
        expected_registry_sha256: str,
        now: datetime | None = None,
    ) -> DurableReleasePolicy:
        """Verify both owner decisions and append one immutable policy row."""

        cas = verify_owner_decision(
            cas_receipt,
            trusted_registry,
            expected_registry_sha256=expected_registry_sha256,
            now=now,
        )
        canary = verify_owner_decision(
            canary_receipt,
            trusted_registry,
            expected_registry_sha256=expected_registry_sha256,
            now=now,
        )
        self._validate_receipt_relationship(cas=cas, canary=canary)
        payload = cas.receipt["payload"]
        policy = payload["policy"]
        workspace_id = payload["workspace_id"]
        workflow_kind = payload["workflow_kind"]
        expected_revision = int(payload["expected_revision"])
        target_revision = int(payload["target_revision"])

        current = self.read_current(
            conn,
            workspace_id=workspace_id,
            workflow_kind=workflow_kind,
            for_update=True,
        )
        actual_revision = current.revision if current is not None else 0
        actual_mode = current.mode if current is not None else "absent"
        if actual_revision != expected_revision:
            raise DurableReleasePolicyConflict(
                expected_revision=expected_revision,
                actual_revision=actual_revision,
            )
        if actual_mode != payload["from_mode"]:
            raise DurableReleasePolicyInvalid(
                "durable_release_policy_from_mode_mismatch"
            )

        params = {
            "workspace_id": workspace_id,
            "workflow_kind": workflow_kind,
            "revision": target_revision,
            "supersedes_revision": (
                expected_revision if expected_revision > 0 else None
            ),
            "mode": payload["to_mode"],
            "policy": json.dumps(
                policy,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ),
            "policy_hash": payload["policy_hash"],
            "owner_receipt": json.dumps(
                cas.receipt,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ),
            "canary_receipt": json.dumps(
                canary.receipt,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ),
            "owner_receipt_id": cas.receipt_id,
            "owner_receipt_sha256": cas.receipt_sha256,
            "trusted_key_registry_revision": cas.registry_revision,
            "trusted_key_registry_sha256": cas.registry_sha256,
            "key_id": cas.key_id,
            "signature": cas.receipt["signature"],
            "created_by": cas.owner_id,
            "created_at": datetime.fromisoformat(
                cas.receipt["issued_at"].replace("Z", "+00:00")
            ),
        }
        inserted = conn.execute(
            text(
                f"""
                INSERT INTO durable_workflow_release_policies (
                    {self._COLUMNS}
                ) VALUES (
                    :workspace_id, :workflow_kind, :revision,
                    :supersedes_revision, :mode, CAST(:policy AS JSONB),
                    :policy_hash, CAST(:owner_receipt AS JSONB),
                    CAST(:canary_receipt AS JSONB),
                    :owner_receipt_id, :owner_receipt_sha256,
                    :trusted_key_registry_revision,
                    :trusted_key_registry_sha256, :key_id, :signature,
                    :created_by, :created_at
                )
                ON CONFLICT (workspace_id, workflow_kind, revision)
                DO NOTHING
                RETURNING {self._COLUMNS}
                """
            ),
            params,
        ).mappings().one_or_none()
        if inserted is None:
            concurrent = self.read_current(
                conn,
                workspace_id=workspace_id,
                workflow_kind=workflow_kind,
                for_update=True,
            )
            raise DurableReleasePolicyConflict(
                expected_revision=expected_revision,
                actual_revision=(
                    concurrent.revision if concurrent is not None else 0
                ),
            )
        return self._from_row(inserted)

    def verify_process_signature(
        self,
        policy: DurableReleasePolicy,
        *,
        trusted_registry: dict[str, Any],
        expected_registry_sha256: str,
        now: datetime | None = None,
    ) -> tuple[VerifiedOwnerDecision, VerifiedOwnerDecision]:
        """Re-verify the signed CAS and canary bytes persisted in PostgreSQL."""

        if (
            not policy.has_process_signature
            or policy.owner_receipt is None
            or policy.canary_receipt is None
        ):
            raise DurableReleasePolicyInvalid(
                "durable_release_policy_process_signature_missing"
            )
        cas = verify_owner_decision(
            policy.owner_receipt,
            trusted_registry,
            expected_registry_sha256=expected_registry_sha256,
            now=now,
        )
        canary = verify_owner_decision(
            policy.canary_receipt,
            trusted_registry,
            expected_registry_sha256=expected_registry_sha256,
            now=now,
        )
        self._validate_receipt_relationship(cas=cas, canary=canary)
        payload = cas.receipt["payload"]
        exact = {
            "durable_release_policy_workspace_readback_mismatch": (
                payload["workspace_id"] == policy.workspace_id
            ),
            "durable_release_policy_kind_readback_mismatch": (
                payload["workflow_kind"] == policy.workflow_kind
            ),
            "durable_release_policy_revision_readback_mismatch": (
                payload["target_revision"] == policy.revision
            ),
            "durable_release_policy_supersedes_readback_mismatch": (
                policy.supersedes_revision
                == (
                    payload["expected_revision"]
                    if payload["expected_revision"] > 0
                    else None
                )
            ),
            "durable_release_policy_mode_readback_mismatch": (
                payload["to_mode"] == policy.mode
            ),
            "durable_release_policy_document_readback_mismatch": (
                encode(payload["policy"]) == encode(policy.policy)
            ),
            "durable_release_policy_hash_readback_mismatch": (
                payload["policy_hash"] == policy.policy_hash
            ),
            "durable_release_policy_receipt_id_readback_mismatch": (
                cas.receipt_id == policy.owner_receipt_id
            ),
            "durable_release_policy_receipt_hash_readback_mismatch": (
                cas.receipt_sha256 == policy.owner_receipt_sha256
            ),
            "durable_release_policy_registry_revision_readback_mismatch": (
                cas.registry_revision
                == policy.trusted_key_registry_revision
            ),
            "durable_release_policy_registry_hash_readback_mismatch": (
                cas.registry_sha256 == policy.trusted_key_registry_sha256
            ),
            "durable_release_policy_key_readback_mismatch": (
                cas.key_id == policy.key_id
            ),
            "durable_release_policy_signature_readback_mismatch": (
                cas.receipt["signature"] == policy.signature
            ),
            "durable_release_policy_owner_readback_mismatch": (
                cas.owner_id == policy.created_by
            ),
        }
        for error, matches_exactly in exact.items():
            if not matches_exactly:
                raise DurableReleasePolicyInvalid(error)
        return cas, canary

    @staticmethod
    def _validate_receipt_relationship(
        *,
        cas: VerifiedOwnerDecision,
        canary: VerifiedOwnerDecision,
    ) -> None:
        if cas.receipt_type != "durable_release_policy_cas":
            raise DurableReleasePolicyInvalid(
                "durable_release_policy_cas_receipt_required"
            )
        if canary.receipt_type != "exact_canary_admission":
            raise DurableReleasePolicyInvalid(
                "exact_canary_admission_receipt_required"
            )
        payload = cas.receipt["payload"]
        policy = payload["policy"]
        if payload["cas_authority_id"] != cas.owner_id:
            raise DurableReleasePolicyInvalid(
                "durable_release_policy_cas_authority_mismatch"
            )
        if policy["canary_receipt_id"] != canary.receipt_id:
            raise DurableReleasePolicyInvalid(
                "durable_release_policy_canary_receipt_id_mismatch"
            )
        if policy["canary_receipt_sha256"] != canary.receipt_sha256:
            raise DurableReleasePolicyInvalid(
                "durable_release_policy_canary_receipt_hash_mismatch"
            )
        if encode(policy["canary"]) != encode(canary.receipt["payload"]):
            raise DurableReleasePolicyInvalid(
                "durable_release_policy_canary_payload_mismatch"
            )

    @staticmethod
    def _from_row(row) -> DurableReleasePolicy:
        value = dict(row)
        return DurableReleasePolicy(
            workspace_id=str(value["workspace_id"]),
            workflow_kind=str(value["workflow_kind"]),
            revision=int(value["revision"]),
            supersedes_revision=(
                int(value["supersedes_revision"])
                if value["supersedes_revision"] is not None
                else None
            ),
            mode=str(value["mode"]),
            policy=dict(value["policy"]),
            policy_hash=str(value["policy_hash"]),
            owner_receipt=(
                dict(value["owner_receipt"])
                if value["owner_receipt"] is not None
                else None
            ),
            canary_receipt=(
                dict(value["canary_receipt"])
                if value["canary_receipt"] is not None
                else None
            ),
            owner_receipt_id=value["owner_receipt_id"],
            owner_receipt_sha256=value["owner_receipt_sha256"],
            trusted_key_registry_revision=value[
                "trusted_key_registry_revision"
            ],
            trusted_key_registry_sha256=value["trusted_key_registry_sha256"],
            key_id=str(value["key_id"]),
            signature=str(value["signature"]),
            created_by=str(value["created_by"]),
            created_at=value["created_at"],
        )
