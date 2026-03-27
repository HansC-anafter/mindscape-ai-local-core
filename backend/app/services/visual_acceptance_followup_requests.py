"""
Materialize review follow-up lanes into durable workspace artifacts.
"""

from __future__ import annotations

import json
import hashlib
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from app.models.workspace import Artifact, ArtifactType, PrimaryActionType
    from app.services.artifact_review_followup_contract import (
        FOLLOWUP_LANE_CAPABILITY_CONSUMER_HANDOFF,
        normalize_followup_action_id,
        normalize_followup_consumer_kind,
        normalize_followup_lane_id,
    )
    from app.services.stores.postgres.artifacts_store import PostgresArtifactsStore
except ImportError:
    from backend.app.models.workspace import Artifact, ArtifactType, PrimaryActionType
    from backend.app.services.artifact_review_followup_contract import (
        FOLLOWUP_LANE_CAPABILITY_CONSUMER_HANDOFF,
        normalize_followup_action_id,
        normalize_followup_consumer_kind,
        normalize_followup_lane_id,
    )
    from backend.app.services.stores.postgres.artifacts_store import (
        PostgresArtifactsStore,
    )

VISUAL_ACCEPTANCE_FOLLOWUP_ARTIFACT_KIND = "visual_acceptance_followup_request"
VISUAL_ACCEPTANCE_FOLLOWUP_PLAYBOOK_CODE = "visual_acceptance_followup"
VISUAL_ACCEPTANCE_FOLLOWUP_DISPATCH_ARTIFACT_KIND = "visual_acceptance_followup_dispatch"
VISUAL_ACCEPTANCE_FOLLOWUP_DISPATCH_PLAYBOOK_CODE = "visual_acceptance_followup_dispatch"
VISUAL_ACCEPTANCE_SCENE_REVIEW_ARTIFACT_KIND = "visual_acceptance_scene_review_request"
VISUAL_ACCEPTANCE_SCENE_REVIEW_PLAYBOOK_CODE = "visual_acceptance_scene_review"
FOLLOWUP_REQUEST_STATE_READY = "ready"
FOLLOWUP_REQUEST_STATE_BLOCKED = "blocked"
FOLLOWUP_REQUEST_STATE_DISPATCHED = "dispatched"
FOLLOWUP_REQUEST_STATE_COMPLETED = "completed"
FOLLOWUP_REQUEST_STATE_SUPERSEDED = "superseded"
VALID_FOLLOWUP_REQUEST_STATES = {
    FOLLOWUP_REQUEST_STATE_READY,
    FOLLOWUP_REQUEST_STATE_BLOCKED,
    FOLLOWUP_REQUEST_STATE_DISPATCHED,
    FOLLOWUP_REQUEST_STATE_COMPLETED,
    FOLLOWUP_REQUEST_STATE_SUPERSEDED,
}
_MAX_ARTIFACT_ID_LENGTH = 64


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_visual_acceptance_artifacts_store() -> PostgresArtifactsStore:
    return PostgresArtifactsStore()


def _safe_segment(value: str, fallback: str) -> str:
    candidate = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "").strip())
    return candidate or fallback


def _bounded_identifier(value: str, fallback: str) -> str:
    candidate = _safe_segment(value, fallback)
    if len(candidate) <= _MAX_ARTIFACT_ID_LENGTH:
        return candidate
    digest = hashlib.sha1(candidate.encode("utf-8")).hexdigest()[:12]
    head = candidate[: _MAX_ARTIFACT_ID_LENGTH - len(digest) - 1].rstrip("_")
    return f"{head}_{digest}" if head else digest


def _bounded_execution_id(value: str, fallback: str) -> str:
    return _bounded_identifier(value, fallback)


def _list_workspace_artifacts(
    *,
    workspace_id: str,
    artifacts_store: Any,
) -> List[Artifact]:
    if hasattr(artifacts_store, "list_artifacts_by_workspace"):
        return list(artifacts_store.list_artifacts_by_workspace(workspace_id) or [])
    if hasattr(artifacts_store, "artifacts"):
        return [
            artifact
            for artifact in getattr(artifacts_store, "artifacts", {}).values()
            if str(getattr(artifact, "workspace_id", "") or "").strip() == workspace_id
        ]
    return []


def _request_artifact_id(review_bundle_id: str, lane_id: str) -> str:
    return _bounded_identifier(
        f"vafreq_{_safe_segment(review_bundle_id, 'bundle')}_{_safe_segment(lane_id, 'lane')}",
        "vafreq_request",
    )


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


def _dispatch_artifact_id(request_id: str) -> str:
    return _bounded_identifier(
        f"vafdispatch_{_safe_segment(request_id, 'request')}_{uuid.uuid4().hex[:8]}",
        "vafdispatch_request",
    )


def _scene_review_artifact_id(request_id: str) -> str:
    return _bounded_identifier(
        f"vasr_{_safe_segment(request_id, 'request')}",
        "vasr_request",
    )


def _dispatch_metadata(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "kind": VISUAL_ACCEPTANCE_FOLLOWUP_DISPATCH_ARTIFACT_KIND,
        "request_id": payload.get("request_id"),
        "review_bundle_id": payload.get("review_bundle_id"),
        "run_id": payload.get("run_id"),
        "scene_id": payload.get("scene_id"),
        "lane_id": payload.get("lane_id"),
        "consumer_kind": payload.get("consumer_kind"),
        "dispatch_status": payload.get("dispatch_status"),
        "dispatch_mode": payload.get("dispatch_mode"),
    }


