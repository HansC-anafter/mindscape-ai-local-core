"""Canonical decision-payload seam for workflow gate resume."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from typing import Any

from jsonschema import Draft202012Validator

MAX_DECISION_PAYLOAD_BYTES = 1024 * 1024


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def build_approved_gate_decision(
    *,
    comment: str | None,
    decision_payload: dict[str, Any] | None,
    decision_payload_schema: dict[str, Any] | None,
    decided_at: str,
) -> dict[str, Any]:
    """Build one bounded approval decision and bind any structured payload."""
    decision: dict[str, Any] = {
        "action": "approved",
        "comment": comment,
        "decided_at": decided_at,
    }
    if decision_payload is None:
        if decision_payload_schema is not None:
            raise ValueError("gate_decision_payload_required")
        return decision
    encoded = _canonical_bytes(decision_payload)
    if not decision_payload or len(encoded) > MAX_DECISION_PAYLOAD_BYTES:
        raise ValueError("gate_decision_payload_invalid")
    if decision_payload_schema is not None:
        try:
            Draft202012Validator.check_schema(decision_payload_schema)
            Draft202012Validator(decision_payload_schema).validate(
                decision_payload
            )
        except Exception as exc:
            raise ValueError(
                "gate_decision_payload_schema_mismatch"
            ) from exc
    decision["payload"] = deepcopy(decision_payload)
    decision["payload_sha256"] = hashlib.sha256(encoded).hexdigest()
    return decision
