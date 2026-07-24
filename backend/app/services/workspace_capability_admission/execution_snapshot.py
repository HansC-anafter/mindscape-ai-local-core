"""Canonical construction and hashing for immutable admission snapshots."""

from __future__ import annotations

from hashlib import sha256
import json
from typing import Any

from .contracts import ExecutionAdmissionSnapshot


MAX_SNAPSHOT_BYTES = 64 * 1024


def canonical_snapshot_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def build_execution_snapshot(
    payload: dict[str, Any],
) -> ExecutionAdmissionSnapshot:
    unsigned = {
        **payload,
        "media_type": (
            "application/vnd.mindscape."
            "execution-admission-snapshot.v1+json"
        ),
        "schema_version": "mindscape.execution-admission-snapshot.v1",
    }
    normalized = ExecutionAdmissionSnapshot.model_validate(
        {**unsigned, "snapshot_hash": "0" * 64}
    ).model_dump(mode="json")
    normalized.pop("snapshot_hash")
    encoded = canonical_snapshot_bytes(normalized)
    if len(encoded) > MAX_SNAPSHOT_BYTES:
        raise ValueError("execution_admission_snapshot_too_large")
    return ExecutionAdmissionSnapshot.model_validate(
        {
            **normalized,
            "snapshot_hash": sha256(encoded).hexdigest(),
        }
    )


def verify_execution_snapshot_hash(
    snapshot: ExecutionAdmissionSnapshot,
) -> None:
    payload = snapshot.model_dump(mode="json")
    expected = payload.pop("snapshot_hash")
    encoded = canonical_snapshot_bytes(payload)
    if len(encoded) > MAX_SNAPSHOT_BYTES:
        raise ValueError("execution_admission_snapshot_too_large")
    if sha256(encoded).hexdigest() != expected:
        raise ValueError("execution_admission_snapshot_hash_mismatch")
