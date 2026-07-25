"""Canonical event construction and bounded chain verification."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from .canonical_json import chained_hash, encode, sha256_hex
from .signature import Ed25519Signer, verify


def build_signed_event(
    signer: Ed25519Signer,
    *,
    locked: dict[str, Any],
    event_type: str,
    actor: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    occurred_at = datetime.now(timezone.utc)
    core = {
        "event_id": str(uuid4()),
        "workflow_id": locked["workflow_id"],
        "segment_id": locked["segment_id"],
        "sequence": locked["current_sequence"] + 1,
        "event_type": event_type,
        "occurred_at": occurred_at.isoformat().replace("+00:00", "Z"),
        "actor": actor,
        "payload": payload,
        "payload_sha256": sha256_hex(payload),
        "previous_event_hash": locked["current_event_hash"],
        "critical_durability": "sync",
    }
    event_hash = chained_hash(locked["current_event_hash"], core)
    signed_content = {**core, "event_hash": event_hash}
    canonical_bytes = len(encode(signed_content))
    signature = signer.sign(encode(signed_content))
    return {
        **signed_content,
        "canonical_bytes": canonical_bytes,
        "key_id": signature.key_id,
        "signature": signature.value,
    }


def verify_events(
    events: list[dict[str, Any]], verification_keys: dict[str, Any]
) -> str | None:
    previous = events[0]["previous_event_hash"] if events else None
    for event in events:
        core = event_core_from_row(event)
        expected = chained_hash(previous, core)
        if event["previous_event_hash"] != previous or event["event_hash"] != expected:
            raise ValueError("durable event hash chain is invalid")
        public_key = verification_keys.get(event["key_id"])
        if public_key is None:
            raise ValueError(f"event signing key {event['key_id']!r} is unavailable")
        verify(
            public_key,
            encode({**core, "event_hash": event["event_hash"]}),
            event["signature"],
        )
        previous = event["event_hash"]
    return previous


def event_core_from_row(event: dict[str, Any]) -> dict[str, Any]:
    occurred_at = event["occurred_at"]
    if hasattr(occurred_at, "isoformat"):
        occurred_at = occurred_at.isoformat().replace("+00:00", "Z")
    return {
        "event_id": event["event_id"],
        "workflow_id": event["workflow_id"],
        "segment_id": event["segment_id"],
        "sequence": event["sequence"],
        "event_type": event["event_type"],
        "occurred_at": occurred_at,
        "actor": event["actor"],
        "payload": event["payload"],
        "payload_sha256": event["payload_sha256"],
        "previous_event_hash": event["previous_event_hash"],
        "critical_durability": "sync",
    }