def _scene_review_metadata(payload: Dict[str, Any]) -> Dict[str, Any]:
    quality_gate = (
        dict(payload.get("quality_gate") or {})
        if isinstance(payload.get("quality_gate"), dict)
        else {}
    )
    return {
        "kind": VISUAL_ACCEPTANCE_SCENE_REVIEW_ARTIFACT_KIND,
        "request_id": payload.get("request_id"),
        "review_bundle_id": payload.get("review_bundle_id"),
        "run_id": payload.get("run_id"),
        "scene_id": payload.get("scene_id"),
        "queue_state": payload.get("queue_state"),
        "source_kind": payload.get("source_kind"),
        "source_decision": payload.get("source_decision"),
        "quality_gate_state": quality_gate.get("quality_gate_state"),
        "impact_region_mode": quality_gate.get("impact_region_mode"),
        "package_id": payload.get("package_id"),
        "preset_id": payload.get("preset_id"),
        "artifact_ids": payload.get("artifact_ids") or [],
    }


def _upsert_dispatch_artifact(
    *,
    workspace_id: str,
    payload: Dict[str, Any],
    artifacts_store: Any,
) -> Artifact:
    artifact_id = str(payload.get("artifact_id") or "").strip()
    lane_id = str(payload.get("lane_id") or "").strip()
    scene_id = str(payload.get("scene_id") or "").strip() or "scene"
    dispatch_status = str(payload.get("dispatch_status") or "").strip() or "pending"
    artifact = Artifact(
        id=artifact_id,
        workspace_id=workspace_id,
        execution_id=_bounded_execution_id(
            f"visual_acceptance_dispatch:{payload.get('run_id') or 'run'}:{scene_id}:{lane_id or 'lane'}",
            "visual_acceptance_dispatch",
        ),
        playbook_code=VISUAL_ACCEPTANCE_FOLLOWUP_DISPATCH_PLAYBOOK_CODE,
        artifact_type=ArtifactType.DATA,
        title=f"Visual Acceptance Dispatch: {scene_id} / {lane_id or 'lane'}",
        summary=(
            f"{payload.get('consumer_kind') or 'followup'} dispatch "
            f"for scene {scene_id} ({dispatch_status})"
        ),
        content=payload,
        storage_ref="",
        primary_action_type=PrimaryActionType.DOWNLOAD,
        metadata=_dispatch_metadata(payload),
    )
    existing = artifacts_store.get_artifact(artifact_id)
    if existing:
        artifacts_store.update_artifact(
            artifact_id,
            title=artifact.title,
            summary=artifact.summary,
            content=artifact.content,
            metadata=artifact.metadata,
            artifact_type=artifact.artifact_type,
            primary_action_type=artifact.primary_action_type,
        )
    else:
        artifacts_store.create_artifact(artifact)
    return artifacts_store.get_artifact(artifact_id) or artifact


def _upsert_scene_review_artifact(
    *,
    workspace_id: str,
    payload: Dict[str, Any],
    artifacts_store: Any,
) -> Artifact:
    artifact_id = str(payload.get("artifact_id") or "").strip()
    scene_id = str(payload.get("scene_id") or "").strip() or "scene"
    queue_state = str(payload.get("queue_state") or "").strip() or "pending_review"
    artifact = Artifact(
        id=artifact_id,
        workspace_id=workspace_id,
        execution_id=_bounded_execution_id(
            f"visual_acceptance_scene_review:{payload.get('run_id') or 'run'}:{scene_id}",
            "visual_acceptance_scene_review",
        ),
        playbook_code=VISUAL_ACCEPTANCE_SCENE_REVIEW_PLAYBOOK_CODE,
        artifact_type=ArtifactType.DATA,
        title=f"Visual Acceptance Scene Review: {scene_id}",
        summary=f"Manual scene review queue item for scene {scene_id} ({queue_state})",
        content=payload,
        storage_ref="",
        primary_action_type=PrimaryActionType.DOWNLOAD,
        metadata=_scene_review_metadata(payload),
    )
    existing = artifacts_store.get_artifact(artifact_id)
    if existing:
        artifacts_store.update_artifact(
            artifact_id,
            title=artifact.title,
            summary=artifact.summary,
            content=artifact.content,
            metadata=artifact.metadata,
            artifact_type=artifact.artifact_type,
            primary_action_type=artifact.primary_action_type,
        )
    else:
        artifacts_store.create_artifact(artifact)
    return artifacts_store.get_artifact(artifact_id) or artifact


def _upsert_request_artifact(
    *,
    workspace_id: str,
    payload: Dict[str, Any],
    artifacts_store: Any,
) -> Dict[str, Any]:
    request_id = str(payload.get("request_id") or "").strip()
    lane_id = str(payload.get("lane_id") or "").strip()
    scene_id = str(payload.get("scene_id") or "").strip() or "scene"
    metadata = _request_metadata(payload)
    artifact = Artifact(
        id=request_id,
        workspace_id=workspace_id,
        execution_id=_bounded_execution_id(
            f"visual_acceptance_followup:{payload.get('run_id') or 'run'}:{scene_id}:{lane_id or 'lane'}",
            "visual_acceptance_followup",
        ),
        playbook_code=VISUAL_ACCEPTANCE_FOLLOWUP_PLAYBOOK_CODE,
        artifact_type=ArtifactType.DATA,
        title=f"Visual Acceptance Follow-up: {scene_id} / {lane_id or 'lane'}",
        summary=(
            f"{payload.get('consumer_kind') or 'followup'} request "
            f"for scene {scene_id} ({payload.get('request_state') or 'ready'})"
        ),
        content=payload,
        storage_ref="",
        primary_action_type=PrimaryActionType.DOWNLOAD,
        metadata=metadata,
    )
    existing = artifacts_store.get_artifact(request_id)
    if existing:
        artifacts_store.update_artifact(
            request_id,
            title=artifact.title,
            summary=artifact.summary,
            content=artifact.content,
            metadata=artifact.metadata,
            artifact_type=artifact.artifact_type,
            primary_action_type=artifact.primary_action_type,
        )
    else:
        artifacts_store.create_artifact(artifact)
    return {
        "artifact_id": request_id,
        "lane_id": lane_id or None,
        "consumer_kind": payload.get("consumer_kind"),
        "request_state": payload.get("request_state"),
        "blocking_reason": payload.get("blocking_reason"),
    }


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


