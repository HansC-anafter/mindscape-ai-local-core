"""Request payload builders for visual acceptance follow-up artifacts."""

from typing import Any, Dict

from .constants import VISUAL_ACCEPTANCE_FOLLOWUP_ARTIFACT_KIND
from .dependencies import (
    normalize_followup_action_id,
    normalize_followup_consumer_kind,
    normalize_followup_lane_id,
)
from .identifiers import _request_artifact_id


def _request_payload(
    *,
    bundle: Dict[str, Any],
    decision_payload: Dict[str, Any],
    lane: Dict[str, Any],
) -> Dict[str, Any]:
    review_bundle_id = str(bundle.get("review_bundle_id") or "").strip()
    lane_id = normalize_followup_lane_id(lane.get("lane_id"))
    dispatch_state = str(lane.get("dispatch_state") or "").strip() or "ready"
    payload = {
        "request_id": _request_artifact_id(review_bundle_id, lane_id),
        "review_bundle_id": review_bundle_id or None,
        "run_id": str(bundle.get("run_id") or "").strip() or None,
        "scene_id": str(bundle.get("scene_id") or "").strip() or None,
        "workspace_id": str(bundle.get("workspace_id") or "").strip() or None,
        "source_kind": str(bundle.get("source_kind") or "").strip() or None,
        "package_id": str(bundle.get("package_id") or "").strip() or None,
        "preset_id": str(bundle.get("preset_id") or "").strip() or None,
        "artifact_ids": list(bundle.get("artifact_ids") or []),
        "binding_mode": str(bundle.get("binding_mode") or "").strip() or None,
        "source_decision": str(decision_payload.get("decision") or "").strip() or None,
        "reviewed_at": str(decision_payload.get("reviewed_at") or "").strip() or None,
        "lane_id": lane_id or None,
        "consumer_kind": normalize_followup_consumer_kind(lane.get("consumer_kind")) or None,
        "request_state": dispatch_state,
        "blocking_reason": str(lane.get("blocking_reason") or "").strip() or None,
        "action_ids": [
            normalize_followup_action_id(item)
            for item in (lane.get("action_ids") or [])
            if normalize_followup_action_id(item)
        ],
        "target_ref": dict(lane.get("target_ref") or {}),
        "dispatch_context": {
            "scene_context": dict(bundle.get("scene_context") or {}),
            "source_metadata": dict(bundle.get("source_metadata") or {}),
            "slots": [
                dict(item)
                for item in (bundle.get("slots") or [])
                if isinstance(item, dict)
            ],
        },
    }
    return payload


def _request_metadata(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "kind": VISUAL_ACCEPTANCE_FOLLOWUP_ARTIFACT_KIND,
        "review_bundle_id": payload.get("review_bundle_id"),
        "run_id": payload.get("run_id"),
        "scene_id": payload.get("scene_id"),
        "lane_id": payload.get("lane_id"),
        "consumer_kind": payload.get("consumer_kind"),
        "request_state": payload.get("request_state"),
        "blocking_reason": payload.get("blocking_reason"),
        "package_id": payload.get("package_id"),
        "preset_id": payload.get("preset_id"),
        "artifact_ids": payload.get("artifact_ids") or [],
    }
