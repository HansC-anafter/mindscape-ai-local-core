"""Request, decision, and one-time consumption writers behind the facade."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import text

from .canonical_json import encode
from .contracts.v1.validator import validate_contract


def _sign(signer, payload: dict) -> tuple[dict, object]:
    unsigned = {key: value for key, value in payload.items() if key != "signature"}
    signature = signer.sign(encode(unsigned))
    signed = {**unsigned, "signature": signature.value}
    validate_contract("approval", signed)
    return signed, signature


def _request_approval(conn, signer, payload: dict) -> dict:
    signed, signature = _sign(signer, {**payload, "phase": "request"})
    conn.execute(
        text(
            """
            INSERT INTO durable_workflow_approval_requests (
                approval_id, workflow_id, interrupt_id, tool_call_id,
                action_hash, resume_payload_hash, requested_by,
                required_quorum, separation_of_duties, payload, expires_at,
                key_id, signature, created_at
            ) VALUES (
                :approval_id, :workflow_id, :interrupt_id, :tool_call_id,
                :action_hash, :resume_payload_hash, :requested_by,
                :required_quorum, :separation_of_duties,
                CAST(:payload AS JSONB), :expires_at,
                :key_id, :signature, :created_at
            )
            """
        ),
        {
            **signed,
            "required_quorum": signed.get("quorum", 1),
            "separation_of_duties": signed.get("separation_of_duties", False),
            "payload": json.dumps(signed, separators=(",", ":"), sort_keys=True),
            "key_id": signature.key_id,
        },
    )
    return signed


def _decide_approval(
    conn,
    signer,
    *,
    approval_id: str,
    decision_id: str,
    decided_by: str,
    decision: str,
    policy_version: str,
    created_at: str,
) -> dict:
    request = conn.execute(
        text(
            """
            SELECT *, expires_at > NOW() AS unexpired
            FROM durable_workflow_approval_requests
            WHERE approval_id = :approval_id
            FOR UPDATE
            """
        ),
        {"approval_id": approval_id},
    ).mappings().one()
    if not request["unexpired"]:
        raise ValueError("approval request is expired")
    if request["separation_of_duties"] and decided_by == request["requested_by"]:
        raise ValueError("approval decision violates separation of duties")
    base = dict(request["payload"])
    base.update(
        {
            "phase": "decision",
            "decided_by": decided_by,
            "decision": decision,
            "quorum": request["required_quorum"],
            "separation_of_duties": request["separation_of_duties"],
            "created_at": created_at,
        }
    )
    base.pop("signature", None)
    signed, signature = _sign(signer, base)
    conn.execute(
        text(
            """
            INSERT INTO durable_workflow_approval_decisions (
                decision_id, approval_id, decided_by, decision,
                policy_version, payload, key_id, signature, decided_at
            ) VALUES (
                :decision_id, :approval_id, :decided_by, :decision,
                :policy_version, CAST(:payload AS JSONB),
                :key_id, :signature, :decided_at
            )
            """
        ),
        {
            "decision_id": decision_id,
            "approval_id": approval_id,
            "decided_by": decided_by,
            "decision": decision,
            "policy_version": policy_version,
            "payload": json.dumps(signed, separators=(",", ":"), sort_keys=True),
            "key_id": signature.key_id,
            "signature": signature.value,
            "decided_at": created_at,
        },
    )
    return signed


def _consume_approval(
    conn,
    signer,
    *,
    approval_id: str,
    consumption_id: str,
    delivery_id: str,
    effect_or_transition_id: str,
    created_at: str,
) -> dict:
    request = conn.execute(
        text(
            """
            SELECT *, expires_at > NOW() AS unexpired
            FROM durable_workflow_approval_requests
            WHERE approval_id = :approval_id
            FOR UPDATE
            """
        ),
        {"approval_id": approval_id},
    ).mappings().one()
    decisions = conn.execute(
        text(
            """
            SELECT decision_id, decision
            FROM durable_workflow_approval_decisions
            WHERE approval_id = :approval_id
            ORDER BY decided_at, decision_id
            """
        ),
        {"approval_id": approval_id},
    ).mappings().all()
    approved = [row for row in decisions if row["decision"] == "approved"]
    if not request["unexpired"] or any(
        row["decision"] != "approved" for row in decisions
    ):
        raise ValueError("approval cannot be consumed")
    if len(approved) < request["required_quorum"]:
        raise ValueError("approval quorum is incomplete")
    base = dict(request["payload"])
    base.update(
        {
            "phase": "consumption",
            "decision_receipt_id": approved[-1]["decision_id"],
            "delivery_id": delivery_id,
            "consumed_effect_id": effect_or_transition_id,
            "created_at": created_at,
        }
    )
    base.pop("signature", None)
    signed, signature = _sign(signer, base)
    conn.execute(
        text(
            """
            INSERT INTO durable_workflow_approval_consumptions (
                consumption_id, approval_id, decision_id, delivery_id,
                effect_or_transition_id, payload, key_id, signature, consumed_at
            ) VALUES (
                :consumption_id, :approval_id, :decision_id, :delivery_id,
                :effect_or_transition_id, CAST(:payload AS JSONB),
                :key_id, :signature, :consumed_at
            )
            """
        ),
        {
            "consumption_id": consumption_id,
            "approval_id": approval_id,
            "decision_id": approved[-1]["decision_id"],
            "delivery_id": delivery_id,
            "effect_or_transition_id": effect_or_transition_id,
            "payload": json.dumps(signed, separators=(",", ":"), sort_keys=True),
            "key_id": signature.key_id,
            "signature": signature.value,
            "consumed_at": created_at,
        },
    )
    return signed


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