def _laf_selection_mode(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"", "named", "targets"}:
        return "targets"
    if normalized == "manual_mask":
        return "manual_mask"
    if normalized == "all":
        return "all"
    return "targets"


def _laf_usage_bindings(scene_payload: Dict[str, Any], scene_id: str) -> List[Dict[str, Any]]:
    snapshot = (
        dict(scene_payload.get("object_workload_snapshot") or {})
        if isinstance(scene_payload.get("object_workload_snapshot"), dict)
        else {}
    )
    usage_bindings = [
        dict(item)
        for item in (snapshot.get("usage_bindings") or [])
        if isinstance(item, dict)
    ]
    scene_specific = [
        dict(item)
        for item in usage_bindings
        if str(item.get("scene_id") or "").strip() == scene_id
    ]
    return scene_specific or usage_bindings


def _build_laf_patch_request(request_content: Dict[str, Any]) -> Dict[str, Any]:
    scene_payload = _scene_payload_from_request(request_content)
    scene_id = str(request_content.get("scene_id") or "").strip() or str(
        scene_payload.get("scene_id") or ""
    ).strip() or "scene"
    snapshot = (
        dict(scene_payload.get("object_workload_snapshot") or {})
        if isinstance(scene_payload.get("object_workload_snapshot"), dict)
        else {}
    )
    source_image_ref = snapshot.get("source_image_ref")
    if not isinstance(source_image_ref, dict) or not source_image_ref:
        raise ValueError("followup_dispatch_missing_source_image_ref")

    affected_ids = {
        str(item or "").strip()
        for item in (snapshot.get("affected_object_instance_ids") or [])
        if str(item or "").strip()
    }
    usage_bindings = _laf_usage_bindings(scene_payload, scene_id)

    direction_ir = (
        dict(scene_payload.get("direction_ir") or {})
        if isinstance(scene_payload.get("direction_ir"), dict)
        else {}
    )
    direction_targets = [
        dict(item)
        for item in (direction_ir.get("object_targets") or [])
        if isinstance(item, dict)
    ]
    target_by_id: Dict[str, Dict[str, Any]] = {}
    target_by_instance: Dict[str, Dict[str, Any]] = {}
    for target in direction_targets:
        target_id = str(
            target.get("object_id")
            or target.get("object_target_id")
            or target.get("object_semantic_key")
            or ""
        ).strip()
        instance_id = str(target.get("object_instance_id") or "").strip()
        if target_id and target_id not in target_by_id:
            target_by_id[target_id] = target
        if instance_id and instance_id not in target_by_instance:
            target_by_instance[instance_id] = target

    object_targets: List[Dict[str, Any]] = []
    scene_assets = [
        dict(item)
        for item in (scene_payload.get("object_assets") or [])
        if isinstance(item, dict)
    ]
    for asset in scene_assets:
        object_target_id = str(asset.get("object_target_id") or "").strip()
        object_instance_id = str(asset.get("object_instance_id") or "").strip()
        if affected_ids and object_instance_id and object_instance_id not in affected_ids:
            continue
        direction_target = (
            target_by_id.get(object_target_id)
            or target_by_instance.get(object_instance_id)
            or {}
        )
        resolved_target_id = (
            object_target_id
            or str(
                direction_target.get("object_id")
                or direction_target.get("object_target_id")
                or direction_target.get("object_semantic_key")
                or ""
            ).strip()
        )
        if not resolved_target_id:
            continue
        source_reference_fingerprint = str(
            asset.get("source_reference_fingerprint")
            or direction_target.get("source_reference_fingerprint")
            or snapshot.get("source_reference_fingerprint")
            or ""
        ).strip()
        object_targets.append(
            {
                "object_target_id": resolved_target_id,
                "object_id": str(
                    direction_target.get("object_id") or resolved_target_id
                ).strip(),
                "object_instance_id": object_instance_id or None,
                "label": str(
                    direction_target.get("label")
                    or resolved_target_id
                    or object_instance_id
                    or "object"
                ).strip(),
                "source_reference_fingerprint": source_reference_fingerprint,
                "usage_bindings": [dict(item) for item in usage_bindings],
            }
        )

    if not object_targets:
        for target in direction_targets:
            object_instance_id = str(target.get("object_instance_id") or "").strip()
            if affected_ids and object_instance_id and object_instance_id not in affected_ids:
                continue
            resolved_target_id = str(
                target.get("object_id")
                or target.get("object_target_id")
                or target.get("object_semantic_key")
                or ""
            ).strip()
            if not resolved_target_id:
                continue
            object_targets.append(
                {
                    "object_target_id": resolved_target_id,
                    "object_id": resolved_target_id,
                    "object_instance_id": object_instance_id or None,
                    "label": str(target.get("label") or resolved_target_id or "object").strip(),
                    "source_reference_fingerprint": str(
                        target.get("source_reference_fingerprint")
                        or snapshot.get("source_reference_fingerprint")
                        or ""
                    ).strip(),
                    "usage_bindings": [dict(item) for item in usage_bindings],
                }
            )

    if not object_targets:
        raise ValueError("followup_dispatch_missing_object_targets")

    return {
        "job_id": (
            f"laf_followup_{_safe_segment(str(request_content.get('review_bundle_id') or ''), 'bundle')}"
            f"_{_safe_segment(scene_id, 'scene')}_{uuid.uuid4().hex[:8]}"
        ),
        "image_ref": dict(source_image_ref),
        "selection_mode": _laf_selection_mode(snapshot.get("selection_mode")),
        "source_scene_ref": {
            "scene_id": str(snapshot.get("source_scene_id") or scene_id).strip() or scene_id
        },
        "object_targets": object_targets,
    }


