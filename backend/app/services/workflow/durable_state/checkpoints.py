"""Append-only checkpoint writer used only through the durable facade."""

from __future__ import annotations

import json

from sqlalchemy import text

from .canonical_json import encode
from .contracts.v1.validator import validate_contract


def _append_checkpoint(conn, signer, receipt: dict) -> dict:
    locked = conn.execute(
        text(
            """
            SELECT segment_id, current_sequence, current_event_hash, reducer_version
            FROM durable_workflow_instances
            WHERE workflow_id = :workflow_id
            FOR UPDATE
            """
        ),
        {"workflow_id": receipt["workflow_id"]},
    ).mappings().one()
    expected = {
        "segment_id": locked["segment_id"],
        "sequence": locked["current_sequence"],
        "event_hash": locked["current_event_hash"],
        "reducer_version": locked["reducer_version"],
    }
    for field_name, value in expected.items():
        if receipt.get(field_name) != value:
            raise ValueError(f"checkpoint {field_name} must equal locked aggregate")
    unsigned = {key: value for key, value in receipt.items() if key != "signature"}
    signature = signer.sign(encode(unsigned))
    signed = {**unsigned, "signature": signature.value}
    validate_contract("checkpoint", signed)
    parent_id = conn.execute(
        text(
            """
            SELECT checkpoint_id
            FROM durable_workflow_checkpoints
            WHERE workflow_id = :workflow_id
            ORDER BY sequence DESC
            LIMIT 1
            """
        ),
        {"workflow_id": receipt["workflow_id"]},
    ).scalar_one_or_none()
    conn.execute(
        text(
            """
            INSERT INTO durable_workflow_checkpoints (
                checkpoint_id, workflow_id, sequence, parent_checkpoint_id,
                state_hash, event_hash, reducer_version, payload,
                key_id, signature, created_at
            ) VALUES (
                :checkpoint_id, :workflow_id, :sequence, :parent_checkpoint_id,
                :state_hash, :event_hash, :reducer_version,
                CAST(:payload AS JSONB), :key_id, :signature, :created_at
            )
            """
        ),
        {
            "checkpoint_id": signed["checkpoint_id"],
            "workflow_id": signed["workflow_id"],
            "sequence": signed["sequence"],
            "parent_checkpoint_id": parent_id,
            "state_hash": signed["state_hash"],
            "event_hash": signed["event_hash"],
            "reducer_version": signed["reducer_version"],
            "payload": json.dumps(signed, separators=(",", ":"), sort_keys=True),
            "key_id": signature.key_id,
            "signature": signature.value,
            "created_at": signed["committed_at"],
        },
    )
    return signed


def _list_checkpoints(conn, workflow_id: str, cursor: int, limit: int) -> list[dict]:
    if not 1 <= limit <= 50:
        raise ValueError("checkpoint page limit must be between 1 and 50")
    return [
        dict(row)
        for row in conn.execute(
            text(
                """
                SELECT payload
                FROM durable_workflow_checkpoints
                WHERE workflow_id = :workflow_id AND sequence > :cursor
                ORDER BY sequence
                LIMIT :limit
                """
            ),
            {"workflow_id": workflow_id, "cursor": cursor, "limit": limit},
        ).scalars()
    ]
