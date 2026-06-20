"""Dispatch payload builders for visual acceptance follow-up requests."""

from typing import Any, Dict, Optional

from .dependencies import (
    normalize_followup_consumer_kind,
    normalize_followup_lane_id,
)
from .identifiers import (
    _dispatch_artifact_id,
    _safe_segment,
    _scene_review_artifact_id,
    _utc_now_iso,
)


def _scene_payload_from_request(request_content: Dict[str, Any]) -> Dict[str, Any]:
    dispatch_context = (
        dict(request_content.get("dispatch_context") or {})
        if isinstance(request_content.get("dispatch_context"), dict)
        else {}
    )
    scene_context = (
        dict(dispatch_context.get("scene_context") or {})
        if isinstance(dispatch_context.get("scene_context"), dict)
        else {}
    )
    scene_payload = (
        dict(scene_context.get("scene_payload") or {})
        if isinstance(scene_context.get("scene_payload"), dict)
        else {}
    )
    scene_id = str(request_content.get("scene_id") or "").strip() or "scene"
    if not scene_payload:
        scene_payload = {
            "scene_id": scene_id,
            "scene_manifest": dict(scene_context.get("scene_manifest") or {}),
            "object_workload_snapshot": dict(
                scene_context.get("object_workload_snapshot") or {}
            ),
        }
    scene_payload["scene_id"] = str(scene_payload.get("scene_id") or scene_id).strip() or scene_id
    return scene_payload


def _build_single_scene_storyboard(request_content: Dict[str, Any]) -> Dict[str, Any]:
    dispatch_context = (
        dict(request_content.get("dispatch_context") or {})
        if isinstance(request_content.get("dispatch_context"), dict)
        else {}
    )
    source_metadata = (
        dict(dispatch_context.get("source_metadata") or {})
        if isinstance(dispatch_context.get("source_metadata"), dict)
        else {}
    )
    scene_payload = _scene_payload_from_request(request_content)
    workspace_id = str(request_content.get("workspace_id") or "").strip()
    if not workspace_id:
        raise ValueError("followup_dispatch_missing_workspace_id")
    if not scene_payload.get("scene_manifest") and not scene_payload.get("direction_ir"):
        raise ValueError("followup_dispatch_missing_scene_payload")

    source_type = str(source_metadata.get("source_type") or "").strip().lower() or "generative"
    render_profile = source_metadata.get("render_profile")
    if not isinstance(render_profile, dict):
        render_profile = {"profile_id": "vr_preview_local"}

    storyboard_id = (
        f"followup_{_safe_segment(str(request_content.get('review_bundle_id') or ''), 'bundle')}"
    )
    return {
        "storyboard_id": storyboard_id,
        "workspace_id": workspace_id,
        "render_profile": dict(render_profile),
        "global_settings": {"source_type": source_type},
        "scenes": [scene_payload],
    }