def _write_bundle_manifest(bundle: Dict[str, Any], manifest_path: str) -> None:
    candidate = Path(str(manifest_path or "").strip())
    if not candidate:
        return
    candidate.parent.mkdir(parents=True, exist_ok=True)
    candidate.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")


def _state_counts(refs: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        state = str(ref.get("request_state") or "").strip()
        if not state:
            continue
        counts[state] = counts.get(state, 0) + 1
    return counts


def _sync_followup_request_state_to_bundle(
    *,
    request_artifact: Artifact,
    request_content: Dict[str, Any],
    transition_event: Dict[str, Any],
    artifacts_store: Any,
) -> None:
    review_bundle_id = str(request_content.get("review_bundle_id") or "").strip()
    if not review_bundle_id:
        return
    bundle_artifact = artifacts_store.get_artifact(review_bundle_id)
    if not bundle_artifact:
        return
    bundle_content = (
        dict(bundle_artifact.content or {})
        if isinstance(bundle_artifact.content, dict)
        else {}
    )
    bundle_metadata = (
        dict(bundle_artifact.metadata or {})
        if isinstance(bundle_artifact.metadata, dict)
        else {}
    )
    request_refs = [
        dict(item)
        for item in (bundle_content.get("followup_request_refs") or [])
        if isinstance(item, dict)
    ]
    updated_refs: List[Dict[str, Any]] = []
    for ref in request_refs:
        item = dict(ref)
        if str(item.get("artifact_id") or "").strip() == request_artifact.id:
            item["request_state"] = request_content.get("request_state")
            item["blocking_reason"] = request_content.get("blocking_reason")
            item["last_transition"] = transition_event
        updated_refs.append(item)
    bundle_content["followup_request_refs"] = updated_refs
    latest_review = (
        dict(bundle_content.get("latest_review_decision") or {})
        if isinstance(bundle_content.get("latest_review_decision"), dict)
        else {}
    )
    if latest_review:
        latest_review["followup_request_refs"] = updated_refs
        bundle_content["latest_review_decision"] = latest_review
    history = bundle_content.get("review_decisions")
    if isinstance(history, list) and history:
        last_item = history[-1]
        if isinstance(last_item, dict):
            updated_last = dict(last_item)
            updated_last["followup_request_refs"] = updated_refs
            history[-1] = updated_last
            bundle_content["review_decisions"] = history
    bundle_metadata["followup_request_count"] = len(updated_refs)
    bundle_metadata["followup_request_state_counts"] = _state_counts(updated_refs)
    manifest_path = str(bundle_metadata.get("manifest_path") or "").strip()
    if manifest_path:
        _write_bundle_manifest(bundle_content, manifest_path)
    artifacts_store.update_artifact(
        bundle_artifact.id,
        content=bundle_content,
        metadata=bundle_metadata,
    )


def _sync_followup_request_state_to_run(
    *,
    request_artifact: Artifact,
    request_content: Dict[str, Any],
    transition_event: Dict[str, Any],
) -> None:
    tenant_id = "default"
    run_id = str(request_content.get("run_id") or "").strip()
    scene_id = str(request_content.get("scene_id") or "").strip()
    if not run_id or not scene_id:
        return
    try:
        try:
            from app.capabilities.multi_media_studio.models import production_run
        except ImportError:
            from backend.app.capabilities.multi_media_studio.models import production_run
        run = production_run.find_run(tenant_id, run_id)
        if not run:
            return
        scene_results = run.get("scene_results") if isinstance(run.get("scene_results"), list) else []
        updated = False
        for scene_result in scene_results:
            if not isinstance(scene_result, dict):
                continue
            if str(scene_result.get("scene_id") or "").strip() != scene_id:
                continue
            provider_metadata = (
                dict(scene_result.get("provider_metadata") or {})
                if isinstance(scene_result.get("provider_metadata"), dict)
                else {}
            )
            request_refs = [
                dict(item)
                for item in (provider_metadata.get("followup_request_refs") or [])
                if isinstance(item, dict)
            ]
            updated_refs: List[Dict[str, Any]] = []
            for ref in request_refs:
                item = dict(ref)
                if str(item.get("artifact_id") or "").strip() == request_artifact.id:
                    item["request_state"] = request_content.get("request_state")
                    item["blocking_reason"] = request_content.get("blocking_reason")
                    item["last_transition"] = transition_event
                updated_refs.append(item)
            provider_metadata["followup_request_refs"] = updated_refs
            review_decision_ref = (
                dict(provider_metadata.get("review_decision_ref") or {})
                if isinstance(provider_metadata.get("review_decision_ref"), dict)
                else {}
            )
            if review_decision_ref:
                review_decision_ref["followup_request_refs"] = updated_refs
                provider_metadata["review_decision_ref"] = review_decision_ref
            bundle_refs = provider_metadata.get("review_bundle_refs")
            updated_bundle_refs: List[Dict[str, Any]] = []
            for bundle_ref in bundle_refs or []:
                if not isinstance(bundle_ref, dict):
                    continue
                item = dict(bundle_ref)
                item["followup_request_refs"] = updated_refs
                review_decision = (
                    dict(item.get("review_decision") or {})
                    if isinstance(item.get("review_decision"), dict)
                    else {}
                )
                if review_decision:
                    review_decision["followup_request_refs"] = updated_refs
                    item["review_decision"] = review_decision
                updated_bundle_refs.append(item)
            if updated_bundle_refs:
                provider_metadata["review_bundle_refs"] = updated_bundle_refs
            scene_result["provider_metadata"] = provider_metadata
            updated = True
            break
        if updated:
            run["updated_at"] = _utc_now_iso()
            production_run._save_run(tenant_id, run["project_id"], run)  # type: ignore[attr-defined]
    except Exception:
        return


def materialize_followup_request_artifacts(
    *,
    bundle: Dict[str, Any],
    decision_payload: Dict[str, Any],
    artifacts_store: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    workspace_id = str(bundle.get("workspace_id") or "").strip()
    review_bundle_id = str(bundle.get("review_bundle_id") or "").strip()
    lanes = [
        {
            **dict(item),
            "lane_id": normalize_followup_lane_id(item.get("lane_id")),
            "consumer_kind": normalize_followup_consumer_kind(item.get("consumer_kind")),
            "action_ids": [
                normalize_followup_action_id(action_id)
                for action_id in (item.get("action_ids") or [])
                if normalize_followup_action_id(action_id)
            ],
        }
        for item in ((decision_payload.get("downstream_action_plan") or {}).get("lanes") or [])
        if isinstance(item, dict)
    ]
    if not workspace_id or not review_bundle_id:
        return []

    store = artifacts_store or get_visual_acceptance_artifacts_store()
    active_lane_ids = {
        normalize_followup_lane_id(item.get("lane_id"))
        for item in lanes
        if normalize_followup_lane_id(item.get("lane_id"))
    }

    refs: List[Dict[str, Any]] = []
    for lane in lanes:
        payload = _request_payload(
            bundle=bundle,
            decision_payload=decision_payload,
            lane=lane,
        )
        refs.append(
            _upsert_request_artifact(
                workspace_id=workspace_id,
                payload=payload,
                artifacts_store=store,
            )
        )

    for artifact in _list_workspace_artifacts(workspace_id=workspace_id, artifacts_store=store):
        metadata = dict(artifact.metadata or {}) if isinstance(artifact.metadata, dict) else {}
        if metadata.get("kind") != VISUAL_ACCEPTANCE_FOLLOWUP_ARTIFACT_KIND:
            continue
        if str(metadata.get("review_bundle_id") or "").strip() != review_bundle_id:
            continue
        lane_id = normalize_followup_lane_id(metadata.get("lane_id"))
        if not lane_id or lane_id in active_lane_ids:
            continue
        payload = dict(artifact.content or {}) if isinstance(artifact.content, dict) else {}
        payload["request_state"] = "superseded"
        payload["blocking_reason"] = "review_decision_replaced"
        metadata["request_state"] = "superseded"
        metadata["blocking_reason"] = "review_decision_replaced"
        store.update_artifact(
            artifact.id,
            content=payload,
            metadata=metadata,
        )

    return refs


def persist_followup_request_state(
    *,
    artifact: Artifact,
    request_state: str,
    actor_id: str = "",
    notes: str = "",
    execution_ref: Optional[Dict[str, Any]] = None,
    artifacts_store: Optional[Any] = None,
) -> Artifact:
    normalized_state = str(request_state or "").strip().lower()
    if normalized_state not in VALID_FOLLOWUP_REQUEST_STATES:
        raise ValueError(f"invalid_followup_request_state:{request_state}")
    metadata = dict(artifact.metadata or {}) if isinstance(artifact.metadata, dict) else {}
    if metadata.get("kind") != VISUAL_ACCEPTANCE_FOLLOWUP_ARTIFACT_KIND:
        raise ValueError("artifact_not_visual_acceptance_followup_request")

    content = dict(artifact.content or {}) if isinstance(artifact.content, dict) else {}
    content["lane_id"] = normalize_followup_lane_id(content.get("lane_id")) or None
    content["consumer_kind"] = (
        normalize_followup_consumer_kind(content.get("consumer_kind")) or None
    )
    content["action_ids"] = [
        normalize_followup_action_id(action_id)
        for action_id in (content.get("action_ids") or [])
        if normalize_followup_action_id(action_id)
    ]
    metadata["lane_id"] = normalize_followup_lane_id(metadata.get("lane_id")) or None
    metadata["consumer_kind"] = (
        normalize_followup_consumer_kind(metadata.get("consumer_kind")) or None
    )
    transition_event = {
        "request_state": normalized_state,
        "actor_id": str(actor_id or "").strip() or None,
        "notes": str(notes or "").strip() or None,
        "execution_ref": dict(execution_ref or {}),
        "handled_at": _utc_now_iso(),
    }
    history = [
        dict(item)
        for item in (content.get("request_events") or [])
        if isinstance(item, dict)
    ]
    history.append(transition_event)
    content["request_state"] = normalized_state
    content["blocking_reason"] = (
        content.get("blocking_reason")
        if normalized_state == FOLLOWUP_REQUEST_STATE_BLOCKED
        else None
    )
    content["request_events"] = history
    content["last_transition"] = transition_event
    metadata["request_state"] = normalized_state
    metadata["last_transition"] = transition_event
    if transition_event["actor_id"]:
        metadata["last_actor_id"] = transition_event["actor_id"]

    store = artifacts_store or get_visual_acceptance_artifacts_store()
    store.update_artifact(
        artifact.id,
        content=content,
        metadata=metadata,
    )
    updated_artifact = store.get_artifact(artifact.id)
    final_artifact = updated_artifact or artifact.model_copy(update={"content": content, "metadata": metadata})
    _sync_followup_request_state_to_bundle(
        request_artifact=final_artifact,
        request_content=content,
        transition_event=transition_event,
        artifacts_store=store,
    )
    _sync_followup_request_state_to_run(
        request_artifact=final_artifact,
        request_content=content,
        transition_event=transition_event,
    )
    refreshed = store.get_artifact(final_artifact.id)
    return refreshed or final_artifact


async def dispatch_followup_request(
    *,
    artifact: Artifact,
    actor_id: str = "",
    notes: str = "",
    artifacts_store: Optional[Any] = None,
) -> Dict[str, Any]:
    metadata = dict(artifact.metadata or {}) if isinstance(artifact.metadata, dict) else {}
    if metadata.get("kind") != VISUAL_ACCEPTANCE_FOLLOWUP_ARTIFACT_KIND:
        raise ValueError("artifact_not_visual_acceptance_followup_request")

    content = dict(artifact.content or {}) if isinstance(artifact.content, dict) else {}
    request_state = str(content.get("request_state") or "").strip().lower()
    if request_state != FOLLOWUP_REQUEST_STATE_READY:
        raise ValueError(f"followup_request_not_ready:{request_state or 'missing'}")

    lane_id = normalize_followup_lane_id(content.get("lane_id"))
    content["lane_id"] = lane_id or None
    content["consumer_kind"] = (
        normalize_followup_consumer_kind(content.get("consumer_kind")) or None
    )
    content["action_ids"] = [
        normalize_followup_action_id(action_id)
        for action_id in (content.get("action_ids") or [])
        if normalize_followup_action_id(action_id)
    ]
    workspace_id = str(content.get("workspace_id") or "").strip()
    if not workspace_id:
        raise ValueError("followup_request_missing_workspace_id")

    store = artifacts_store or get_visual_acceptance_artifacts_store()

    if lane_id == "rerender":
        storyboard = _build_single_scene_storyboard(content)
        source_type = _source_type_from_request(content)
        dispatch_payload = _dispatch_payload(
            request_content=content,
            dispatch_mode="execute_storyboard",
            dispatch_status="running",
            actor_id=actor_id,
            notes=notes,
            storyboard=storyboard,
        )
        dispatch_artifact = _upsert_dispatch_artifact(
            workspace_id=workspace_id,
            payload=dispatch_payload,
            artifacts_store=store,
        )

        try:
            try:
                from app.capabilities.multi_media_studio.tools.storyboard_execution import (
                    execute_storyboard,
                )
            except ImportError:
                from backend.app.capabilities.multi_media_studio.tools.storyboard_execution import (
                    execute_storyboard,
                )

            result = await execute_storyboard(
                project_id=_project_id_from_request(content),
                storyboard=storyboard,
                source_type=source_type,
                tenant_id="default",
            )
            result_payload = dict(result or {})
            dispatch_status = "completed"
            request_transition_state = FOLLOWUP_REQUEST_STATE_COMPLETED
            if not result_payload.get("success", False):
                dispatch_status = "failed"
                request_transition_state = FOLLOWUP_REQUEST_STATE_BLOCKED
            elif str(result_payload.get("status") or "").strip().lower() == "blocked":
                dispatch_status = "blocked"
                request_transition_state = FOLLOWUP_REQUEST_STATE_BLOCKED

            finalized_dispatch = dict(dispatch_payload)
            finalized_dispatch["dispatch_status"] = dispatch_status
            finalized_dispatch["dispatch_result"] = result_payload
            dispatch_artifact = _upsert_dispatch_artifact(
                workspace_id=workspace_id,
                payload=finalized_dispatch,
                artifacts_store=store,
            )
            updated_request = persist_followup_request_state(
                artifact=artifact,
                request_state=request_transition_state,
                actor_id=actor_id,
                notes=notes or f"rerender_{dispatch_status}",
                execution_ref={
                    "kind": VISUAL_ACCEPTANCE_FOLLOWUP_DISPATCH_ARTIFACT_KIND,
                    "artifact_id": dispatch_artifact.id,
                    "lane_id": lane_id,
                    "dispatch_status": dispatch_status,
                    "run_id": result_payload.get("run_id"),
                    "result_status": result_payload.get("status"),
                },
                artifacts_store=store,
            )
            return {
                "request_artifact": updated_request,
                "dispatch_artifact": dispatch_artifact,
                "dispatch_status": dispatch_status,
                "dispatch_result": result_payload,
            }
        except Exception as exc:
            failed_payload = dict(dispatch_payload)
            failed_payload["dispatch_status"] = "failed"
            failed_payload["dispatch_result"] = {"success": False, "error": str(exc)}
            dispatch_artifact = _upsert_dispatch_artifact(
                workspace_id=workspace_id,
                payload=failed_payload,
                artifacts_store=store,
            )
            updated_request = persist_followup_request_state(
                artifact=artifact,
                request_state=FOLLOWUP_REQUEST_STATE_BLOCKED,
                actor_id=actor_id,
                notes=notes or str(exc),
                execution_ref={
                    "kind": VISUAL_ACCEPTANCE_FOLLOWUP_DISPATCH_ARTIFACT_KIND,
                    "artifact_id": dispatch_artifact.id,
                    "lane_id": lane_id,
                    "dispatch_status": "failed",
                    "error": str(exc),
                },
                artifacts_store=store,
            )
            return {
                "request_artifact": updated_request,
                "dispatch_artifact": dispatch_artifact,
                "dispatch_status": "failed",
                "dispatch_result": {"success": False, "error": str(exc)},
            }

    if lane_id == "laf_patch":
        storyboard = _build_single_scene_storyboard(content)
        source_type = _source_type_from_request(content)
        project_id = _project_id_from_request(content)
        extract_request = _build_laf_patch_request(content)
        dispatch_payload = _dispatch_payload(
            request_content=content,
            dispatch_mode="extract_patch_execute_storyboard",
            dispatch_status="running",
            actor_id=actor_id,
            notes=notes,
            dispatch_result={"laf_extract_request": dict(extract_request)},
            storyboard=storyboard,
        )
        dispatch_artifact = _upsert_dispatch_artifact(
            workspace_id=workspace_id,
            payload=dispatch_payload,
            artifacts_store=store,
        )

        try:
            try:
                from app.capabilities.layer_asset_forge.api.layer_asset_forge_endpoints import (
                    ObjectExtractRequest,
                    extract_object_assets,
                )
            except ImportError:
                from backend.app.capabilities.layer_asset_forge.api.layer_asset_forge_endpoints import (
                    ObjectExtractRequest,
                    extract_object_assets,
                )

            try:
                from app.capabilities.multi_media_studio.tools.storyboard_execution import (
                    execute_storyboard,
                )
            except ImportError:
                from backend.app.capabilities.multi_media_studio.tools.storyboard_execution import (
                    execute_storyboard,
                )

            try:
                from app.capabilities.multi_media_studio.tools.storyboard_patch import (
                    apply_storyboard_scene_patch,
                )
            except ImportError:
                from backend.app.capabilities.multi_media_studio.tools.storyboard_patch import (
                    apply_storyboard_scene_patch,
                )

            extract_result = await extract_object_assets(
                request=ObjectExtractRequest(**extract_request),
                tenant_id="default",
            )
            extract_job = dict((extract_result or {}).get("job") or {})
            storyboard_scene_patch = (
                dict(extract_job.get("storyboard_scene_patch") or {})
                if isinstance(extract_job.get("storyboard_scene_patch"), dict)
                else {}
            )
            if not storyboard_scene_patch:
                raise ValueError("followup_dispatch_missing_storyboard_scene_patch")

            patched_result = await apply_storyboard_scene_patch(
                storyboard=storyboard,
                scene_id=str(content.get("scene_id") or "").strip(),
                storyboard_scene_patch=storyboard_scene_patch,
                tenant_id="default",
            )
            if not bool(patched_result.get("success")):
                raise ValueError(
                    str(patched_result.get("error") or "followup_dispatch_patch_failed")
                )
            patched_storyboard = (
                dict(patched_result.get("storyboard") or {})
                if isinstance(patched_result.get("storyboard"), dict)
                else {}
            )
            if not patched_storyboard:
                raise ValueError("followup_dispatch_missing_patched_storyboard")

            result = await execute_storyboard(
                project_id=project_id,
                storyboard=patched_storyboard,
                source_type=source_type,
                tenant_id="default",
            )
            result_payload = {
                "laf_extract_job_id": extract_job.get("job_id"),
                "laf_extract_status": extract_job.get("status"),
                "patched_scene_id": patched_result.get("patched_scene_id"),
                **dict(result or {}),
            }
            dispatch_status = "completed"
            request_transition_state = FOLLOWUP_REQUEST_STATE_COMPLETED
            if not result_payload.get("success", False):
                dispatch_status = "failed"
                request_transition_state = FOLLOWUP_REQUEST_STATE_BLOCKED
            elif str(result_payload.get("status") or "").strip().lower() == "blocked":
                dispatch_status = "blocked"
                request_transition_state = FOLLOWUP_REQUEST_STATE_BLOCKED

            finalized_dispatch = dict(dispatch_payload)
            finalized_dispatch["dispatch_status"] = dispatch_status
            finalized_dispatch["dispatch_result"] = result_payload
            finalized_dispatch["storyboard"] = patched_storyboard
            finalized_dispatch["laf_extract_request"] = dict(extract_request)
            finalized_dispatch["storyboard_scene_patch"] = storyboard_scene_patch
            dispatch_artifact = _upsert_dispatch_artifact(
                workspace_id=workspace_id,
                payload=finalized_dispatch,
                artifacts_store=store,
            )
            updated_request = persist_followup_request_state(
                artifact=artifact,
                request_state=request_transition_state,
                actor_id=actor_id,
                notes=notes or f"laf_patch_{dispatch_status}",
                execution_ref={
                    "kind": VISUAL_ACCEPTANCE_FOLLOWUP_DISPATCH_ARTIFACT_KIND,
                    "artifact_id": dispatch_artifact.id,
                    "lane_id": lane_id,
                    "dispatch_status": dispatch_status,
                    "laf_extract_job_id": extract_job.get("job_id"),
                    "run_id": result_payload.get("run_id"),
                    "result_status": result_payload.get("status"),
                },
                artifacts_store=store,
            )
            return {
                "request_artifact": updated_request,
                "dispatch_artifact": dispatch_artifact,
                "dispatch_status": dispatch_status,
                "dispatch_result": result_payload,
            }
        except Exception as exc:
            failed_payload = dict(dispatch_payload)
            failed_payload["dispatch_status"] = "failed"
            failed_payload["dispatch_result"] = {
                "success": False,
                "error": str(exc),
                "laf_extract_request": dict(extract_request),
            }
            dispatch_artifact = _upsert_dispatch_artifact(
                workspace_id=workspace_id,
                payload=failed_payload,
                artifacts_store=store,
            )
            updated_request = persist_followup_request_state(
                artifact=artifact,
                request_state=FOLLOWUP_REQUEST_STATE_BLOCKED,
                actor_id=actor_id,
                notes=notes or str(exc),
                execution_ref={
                    "kind": VISUAL_ACCEPTANCE_FOLLOWUP_DISPATCH_ARTIFACT_KIND,
                    "artifact_id": dispatch_artifact.id,
                    "lane_id": lane_id,
                    "dispatch_status": "failed",
                    "error": str(exc),
                },
                artifacts_store=store,
            )
            return {
                "request_artifact": updated_request,
                "dispatch_artifact": dispatch_artifact,
                "dispatch_status": "failed",
                "dispatch_result": {
                    "success": False,
                    "error": str(exc),
                    "laf_extract_request": dict(extract_request),
                },
            }

    if lane_id == FOLLOWUP_LANE_CAPABILITY_CONSUMER_HANDOFF:
        dispatch_result = _capability_owned_consumer_handoff_result(content)
        dispatch_payload = _dispatch_payload(
            request_content=content,
            dispatch_mode="consumer_handoff",
            dispatch_status="pending_worker",
            actor_id=actor_id,
            notes=notes,
            dispatch_result=dispatch_result,
        )
        dispatch_artifact = _upsert_dispatch_artifact(
            workspace_id=workspace_id,
            payload=dispatch_payload,
            artifacts_store=store,
        )
        updated_request = persist_followup_request_state(
            artifact=artifact,
            request_state=FOLLOWUP_REQUEST_STATE_DISPATCHED,
            actor_id=actor_id,
            notes=notes or "handoff_to_capability_owned_consumer",
            execution_ref={
                "kind": VISUAL_ACCEPTANCE_FOLLOWUP_DISPATCH_ARTIFACT_KIND,
                "artifact_id": dispatch_artifact.id,
                "lane_id": lane_id,
                "dispatch_status": "pending_worker",
                "dispatch_mode": "consumer_handoff",
            },
            artifacts_store=store,
        )
        return {
            "request_artifact": updated_request,
            "dispatch_artifact": dispatch_artifact,
            "dispatch_status": "pending_worker",
            "dispatch_result": dispatch_result,
        }

    if lane_id == "local_scene_review":
        bundle_content = _bundle_content_from_request(content, store)
        scene_review_request = _build_local_scene_review_request(
            request_content=content,
            bundle_content=bundle_content,
        )
        scene_review_artifact = _upsert_scene_review_artifact(
            workspace_id=workspace_id,
            payload=scene_review_request,
            artifacts_store=store,
        )
        dispatch_payload = _dispatch_payload(
            request_content=content,
            dispatch_mode="manual_scene_review_queue",
            dispatch_status="queued",
            actor_id=actor_id,
            notes=notes,
            dispatch_result={
                "success": True,
                "mode": "manual_scene_review_queue",
                "scene_review_artifact_id": scene_review_artifact.id,
                "scene_review_request": scene_review_request,
                "execution_strategy": "workspace_artifact_manual_queue",
            },
        )
        dispatch_artifact = _upsert_dispatch_artifact(
            workspace_id=workspace_id,
            payload=dispatch_payload,
            artifacts_store=store,
        )
        updated_request = persist_followup_request_state(
            artifact=artifact,
            request_state=FOLLOWUP_REQUEST_STATE_DISPATCHED,
            actor_id=actor_id,
            notes=notes or "queued_to_local_scene_review",
            execution_ref={
                "kind": VISUAL_ACCEPTANCE_FOLLOWUP_DISPATCH_ARTIFACT_KIND,
                "artifact_id": dispatch_artifact.id,
                "lane_id": lane_id,
                "dispatch_status": "queued",
                "dispatch_mode": "manual_scene_review_queue",
                "scene_review_artifact_id": scene_review_artifact.id,
            },
            artifacts_store=store,
        )
        return {
            "request_artifact": updated_request,
            "dispatch_artifact": dispatch_artifact,
            "consumer_artifact": scene_review_artifact,
            "dispatch_status": "queued",
            "dispatch_result": {
                "success": True,
                "mode": "manual_scene_review_queue",
                "scene_review_artifact_id": scene_review_artifact.id,
                "scene_review_request": scene_review_request,
                "execution_strategy": "workspace_artifact_manual_queue",
            },
        }

    raise ValueError(f"unsupported_followup_lane:{lane_id or 'missing'}")
