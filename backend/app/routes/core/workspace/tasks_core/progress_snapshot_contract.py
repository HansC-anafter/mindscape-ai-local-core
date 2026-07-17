"""Stable degraded-state and payload budget contract for progress snapshots."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi.encoders import jsonable_encoder


PROGRESS_SNAPSHOT_SCHEMA_VERSION = "2"
PROGRESS_SNAPSHOT_MAX_BYTES = 15 * 1024
PROGRESS_LAST_KNOWN_TTL_SECONDS = 60 * 60

_PROGRESS_SUMMARY_KEYS = (
    "status",
    "state",
    "phase",
    "percent",
    "completed",
    "total",
    "message",
    "updated_at",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _encoded_size(payload: dict[str, Any]) -> int:
    return len(
        json.dumps(
            jsonable_encoder(payload),
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    )


def fresh_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    next_payload = dict(payload)
    next_payload.update(
        {
            "stale": False,
            "captured_at": _now_iso(),
            "source": "postgres_compact_projection",
            "schema_version": PROGRESS_SNAPSHOT_SCHEMA_VERSION,
        }
    )
    return enforce_progress_snapshot_budget(next_payload)


def stale_snapshot(
    payload: dict[str, Any],
    *,
    degraded_reason: str,
) -> dict[str, Any]:
    next_payload = dict(payload)
    next_payload.update(
        {
            "stale": True,
            "degraded_reason": degraded_reason,
            "source": "last_known_snapshot",
            "schema_version": PROGRESS_SNAPSHOT_SCHEMA_VERSION,
        }
    )
    return enforce_progress_snapshot_budget(next_payload)


def enforce_progress_snapshot_budget(
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Replace oversized optional detail with explicit detail pointers."""

    encoded = jsonable_encoder(payload)
    if not isinstance(encoded, dict):
        raise ValueError("progress_snapshot_must_be_object")
    if _encoded_size(encoded) <= PROGRESS_SNAPSHOT_MAX_BYTES:
        return encoded

    compact = dict(encoded)
    omitted: list[str] = []
    for key in ("artifact_metadata", "content_metadata"):
        if compact.get(key):
            compact[key] = None
            omitted.append(key)

    progress = compact.get("progress")
    if isinstance(progress, dict):
        progress_summary = {
            key: progress[key]
            for key in _PROGRESS_SUMMARY_KEYS
            if key in progress
        }
        if progress_summary != progress:
            compact["progress"] = progress_summary or None
            omitted.append("progress_detail")

    if omitted:
        compact["detail_pointers"] = {
            key: f"execution:{compact.get('execution_id')}:{key}"
            for key in omitted
        }
    if _encoded_size(compact) > PROGRESS_SNAPSHOT_MAX_BYTES:
        raise ValueError("progress_snapshot_payload_budget_exceeded")
    return compact
