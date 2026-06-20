"""Artifact store and upsert helpers for visual acceptance follow-up artifacts."""

from typing import Any, Dict, List

from .constants import (
    VISUAL_ACCEPTANCE_FOLLOWUP_DISPATCH_ARTIFACT_KIND,
    VISUAL_ACCEPTANCE_FOLLOWUP_DISPATCH_PLAYBOOK_CODE,
    VISUAL_ACCEPTANCE_FOLLOWUP_PLAYBOOK_CODE,
    VISUAL_ACCEPTANCE_SCENE_REVIEW_ARTIFACT_KIND,
    VISUAL_ACCEPTANCE_SCENE_REVIEW_PLAYBOOK_CODE,
)
from .dependencies import Artifact, ArtifactType, PostgresArtifactsStore, PrimaryActionType
from .identifiers import _bounded_execution_id
from .request_payloads import _request_metadata


def get_visual_acceptance_artifacts_store() -> PostgresArtifactsStore:
    return PostgresArtifactsStore()


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
