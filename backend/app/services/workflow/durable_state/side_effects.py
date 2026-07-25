"""Immutable side-effect receipts used only through the durable facade."""

from __future__ import annotations

import json

from sqlalchemy import text

from .canonical_json import encode
from .contracts.v1.validator import validate_contract


def _record_side_effect(conn, signer, payload: dict) -> dict:
    unsigned = {key: value for key, value in payload.items() if key != "signature"}
    signature = signer.sign(encode(unsigned))
    signed = {**unsigned, "signature": signature.value}
    validate_contract("side_effect_receipt", signed)
    conn.execute(
        text(
            """
            INSERT INTO durable_workflow_side_effect_receipts (
                receipt_id, workflow_id, effect_id, effect_type, owner,
                request_hash, response_hash, adapter_id, adapter_version,
                status, replay_disposition, attempt, payload,
                key_id, signature, recorded_at
            ) VALUES (
                :receipt_id, :workflow_id, :effect_id, :effect_type, :owner,
                :request_hash, :response_hash, :adapter_id, :adapter_version,
                :status, :replay_disposition, :attempt, CAST(:payload AS JSONB),
                :key_id, :signature, :recorded_at
            )
            """
        ),
        {
            **signed,
            "response_hash": signed.get("response_hash"),
            "payload": json.dumps(signed, separators=(",", ":"), sort_keys=True),
            "key_id": signature.key_id,
        },
    )
    return signed
