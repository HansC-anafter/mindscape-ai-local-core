"""
Artifact review decision helpers.

This module defines a minimal durable contract for review decisions so the
backend can persist and validate acceptance outcomes before the UI flow lands.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

try:
    from app.services.artifact_review_followup_contract import (
        FOLLOWUP_ACTION_CAPABILITY_CONSUMER_HANDOFF,
        FOLLOWUP_CONSUMER_CAPABILITY_OWNED,
        FOLLOWUP_LANE_CAPABILITY_CONSUMER_HANDOFF,
        FOLLOWUP_PLAN_CAPABILITY_CONSUMER_HANDOFF_READY,
        FOLLOWUP_PLAN_CAPABILITY_CONSUMER_HANDOFF_REQUESTED,
        normalize_followup_action_id,
        normalize_followup_consumer_kind,
        normalize_followup_lane_id,
    )
except ImportError:
    from backend.app.services.artifact_review_followup_contract import (
        FOLLOWUP_ACTION_CAPABILITY_CONSUMER_HANDOFF,
        FOLLOWUP_CONSUMER_CAPABILITY_OWNED,
        FOLLOWUP_LANE_CAPABILITY_CONSUMER_HANDOFF,
        FOLLOWUP_PLAN_CAPABILITY_CONSUMER_HANDOFF_READY,
        FOLLOWUP_PLAN_CAPABILITY_CONSUMER_HANDOFF_REQUESTED,
        normalize_followup_action_id,
        normalize_followup_consumer_kind,
        normalize_followup_lane_id,
    )

REVIEW_DECISION_ACCEPTED = "accepted"
REVIEW_DECISION_REJECTED = "rejected"
REVIEW_DECISION_NEEDS_TUNE = "needs_tune"
REVIEW_DECISION_MANUAL_REQUIRED = "manual_required"

VALID_REVIEW_DECISIONS = {
    REVIEW_DECISION_ACCEPTED,
    REVIEW_DECISION_REJECTED,
    REVIEW_DECISION_NEEDS_TUNE,
    REVIEW_DECISION_MANUAL_REQUIRED,
}

FOLLOWUP_ACTION_SPECS: Dict[str, Dict[str, str]] = {
    "compare_against_accepted_baseline": {
        "lane_id": "baseline_compare",
        "consumer_kind": "review_compare",
    },
    "rerender_same_preset": {
        "lane_id": "rerender",
        "consumer_kind": "scene_rerender",
    },
    "retune_prompt_and_negative": {
        "lane_id": "rerender",
        "consumer_kind": "scene_rerender",
    },
    "retune_character_adapter": {
        "lane_id": "rerender",
        "consumer_kind": "scene_rerender",
    },
    "rebuild_contact_zone_mask": {
        "lane_id": "laf_patch",
        "consumer_kind": "layer_asset_forge_patch",
    },
    "escalate_local_scene_review": {
        "lane_id": "local_scene_review",
        "consumer_kind": "manual_scene_review",
    },
    "capture_accepted_baseline": {
        "lane_id": "baseline_capture",
        "consumer_kind": "accepted_baseline_capture",
    },
    FOLLOWUP_ACTION_CAPABILITY_CONSUMER_HANDOFF: {
        "lane_id": FOLLOWUP_LANE_CAPABILITY_CONSUMER_HANDOFF,
        "consumer_kind": FOLLOWUP_CONSUMER_CAPABILITY_OWNED,
    },
}

_ACCEPTED_ONLY_LANES = {
    "baseline_capture",
    FOLLOWUP_LANE_CAPABILITY_CONSUMER_HANDOFF,
}

CHECKLIST_LIBRARY: Dict[str, Dict[str, str]] = {
    "edge_cleanliness": {
        "label": "Edge Cleanliness",
        "description": "Whether the subject boundary contains jagged edges, holes, ghosting, or cut-out errors.",
    },
    "contact_zone_naturalness": {
        "label": "Contact Zone Naturalness",
        "description": "Whether the contact area between the object and hands, table, or supporting surface blends naturally.",
    },
    "identity_consistency": {
        "label": "Identity Consistency",
        "description": "Whether facial features, hairstyle, clothing, and other key identity traits stay consistent.",
    },
    "prompt_following": {
        "label": "Prompt Following",
        "description": "Whether composition, pose, emotion, and scene semantics match the render objective.",
    },
    "artifact_contamination": {
        "label": "Artifact Contamination",
        "description": "Whether the frame contains foreign objects, color contamination, ghosting, or implausible structures.",
    },
    "family_fit": {
        "label": "Family Fit",
        "description": "Whether the result matches the expected visual family of the package or preset.",
    },
    "lip_sync_naturalness": {
        "label": "Lip Sync Naturalness",
        "description": "Whether mouth movement aligns naturally with speech rhythm without obvious fake dubbing or mistiming.",
    },
    "mouth_shape_consistency": {
        "label": "Mouth Shape Consistency",
        "description": "Whether mouth shapes remain stable, consistent, and trackable across similar phonemes and matching shot segments.",
    },
    "expression_stability": {
        "label": "Expression Stability",
        "description": "Whether expression changes stay smooth without abrupt distortion, drift, or resets.",
    },
    "head_motion_coherence": {
        "label": "Head Motion Coherence",
        "description": "Whether head pose, driving motion, and character identity stay coherent without unnatural jitter.",
    },
    "temporal_jitter": {
        "label": "Temporal Jitter",
        "description": "Whether consecutive frames show high-frequency flicker or jitter around the mouth, eyes, or silhouette.",
    },
    "speaker_alignment": {
        "label": "Speaker Alignment",
        "description": "Whether the audio source, speaker identity, and the on-screen character are aligned correctly.",
    },
}

CHECKLIST_TEMPLATE_IDS: Dict[str, List[str]] = {
    "laf_patch": [
        "edge_cleanliness",
        "contact_zone_naturalness",
        "artifact_contamination",
        "identity_consistency",
    ],
    "vr_render": [
        "identity_consistency",
        "prompt_following",
        "family_fit",
        "artifact_contamination",
    ],
    "character_training_eval": [
        "identity_consistency",
        "family_fit",
        "prompt_following",
        "artifact_contamination",
    ],
    "character_performance_eval": [
        "expression_stability",
        "head_motion_coherence",
        "temporal_jitter",
        "speaker_alignment",
    ],
    "portrait_animation_eval": [
        "expression_stability",
        "head_motion_coherence",
        "temporal_jitter",
        "identity_consistency",
    ],
    "talking_head_eval": [
        "lip_sync_naturalness",
        "mouth_shape_consistency",
        "expression_stability",
        "speaker_alignment",
        "temporal_jitter",
    ],
    "default": [
        "identity_consistency",
        "prompt_following",
        "artifact_contamination",
    ],
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
def _normalize_followup_actions(actions: Optional[Iterable[Any]]) -> List[str]:
    seen: set[str] = set()
    normalized: List[str] = []
    for action in actions or []:
        value = normalize_followup_action_id(action)
        if not value or value in seen or value not in FOLLOWUP_ACTION_SPECS:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def _normalize_artifact_ids(values: Optional[Iterable[Any]]) -> List[str]:
    seen: set[str] = set()
    normalized: List[str] = []
    for value in values or []:
        item = str(value or "").strip()
        if not item or item in seen:
            continue
        seen.add(item)
        normalized.append(item)
    return normalized


def _lane_dispatch_state(lane_id: str, decision: str) -> Dict[str, Optional[str]]:
    normalized_lane_id = normalize_followup_lane_id(lane_id)
    if normalized_lane_id in _ACCEPTED_ONLY_LANES and decision != REVIEW_DECISION_ACCEPTED:
        return {
            "dispatch_state": "blocked",
            "blocking_reason": "accepted_review_required",
        }
    return {
        "dispatch_state": "ready",
        "blocking_reason": None,
    }


def build_followup_action_plan(
    *,
    review_bundle_id: str,
    decision: str,
    run_id: str = "",
    scene_id: str = "",
    source_kind: str = "",
    package_id: str = "",
    preset_id: str = "",
    artifact_ids: Optional[Iterable[Any]] = None,
    binding_mode: str = "",
    followup_actions: Optional[Iterable[Any]] = None,
) -> Dict[str, Any]:
    normalized_decision = str(decision or "").strip().lower()
    action_ids = _normalize_followup_actions(followup_actions)
    target_ref = {
        "run_id": str(run_id or "").strip() or None,
        "scene_id": str(scene_id or "").strip() or None,
        "source_kind": str(source_kind or "").strip().lower() or None,
        "package_id": str(package_id or "").strip() or None,
        "preset_id": str(preset_id or "").strip() or None,
        "artifact_ids": _normalize_artifact_ids(artifact_ids),
        "binding_mode": str(binding_mode or "").strip() or None,
    }

    lane_index: Dict[str, Dict[str, Any]] = {}
    for action_id in action_ids:
        spec = FOLLOWUP_ACTION_SPECS[action_id]
        lane_id = normalize_followup_lane_id(spec["lane_id"])
        if lane_id not in lane_index:
            state = _lane_dispatch_state(lane_id, normalized_decision)
            lane_index[lane_id] = {
                "lane_id": lane_id,
                "consumer_kind": normalize_followup_consumer_kind(spec["consumer_kind"]),
                "dispatch_state": state["dispatch_state"],
                "blocking_reason": state["blocking_reason"],
                "action_ids": [],
                "target_ref": dict(target_ref),
            }
        lane_index[lane_id]["action_ids"].append(action_id)

    lanes = list(lane_index.values())
    lane_ids = [str(item.get("lane_id") or "").strip() for item in lanes if item.get("lane_id")]
    dispatchable_lane_count = sum(
        1 for item in lanes if str(item.get("dispatch_state") or "").strip() == "ready"
    )
    blocked_lane_count = sum(
        1 for item in lanes if str(item.get("dispatch_state") or "").strip() == "blocked"
    )

    return {
        "review_bundle_id": str(review_bundle_id or "").strip() or None,
        "decision": normalized_decision or None,
        "action_ids": action_ids,
        "lane_ids": lane_ids,
        "lanes": lanes,
        "target_ref": target_ref,
        "rerender_required": any(lane_id in {"rerender", "laf_patch"} for lane_id in lane_ids),
        "manual_escalation_required": "local_scene_review" in lane_ids,
        "baseline_compare_requested": "baseline_compare" in lane_ids,
        "baseline_capture_requested": "baseline_capture" in lane_ids,
        FOLLOWUP_PLAN_CAPABILITY_CONSUMER_HANDOFF_REQUESTED: (
            FOLLOWUP_ACTION_CAPABILITY_CONSUMER_HANDOFF in action_ids
        ),
        FOLLOWUP_PLAN_CAPABILITY_CONSUMER_HANDOFF_READY: any(
            normalize_followup_lane_id(item.get("lane_id"))
            == FOLLOWUP_LANE_CAPABILITY_CONSUMER_HANDOFF
            and str(item.get("dispatch_state") or "").strip() == "ready"
            for item in lanes
        ),
        "dispatchable_lane_count": dispatchable_lane_count,
        "blocked_lane_count": blocked_lane_count,
    }


def _checklist_item(check_id: str, *, focus: str) -> Dict[str, Any]:
    definition = CHECKLIST_LIBRARY[check_id]
    return {
        "check_id": check_id,
        "label": definition["label"],
        "description": definition["description"],
        "focus": focus,
    }


def build_review_checklist_template(source_kind: str) -> List[Dict[str, Any]]:
    normalized_source_kind = str(source_kind or "").strip().lower()
    check_ids = CHECKLIST_TEMPLATE_IDS.get(
        normalized_source_kind,
        CHECKLIST_TEMPLATE_IDS["default"],
    )
    template: List[Dict[str, Any]] = []
    for index, check_id in enumerate(check_ids):
        template.append(
            _checklist_item(
                check_id,
                focus="primary" if index < 2 else "secondary",
            )
        )
    return template


def _normalized_score(value: Any) -> Optional[float]:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    if score < 0:
        score = 0.0
    if score > 1:
        score = 1.0
    return round(score, 3)


def normalize_review_checklist_scores(
    checklist_scores: Optional[Dict[str, Any]],
    *,
    checklist_template: Optional[Iterable[Dict[str, Any]]] = None,
) -> Dict[str, float]:
    template_ids = {
        str(item.get("check_id") or "").strip()
        for item in checklist_template or []
        if isinstance(item, dict)
    }
    normalized: Dict[str, float] = {}
    for key, value in dict(checklist_scores or {}).items():
        check_id = str(key or "").strip()
        if not check_id:
            continue
        if template_ids and check_id not in template_ids:
            continue
        score = _normalized_score(value)
        if score is None:
            continue
        normalized[check_id] = score
    return normalized


def build_artifact_review_decision(
    *,
    review_bundle_id: str,
    decision: str,
    reviewer_id: str = "",
    notes: str = "",
    checklist_scores: Optional[Dict[str, Any]] = None,
    followup_actions: Optional[Iterable[Any]] = None,
    reviewed_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Build and validate a minimal review decision payload."""

    review_bundle_id = str(review_bundle_id or "").strip()
    normalized_decision = str(decision or "").strip().lower()
    if not review_bundle_id:
        raise ValueError("review_bundle_id required")
    if normalized_decision not in VALID_REVIEW_DECISIONS:
        raise ValueError(f"invalid_review_decision:{decision}")

    return {
        "review_bundle_id": review_bundle_id,
        "decision": normalized_decision,
        "reviewer_id": str(reviewer_id or "").strip(),
        "reviewed_at": str(reviewed_at or _utc_now_iso()),
        "notes": str(notes or "").strip(),
        "checklist_scores": dict(checklist_scores or {}),
        "followup_actions": _normalize_followup_actions(followup_actions),
    }
