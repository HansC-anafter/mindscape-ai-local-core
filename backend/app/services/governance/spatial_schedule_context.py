"""Spatial schedule context normalization and merge helpers."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping


def normalize_spatial_schedule_context(
    context: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(context, Mapping):
        return None

    result = dict(context)
    if "artifact_ref" not in result and result.get("source_artifact_id"):
        result["artifact_ref"] = {"artifact_id": result["source_artifact_id"]}

    active_segment_ids = result.get("active_segment_ids")
    if "active_segments" not in result and isinstance(active_segment_ids, list):
        result["active_segments"] = [
            {"segment_id": str(segment_id)}
            for segment_id in active_segment_ids
            if str(segment_id).strip()
        ]

    consumer_refs = result.get("consumer_refs")
    if "consumer_receipts" not in result and isinstance(consumer_refs, list):
        receipts: dict[str, dict[str, Any]] = {}
        for ref in consumer_refs:
            if not isinstance(ref, Mapping):
                continue
            consumer_code = str(ref.get("consumer_code") or "").strip()
            if not consumer_code:
                continue
            receipt: dict[str, Any] = {}
            if ref.get("status"):
                receipt["status"] = ref.get("status")
            if ref.get("receipt_artifact_id"):
                receipt["receipt_ref"] = {
                    "artifact_id": ref.get("receipt_artifact_id"),
                }
            receipts[consumer_code] = receipt
        if receipts:
            result["consumer_receipts"] = receipts

    return result


def merge_spatial_schedule_contexts(
    workspace_context: Mapping[str, Any] | None,
    session_context: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    workspace_normalized = normalize_spatial_schedule_context(workspace_context)
    session_normalized = normalize_spatial_schedule_context(session_context)

    if session_normalized is None:
        return workspace_normalized
    if workspace_normalized is None:
        return session_normalized

    workspace_schedule_id = workspace_normalized.get("schedule_id")
    session_schedule_id = session_normalized.get("schedule_id")
    if workspace_schedule_id == session_schedule_id:
        merged = {**workspace_normalized, **session_normalized}
        merged["consumer_receipts"] = {
            **dict(workspace_normalized.get("consumer_receipts") or {}),
            **dict(session_normalized.get("consumer_receipts") or {}),
        }
        return merged

    latest, previous = _choose_latest_context(
        workspace_normalized,
        session_normalized,
    )
    merged = dict(latest)
    revision_refs = list(merged.get("schedule_revision_refs") or [])
    previous_ref = _build_revision_ref(previous)
    if previous_ref:
        revision_refs.append(previous_ref)
    if revision_refs:
        merged["schedule_revision_refs"] = revision_refs
    return merged


def _choose_latest_context(
    workspace_context: dict[str, Any],
    session_context: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    workspace_updated_at = _parse_time(workspace_context.get("updated_at"))
    session_updated_at = _parse_time(session_context.get("updated_at"))
    if workspace_updated_at and session_updated_at:
        if session_updated_at >= workspace_updated_at:
            return session_context, workspace_context
        return workspace_context, session_context
    return session_context, workspace_context


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _build_revision_ref(context: Mapping[str, Any]) -> dict[str, Any] | None:
    schedule_id = context.get("schedule_id")
    if not schedule_id:
        return None
    ref: dict[str, Any] = {
        "schedule_id": schedule_id,
        "relation": "supersedes",
    }
    if context.get("artifact_ref"):
        ref["artifact_ref"] = context.get("artifact_ref")
    if context.get("updated_at"):
        ref["updated_at"] = context.get("updated_at")
    return ref
