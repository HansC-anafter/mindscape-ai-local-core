"""Signed internal admission receipt for existing-lane outcome tasks."""

from __future__ import annotations

from typing import Any

from .canonical_json import encode, sha256_hex
from .signature import Ed25519Signer, SigningKeyError, verify


def build_outcome_task_admission(
    signer: Ed25519Signer,
    *,
    task_id: str,
    workspace_id: str,
    terminal_receipt_id: str,
    enrollment_id: str,
    iteration_id: str,
    descriptor_sha256: str,
    task_params: dict[str, Any],
) -> dict[str, Any]:
    unsigned = {
        "receipt_type": "product_outcome_evaluation_task_admission",
        "task_id": task_id,
        "workspace_id": workspace_id,
        "terminal_receipt_id": terminal_receipt_id,
        "enrollment_id": enrollment_id,
        "iteration_id": iteration_id,
        "descriptor_sha256": descriptor_sha256,
        "task_params_sha256": sha256_hex(task_params),
        "authorized_lane": "runner:existing",
        "key_id": signer.key_id,
    }
    signature = signer.sign(encode(unsigned))
    return {**unsigned, "signature": signature.value}


def verify_outcome_task_admission(
    receipt: Any,
    *,
    expected_task_id: str,
    expected_workspace_id: str,
    expected_params: dict[str, Any],
    verification_keys: dict[str, object],
) -> dict[str, Any]:
    if not isinstance(receipt, dict):
        raise ValueError("outcome_task_admission_required")
    expected = {
        "receipt_type": "product_outcome_evaluation_task_admission",
        "task_id": expected_task_id,
        "workspace_id": expected_workspace_id,
        "task_params_sha256": sha256_hex(expected_params),
        "authorized_lane": "runner:existing",
    }
    for field, value in expected.items():
        if receipt.get(field) != value:
            raise ValueError(f"outcome_task_admission_{field}_mismatch")
    public_key = verification_keys.get(str(receipt.get("key_id") or ""))
    if public_key is None:
        raise ValueError("outcome_task_admission_key_unavailable")
    try:
        verify(
            public_key,
            encode(
                {key: value for key, value in receipt.items() if key != "signature"}
            ),
            str(receipt.get("signature") or ""),
        )
    except SigningKeyError as exc:
        raise ValueError("outcome_task_admission_signature_invalid") from exc
    return dict(receipt)


__all__ = (
    "build_outcome_task_admission",
    "verify_outcome_task_admission",
)
