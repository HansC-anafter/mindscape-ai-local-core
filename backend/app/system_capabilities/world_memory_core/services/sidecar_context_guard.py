from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional


def _parse_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if not isinstance(value, str):
        return None

    raw = value.strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _normalize_motion_artifact_refs(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []

    normalized: List[Dict[str, Any]] = []
    for item in value:
        if hasattr(item, "model_dump"):
            item = item.model_dump(mode="json")
        if isinstance(item, dict) and item:
            normalized.append(dict(item))
    return normalized


def _normalize_performance_state(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    normalized: Dict[str, Any] = {}
    for key in (
        "context_version",
        "storyboard_id",
        "scene_id",
        "performance_mode",
        "execution_bridge",
        "preview_ready_state",
        "face_lane_active",
        "face_source_type",
        "body_lane_active",
        "body_source_type",
        "retarget_ready_state",
    ):
        if value.get(key) is not None:
            normalized[key] = value.get(key)
    return normalized


def derive_active_motion(motion_context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    active_motion = motion_context.get("active_motion")
    if isinstance(active_motion, dict) and active_motion:
        return dict(active_motion)

    fallback = {
        key: motion_context.get(key)
        for key in (
            "motion_id",
            "provider",
            "source_family",
            "status",
            "duration_sec",
            "fps",
            "skeleton_family",
            "skeleton_version",
            "coordinate_space",
            "retarget_profile",
        )
        if motion_context.get(key) is not None
    }
    return fallback or None


def derive_motion_constraints(motion_context: Dict[str, Any]) -> Dict[str, Any]:
    explicit = motion_context.get("motion_constraints")
    if isinstance(explicit, dict) and explicit:
        return dict(explicit)

    constraints: Dict[str, Any] = {}
    timing_policy = motion_context.get("timing_policy")
    if isinstance(timing_policy, dict) and timing_policy:
        constraints["timing_policy"] = dict(timing_policy)
    retarget_profile = motion_context.get("retarget_profile")
    if retarget_profile:
        constraints["retarget_profile"] = retarget_profile
    return constraints


def _coerce_positive_float(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if numeric <= 0:
        return None
    return numeric


def _isoformat(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value else None


def _derive_freshness_state(context: Dict[str, Any]) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    updated_at = _parse_datetime(context.get("updated_at"))
    expires_at = _parse_datetime(context.get("expires_at"))
    ttl_seconds = _coerce_positive_float(
        context.get("max_age_sec") or context.get("freshness_ttl_sec")
    )
    source_run_id = str(context.get("source_run_id") or "").strip() or None
    receipt_id = str(context.get("receipt_id") or "").strip() or None
    freshness = str(context.get("freshness") or "").strip().lower()
    stale_reason: Optional[str] = None

    has_provenance = any((updated_at, expires_at, source_run_id, receipt_id))
    if freshness in {"stale", "expired"}:
        freshness = "stale"
        stale_reason = "provider_marked_stale"
    elif expires_at and expires_at <= now:
        freshness = "stale"
        stale_reason = "expired"
    elif updated_at and ttl_seconds is not None and updated_at + timedelta(seconds=ttl_seconds) <= now:
        freshness = "stale"
        stale_reason = "ttl_exceeded"
    elif not has_provenance:
        freshness = "missing_provenance"
    else:
        freshness = "fresh"

    return {
        "updated_at": updated_at,
        "expires_at": expires_at,
        "ttl_seconds": ttl_seconds,
        "source_run_id": source_run_id,
        "receipt_id": receipt_id,
        "freshness": freshness,
        "stale_reason": stale_reason,
        "has_provenance": has_provenance,
        "confidence": context.get("confidence"),
    }


def guard_motion_context(motion_context: Dict[str, Any]) -> Dict[str, Any]:
    motion_context = dict(motion_context or {})
    if not motion_context:
        return {
            "active_motion": None,
            "motion_artifact_refs": [],
            "motion_constraints": {},
            "metadata": {},
        }

    active_motion = derive_active_motion(motion_context)
    motion_artifact_refs = _normalize_motion_artifact_refs(
        motion_context.get("artifact_refs")
    )
    motion_constraints = derive_motion_constraints(motion_context)

    freshness_state = _derive_freshness_state(motion_context)
    updated_at = freshness_state["updated_at"]
    expires_at = freshness_state["expires_at"]
    source_run_id = freshness_state["source_run_id"]
    receipt_id = freshness_state["receipt_id"]
    freshness = freshness_state["freshness"]
    stale_reason = freshness_state["stale_reason"]
    has_provenance = freshness_state["has_provenance"]

    if freshness == "stale":
        active_motion = None

    metadata = {
        "motion_provider": motion_context.get("provider"),
        "motion_source_family": motion_context.get("source_family"),
        "motion_source_run_id": source_run_id,
        "motion_receipt_id": receipt_id,
        "motion_confidence": freshness_state["confidence"],
        "motion_context_updated_at": _isoformat(updated_at),
        "motion_context_expires_at": _isoformat(expires_at),
        "motion_freshness": freshness,
        "motion_stale_reason": stale_reason,
        "motion_has_provenance": has_provenance,
        "motion_artifact_count": len(motion_artifact_refs),
    }

    return {
        "active_motion": active_motion,
        "motion_artifact_refs": motion_artifact_refs,
        "motion_constraints": motion_constraints,
        "metadata": {key: value for key, value in metadata.items() if value is not None},
    }


def guard_performance_context(performance_context: Dict[str, Any]) -> Dict[str, Any]:
    performance_context = dict(performance_context or {})
    if not performance_context:
        return {
            "performance_state": {},
            "metadata": {},
        }

    performance_state = _normalize_performance_state(performance_context)
    freshness_state = _derive_freshness_state(performance_context)
    updated_at = freshness_state["updated_at"]
    expires_at = freshness_state["expires_at"]
    source_run_id = freshness_state["source_run_id"]
    receipt_id = freshness_state["receipt_id"]
    freshness = freshness_state["freshness"]
    stale_reason = freshness_state["stale_reason"]
    has_provenance = freshness_state["has_provenance"]

    if freshness == "stale":
        if "face_lane_active" in performance_state:
            performance_state["face_lane_active"] = False
        if "body_lane_active" in performance_state:
            performance_state["body_lane_active"] = False
        performance_state["preview_ready_state"] = "stale"

    metadata = {
        "performance_storyboard_id": performance_state.get("storyboard_id"),
        "performance_mode": performance_state.get("performance_mode"),
        "performance_execution_bridge": performance_state.get("execution_bridge"),
        "performance_source_run_id": source_run_id,
        "performance_receipt_id": receipt_id,
        "performance_confidence": freshness_state["confidence"],
        "performance_context_updated_at": _isoformat(updated_at),
        "performance_context_expires_at": _isoformat(expires_at),
        "performance_freshness": freshness,
        "performance_stale_reason": stale_reason,
        "performance_has_provenance": has_provenance,
    }

    return {
        "performance_state": performance_state,
        "metadata": {key: value for key, value in metadata.items() if value is not None},
    }