def _dispatch_payload(
    *,
    request_content: Dict[str, Any],
    dispatch_mode: str,
    dispatch_status: str,
    actor_id: str,
    notes: str,
    dispatch_result: Optional[Dict[str, Any]] = None,
    storyboard: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    payload = {
        "artifact_id": _dispatch_artifact_id(
            str(request_content.get("request_id") or "").strip()
        ),
        "request_id": str(request_content.get("request_id") or "").strip() or None,
        "review_bundle_id": str(request_content.get("review_bundle_id") or "").strip() or None,
        "run_id": str(request_content.get("run_id") or "").strip() or None,
        "scene_id": str(request_content.get("scene_id") or "").strip() or None,
        "workspace_id": str(request_content.get("workspace_id") or "").strip() or None,
        "lane_id": str(request_content.get("lane_id") or "").strip() or None,
        "consumer_kind": str(request_content.get("consumer_kind") or "").strip() or None,
        "request_state_before_dispatch": str(
            request_content.get("request_state") or ""
        ).strip() or None,
        "dispatch_mode": dispatch_mode,
        "dispatch_status": dispatch_status,
        "dispatch_actor_id": str(actor_id or "").strip() or None,
        "dispatch_notes": str(notes or "").strip() or None,
        "action_ids": list(request_content.get("action_ids") or []),
        "target_ref": dict(request_content.get("target_ref") or {}),
        "dispatch_context": dict(request_content.get("dispatch_context") or {}),
        "dispatch_result": dict(dispatch_result or {}),
    }
    if storyboard is not None:
        payload["storyboard"] = dict(storyboard)
    return payload


def _dispatch_context_from_request(request_content: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(request_content.get("dispatch_context"), dict):
        return {}
    return dict(request_content.get("dispatch_context") or {})


def _source_metadata_from_request(request_content: Dict[str, Any]) -> Dict[str, Any]:
    dispatch_context = _dispatch_context_from_request(request_content)
    if not isinstance(dispatch_context.get("source_metadata"), dict):
        return {}
    return dict(dispatch_context.get("source_metadata") or {})


def _capability_owned_consumer_handoff_result(
    request_content: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "success": True,
        "mode": "consumer_handoff",
        "execution_strategy": "workspace_artifact_handoff",
        "handoff_reason": "capability_owned_consumer_required",
        "lane_id": normalize_followup_lane_id(request_content.get("lane_id")) or None,
        "consumer_kind": normalize_followup_consumer_kind(
            request_content.get("consumer_kind")
        )
        or None,
        "review_bundle_id": str(request_content.get("review_bundle_id") or "").strip()
        or None,
        "workspace_id": str(request_content.get("workspace_id") or "").strip() or None,
        "package_id": str(request_content.get("package_id") or "").strip() or None,
        "preset_id": str(request_content.get("preset_id") or "").strip() or None,
        "artifact_ids": list(request_content.get("artifact_ids") or []),
        "binding_mode": str(request_content.get("binding_mode") or "").strip() or None,
        "target_ref": (
            dict(request_content.get("target_ref") or {})
            if isinstance(request_content.get("target_ref"), dict)
            else {}
        ),
    }


def _bundle_content_from_request(
    request_content: Dict[str, Any],
    artifacts_store: Any,
) -> Dict[str, Any]:
    review_bundle_id = str(request_content.get("review_bundle_id") or "").strip()
    if not review_bundle_id:
        return {}
    artifact = artifacts_store.get_artifact(review_bundle_id)
    if not artifact or not isinstance(artifact.content, dict):
        return {}
    return dict(artifact.content or {})


def _build_local_scene_review_request(
    *,
    request_content: Dict[str, Any],
    bundle_content: Dict[str, Any],
) -> Dict[str, Any]:
    dispatch_context = _dispatch_context_from_request(request_content)
    scene_context = (
        dict(dispatch_context.get("scene_context") or {})
        if isinstance(dispatch_context.get("scene_context"), dict)
        else {}
    )
    source_metadata = _source_metadata_from_request(request_content)
    scene_payload = _scene_payload_from_request(request_content)
    snapshot = (
        dict(scene_payload.get("object_workload_snapshot") or {})
        if isinstance(scene_payload.get("object_workload_snapshot"), dict)
        else {}
    )
    latest_review_decision = (
        dict(bundle_content.get("latest_review_decision") or {})
        if isinstance(bundle_content.get("latest_review_decision"), dict)
        else {}
    )
    checklist_template = [
        dict(item)
        for item in (bundle_content.get("checklist_template") or [])
        if isinstance(item, dict)
    ]
    slots = [
        dict(item)
        for item in (dispatch_context.get("slots") or bundle_content.get("slots") or [])
        if isinstance(item, dict)
    ]
    request_id = str(request_content.get("request_id") or "").strip()
    review_bundle_id = str(request_content.get("review_bundle_id") or "").strip()
    quality_gate = {
        "quality_gate_state": str(snapshot.get("quality_gate_state") or "").strip() or None,
        "impact_region_mode": str(snapshot.get("impact_region_mode") or "").strip() or None,
        "impact_region_bbox": (
            dict(snapshot.get("impact_region_bbox") or {})
            if isinstance(snapshot.get("impact_region_bbox"), dict)
            else {}
        ),
        "source_scene_id": str(snapshot.get("source_scene_id") or "").strip() or None,
        "source_reference_fingerprint": (
            str(snapshot.get("source_reference_fingerprint") or "").strip() or None
        ),
        "source_image_ref": (
            dict(snapshot.get("source_image_ref") or {})
            if isinstance(snapshot.get("source_image_ref"), dict)
            else {}
        ),
        "affected_object_instance_ids": list(snapshot.get("affected_object_instance_ids") or []),
    }
    return {
        "artifact_id": _scene_review_artifact_id(request_id or review_bundle_id or "request"),
        "request_id": request_id or None,
        "review_bundle_id": review_bundle_id or None,
        "workspace_id": str(request_content.get("workspace_id") or "").strip() or None,
        "project_id": str(bundle_content.get("project_id") or "").strip()
        or _project_id_from_request(request_content),
        "run_id": str(request_content.get("run_id") or "").strip() or None,
        "scene_id": str(request_content.get("scene_id") or "").strip() or None,
        "source_kind": str(request_content.get("source_kind") or "").strip() or None,
        "package_id": str(request_content.get("package_id") or "").strip() or None,
        "preset_id": str(request_content.get("preset_id") or "").strip() or None,
        "artifact_ids": list(request_content.get("artifact_ids") or []),
        "binding_mode": str(request_content.get("binding_mode") or "").strip() or None,
        "queue_state": "pending_review",
        "queue_reason": "escalate_local_scene_review",
        "source_decision": str(request_content.get("source_decision") or "").strip() or None,
        "reviewed_at": str(request_content.get("reviewed_at") or "").strip() or None,
        "review_decision": (
            latest_review_decision
            if latest_review_decision
            else {
                "decision": str(request_content.get("source_decision") or "").strip() or None,
                "reviewed_at": str(request_content.get("reviewed_at") or "").strip() or None,
            }
        ),
        "checklist_template": checklist_template,
        "quality_gate": quality_gate,
        "scene_context": scene_context or {"scene_payload": scene_payload},
        "source_metadata": source_metadata,
        "slots": slots,
        "action_ids": list(request_content.get("action_ids") or []),
        "target_ref": (
            dict(request_content.get("target_ref") or {})
            if isinstance(request_content.get("target_ref"), dict)
            else {}
        ),
        "dispatch_origin": {
            "followup_request_id": request_id or None,
            "lane_id": str(request_content.get("lane_id") or "").strip() or None,
            "consumer_kind": str(request_content.get("consumer_kind") or "").strip() or None,
        },
        "created_at": _utc_now_iso(),
    }


def _project_id_from_request(request_content: Dict[str, Any]) -> str:
    dispatch_context = _dispatch_context_from_request(request_content)
    scene_context = (
        dict(dispatch_context.get("scene_context") or {})
        if isinstance(dispatch_context.get("scene_context"), dict)
        else {}
    )
    source_metadata = _source_metadata_from_request(request_content)
    target_ref = (
        dict(request_content.get("target_ref") or {})
        if isinstance(request_content.get("target_ref"), dict)
        else {}
    )
    for candidate in (
        target_ref.get("project_id"),
        source_metadata.get("project_id"),
        source_metadata.get("projectId"),
        scene_context.get("project_id"),
        scene_context.get("projectId"),
    ):
        value = str(candidate or "").strip()
        if value:
            return value
    return "followup_project"


def _source_type_from_request(request_content: Dict[str, Any]) -> str:
    source_metadata = _source_metadata_from_request(request_content)
    return str(source_metadata.get("source_type") or "").strip() or "generative"
