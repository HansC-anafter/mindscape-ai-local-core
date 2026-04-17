from __future__ import annotations

from typing import Any, Dict, Optional

from backend.app.services.orchestration.meeting.spatial_scheduling_compiler import (
    merge_spatial_schedule_context,
    normalize_spatial_schedule_context,
)


SPATIAL_SCHEDULE_ARTIFACT_MIME = "application/vnd.mindscape.spatial-scheduling+json"


def _as_dict(value: Any) -> Dict[str, Any]:
    return dict(value or {}) if isinstance(value, dict) else {}


def resolve_spatial_schedule_summary(
    *,
    workspace_metadata: Optional[Dict[str, Any]] = None,
    meeting_session_payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    normalized_workspace = normalize_spatial_schedule_context(
        _as_dict(_as_dict(workspace_metadata).get("spatial_schedule_context"))
    )

    normalized_session = None
    if meeting_session_payload:
        session_metadata = _as_dict(meeting_session_payload.get("metadata"))
        normalized_session = normalize_spatial_schedule_context(
            _as_dict(session_metadata.get("spatial_schedule_context"))
        )

    merged = merge_spatial_schedule_context(
        existing=normalized_workspace,
        incoming=normalized_session,
    )
    return dict(merged or normalized_workspace or normalized_session or {})


def resolve_spatial_schedule_artifact_ref(summary: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    normalized_summary = normalize_spatial_schedule_context(_as_dict(summary))
    if not normalized_summary:
        return {}

    artifact_ref = _as_dict(normalized_summary.get("artifact_ref"))
    artifact_id = str(artifact_ref.get("artifact_id") or "").strip()
    if not artifact_id:
        return {}

    return {
        "artifact_id": artifact_id,
        "artifact_type": str(
            artifact_ref.get("type") or SPATIAL_SCHEDULE_ARTIFACT_MIME
        ),
    }


__all__ = [
    "SPATIAL_SCHEDULE_ARTIFACT_MIME",
    "resolve_spatial_schedule_artifact_ref",
    "resolve_spatial_schedule_summary",
]
