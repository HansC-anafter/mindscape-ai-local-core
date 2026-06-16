"""Artifact provenance gate for host runtime terminal states."""

from __future__ import annotations

from typing import Any


def build_artifact_provenance_ref(
    *,
    workspace_id: str,
    session_id: str,
    turn_id: str,
    artifact_ref: dict[str, Any] | None,
) -> dict[str, Any]:
    ref = dict(artifact_ref or {})
    ref.setdefault("workspace_id", workspace_id)
    ref.setdefault("session_id", session_id)
    ref.setdefault("turn_id", turn_id)
    ref.setdefault("source", "host_runtime_session_gateway")
    return ref


def requires_artifact_provenance(event_type: str, payload: dict[str, Any]) -> bool:
    return event_type == "turn.completed" and bool(
        payload.get("patches") or payload.get("files") or payload.get("artifacts")
    )
