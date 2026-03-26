"""
Visual acceptance bundle helpers.

This module creates a compare-ready manifest and lands it as a workspace
artifact when possible. The first rollout keeps the contract lightweight:
JSON manifest on disk + artifact metadata/content for downstream UI.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

try:
    from app.models.workspace import Artifact, ArtifactType, PrimaryActionType
    from app.services.artifact_review_decision import (
        FOLLOWUP_PLAN_PACK_CONSUMER_HANDOFF_READY,
        build_followup_action_plan,
        build_review_checklist_template,
        normalize_review_checklist_scores,
    )
    from app.services.visual_acceptance_followup_requests import (
        materialize_followup_request_artifacts,
    )
    from app.services.stores.postgres.artifacts_store import PostgresArtifactsStore
except ImportError:
    from backend.app.models.workspace import Artifact, ArtifactType, PrimaryActionType
    from backend.app.services.artifact_review_decision import (
        FOLLOWUP_PLAN_PACK_CONSUMER_HANDOFF_READY,
        build_followup_action_plan,
        build_review_checklist_template,
        normalize_review_checklist_scores,
    )
    from backend.app.services.visual_acceptance_followup_requests import (
        materialize_followup_request_artifacts,
    )
    from backend.app.services.stores.postgres.artifacts_store import (
        PostgresArtifactsStore,
    )

logger = logging.getLogger(__name__)

VISUAL_ACCEPTANCE_ARTIFACT_KIND = "visual_acceptance_bundle"
VISUAL_ACCEPTANCE_PLAYBOOK_CODE = "visual_acceptance_review"

REVIEW_STATUS_PENDING = "pending_review"
SOURCE_KIND_LAF_PATCH = "laf_patch"
SOURCE_KIND_VR_RENDER = "vr_render"
SOURCE_KIND_CHARACTER_TRAINING_EVAL = "character_training_eval"
SOURCE_KIND_CHARACTER_PERFORMANCE_EVAL = "character_performance_eval"
SOURCE_KIND_PORTRAIT_ANIMATION_EVAL = "portrait_animation_eval"
SOURCE_KIND_TALKING_HEAD_EVAL = "talking_head_eval"

LINEAGE_KEYS = ("package_id", "preset_id", "binding_mode")
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
VIDEO_EXTS = {".mp4", ".mov", ".webm", ".m4v"}
JSON_EXTS = {".json"}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().isoformat()


def _storage_base() -> Path:
    return Path(os.getenv("LOCAL_STORAGE_PATH", "/tmp/vcs-storage"))


def get_visual_acceptance_artifacts_store() -> PostgresArtifactsStore:
    return PostgresArtifactsStore()


def _safe_segment(value: str, fallback: str) -> str:
    candidate = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "").strip())
    return candidate or fallback


def _enum_value(value: Any) -> Any:
    if hasattr(value, "value"):
        return getattr(value, "value")
    return value


def _jsonable(value: Any) -> Any:
    value = _enum_value(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "model_dump"):
        return _jsonable(value.model_dump())
    if hasattr(value, "dict"):
        return _jsonable(value.dict())
    return str(value)


def _field_value(obj: Any, field: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(field, default)
    return getattr(obj, field, default)


def _normalized_storage_key(value: Any) -> str:
    return str(value or "").strip().lstrip("/")


def _preview_kind(storage_key: str) -> Optional[str]:
    key = _normalized_storage_key(storage_key)
    if not key:
        return None
    suffix = Path(key).suffix.lower()
    if suffix in IMAGE_EXTS:
        return "image"
    if suffix in VIDEO_EXTS:
        return "video"
    if suffix in JSON_EXTS:
        return "json"
    return "binary"


def _storage_capability(slot_name: str, storage_key: str) -> str:
    key = _normalized_storage_key(storage_key)
    if key.startswith("video_renderer/"):
        return "video_renderer"
    if key.startswith("layer_asset_forge/"):
        return "layer_asset_forge"
    return "video_renderer" if slot_name == "final_render" else "layer_asset_forge"


def _preview_url(*, tenant_id: str, slot_name: str, storage_key: Any) -> Optional[str]:
    key = _normalized_storage_key(storage_key)
    if not key:
        return None
    capability = _storage_capability(slot_name, key)
    tenant = _safe_segment(tenant_id, "default")
    return f"/api/v1/capabilities/{capability}/storage/{tenant}/{key}"


def _with_preview_refs(slot: Dict[str, Any], *, tenant_id: str) -> Dict[str, Any]:
    enriched = dict(slot)
    slot_name = str(enriched.get("slot") or "").strip()
    for field_name, preview_prefix in (
        ("storage_key", "preview"),
        ("mask_storage_key", "mask_preview"),
        ("alpha_storage_key", "alpha_preview"),
    ):
        key = _normalized_storage_key(enriched.get(field_name))
        if not key:
            continue
        enriched[field_name] = key
        enriched[f"{preview_prefix}_url"] = _preview_url(
            tenant_id=tenant_id,
            slot_name=slot_name,
            storage_key=key,
        )
        enriched[f"{preview_prefix}_kind"] = _preview_kind(key)
    return enriched


def _normalize_clip_ref(ref: Any) -> Dict[str, Any]:
    if isinstance(ref, dict):
        return dict(ref)
    if hasattr(ref, "model_dump"):
        dumped = ref.model_dump()
        return dumped if isinstance(dumped, dict) else {}
    normalized: Dict[str, Any] = {}
    storage_key = getattr(ref, "storage_key", None)
    if storage_key:
        normalized["storage_key"] = storage_key
    metadata = getattr(ref, "metadata", None)
    if isinstance(metadata, dict):
        normalized["metadata"] = metadata
    return normalized


def _collect_object_asset_slots(scene: Any, *, tenant_id: str) -> List[Dict[str, Any]]:
    slots: List[Dict[str, Any]] = []
    assets = _field_value(scene, "object_assets", []) or []
    for index, asset in enumerate(assets):
        payload = _jsonable(asset)
        if not isinstance(payload, dict):
            continue
        asset_ref = payload.get("asset_ref")
        storage_key = ""
        if isinstance(asset_ref, dict):
            storage_key = str(asset_ref.get("storage_key") or "").strip()
        storage_key = storage_key or str(payload.get("storage_key") or "").strip()
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        mask_storage_key = metadata.get("mask_storage_key")
        alpha_storage_key = metadata.get("alpha_storage_key")
        if not storage_key and not mask_storage_key and not alpha_storage_key:
            continue
        slots.append(
            _with_preview_refs(
                {
                    "slot": "final_layer",
                    "index": index,
                    "label": str(
                        payload.get("object_target_id")
                        or payload.get("object_instance_id")
                        or f"layer_{index}"
                    ),
                    "storage_key": storage_key or None,
                    "mask_storage_key": mask_storage_key,
                    "alpha_storage_key": alpha_storage_key,
                    "source_reference_fingerprint": payload.get("source_reference_fingerprint"),
                    "metadata": metadata,
                },
                tenant_id=tenant_id,
            )
        )
    return slots


def _collect_render_slots(clip_refs: Iterable[Any], *, tenant_id: str) -> List[Dict[str, Any]]:
    slots: List[Dict[str, Any]] = []
    for index, ref in enumerate(clip_refs):
        payload = _normalize_clip_ref(ref)
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        slots.append(
            _with_preview_refs(
                {
                    "slot": "final_render",
                    "index": index,
                    "storage_key": payload.get("storage_key"),
                    "metadata": metadata,
                },
                tenant_id=tenant_id,
            )
        )
    return slots


def _collect_lineage(context_metadata: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    metadata = dict(context_metadata or {})
    lineage: Dict[str, Any] = {key: str(metadata.get(key) or "").strip() or None for key in LINEAGE_KEYS}
    artifact_ids: List[str] = []
    for key in ("artifact_ids", "artifact_id"):
        value = metadata.get(key)
        if isinstance(value, list):
            for item in value:
                normalized = str(item or "").strip()
                if normalized and normalized not in artifact_ids:
                    artifact_ids.append(normalized)
        else:
            normalized = str(value or "").strip()
            if normalized and normalized not in artifact_ids:
                artifact_ids.append(normalized)
    lineage["artifact_ids"] = artifact_ids
    lineage["vr_commit_id"] = str(metadata.get("vr_commit_id") or "").strip() or None
    lineage["prompt_id"] = str(metadata.get("prompt_id") or "").strip() or None
    return lineage


def build_visual_acceptance_bundle(
    *,
    tenant_id: str,
    project_id: str,
    run_id: str,
    workspace_id: str,
    scene: Any,
    source_kind: str,
    render_status: str,
    renderer: str,
    clip_refs: Optional[Iterable[Any]] = None,
    context_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a minimal compare-ready bundle manifest."""

    scene_id = str(_field_value(scene, "scene_id", "") or "").strip() or "scene"
    review_bundle_id = (
        f"vrb_{_safe_segment(run_id, 'run')}_{_safe_segment(scene_id, 'scene')}_{_safe_segment(source_kind, 'source')}"
    )
    snapshot = _field_value(scene, "object_workload_snapshot", None)
    snapshot_payload = _jsonable(snapshot) if snapshot is not None else None
    scene_manifest = _jsonable(_field_value(scene, "scene_manifest", {}) or {})
    lineage = _collect_lineage(context_metadata)
    slots = _collect_object_asset_slots(scene, tenant_id=tenant_id)
    slots.extend(_collect_render_slots(list(clip_refs or []), tenant_id=tenant_id))

    source_kind_value = str(source_kind or "").strip() or SOURCE_KIND_VR_RENDER
    return {
        "review_bundle_id": review_bundle_id,
        "workspace_id": str(workspace_id or "").strip(),
        "tenant_id": str(tenant_id or "").strip(),
        "project_id": str(project_id or "").strip(),
        "run_id": str(run_id or "").strip(),
        "scene_id": scene_id,
        "source_kind": source_kind_value,
        "status": REVIEW_STATUS_PENDING,
        "render_status": str(render_status or "").strip() or "unknown",
        "renderer": str(renderer or "").strip() or "unknown",
        "binding_mode": lineage.get("binding_mode"),
        "package_id": lineage.get("package_id"),
        "preset_id": lineage.get("preset_id"),
        "artifact_ids": list(lineage.get("artifact_ids") or []),
        "checklist_template": build_review_checklist_template(source_kind_value),
        "scene_context": {
            "scene_payload": _jsonable(scene),
            "scene_manifest": scene_manifest,
            "object_workload_snapshot": snapshot_payload,
        },
        "source_metadata": _jsonable(context_metadata or {}),
        "slots": slots,
        "created_at": _utc_now_iso(),
    }


def _bundle_manifest_path(
    *, tenant_id: str, project_id: str, run_id: str, scene_id: str, review_bundle_id: str
) -> Path:
    project_segment = _safe_segment(project_id, "project")
    run_segment = _safe_segment(run_id, "run")
    scene_segment = _safe_segment(scene_id, "scene")
    file_name = f"{_safe_segment(review_bundle_id, 'bundle')}.json"
    return (
        _storage_base()
        / _safe_segment(tenant_id, "default")
        / "multi_media_studio"
        / "projects"
        / project_segment
        / "visual_acceptance"
        / run_segment
        / scene_segment
        / file_name
    )


def _artifact_metadata(bundle: Dict[str, Any], manifest_path: str) -> Dict[str, Any]:
    return {
        "kind": VISUAL_ACCEPTANCE_ARTIFACT_KIND,
        "review_bundle_id": bundle["review_bundle_id"],
        "run_id": bundle["run_id"],
        "scene_id": bundle["scene_id"],
        "source_kind": bundle["source_kind"],
        "visual_acceptance_state": bundle["status"],
        "package_id": bundle.get("package_id"),
        "preset_id": bundle.get("preset_id"),
        "artifact_ids": bundle.get("artifact_ids", []),
        "binding_mode": bundle.get("binding_mode"),
        "manifest_path": manifest_path,
    }


def _write_bundle_manifest(bundle: Dict[str, Any], manifest_path: Path) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _load_bundle_manifest(manifest_path: str) -> Optional[Dict[str, Any]]:
    candidate = Path(str(manifest_path or "").strip())
    if not candidate.exists():
        return None
    try:
        return json.loads(candidate.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("failed to load visual acceptance bundle manifest: %s", candidate, exc_info=True)
        return None


def _upsert_bundle_artifact(
    *,
    workspace_id: str,
    bundle: Dict[str, Any],
    manifest_path: Path,
) -> Optional[str]:
    if not workspace_id:
        return None
    artifact_id = bundle["review_bundle_id"]
    metadata = _artifact_metadata(bundle, str(manifest_path))
    artifact = Artifact(
        id=artifact_id,
        workspace_id=workspace_id,
        execution_id=f"visual_acceptance:{bundle['run_id']}:{bundle['scene_id']}",
        playbook_code=VISUAL_ACCEPTANCE_PLAYBOOK_CODE,
        artifact_type=ArtifactType.DATA,
        title=f"Visual Acceptance Bundle: {bundle['scene_id']}",
        summary=(
            f"Visual acceptance bundle for scene {bundle['scene_id']} "
            f"({bundle['source_kind']}, {bundle['render_status']})"
        ),
        content=bundle,
        storage_ref=str(manifest_path),
        primary_action_type=PrimaryActionType.DOWNLOAD,
        metadata=metadata,
    )
    store = get_visual_acceptance_artifacts_store()
    existing = store.get_artifact(artifact_id)
    if existing:
        store.update_artifact(
            artifact_id,
            title=artifact.title,
            summary=artifact.summary,
            content=artifact.content,
            storage_ref=artifact.storage_ref,
            metadata=artifact.metadata,
            artifact_type=artifact.artifact_type,
            primary_action_type=artifact.primary_action_type,
        )
    else:
        store.create_artifact(artifact)
    return artifact_id


def publish_visual_acceptance_bundle(
    *,
    tenant_id: str,
    project_id: str,
    run_id: str,
    workspace_id: str,
    scene: Any,
    source_kind: str,
    render_status: str,
    renderer: str,
    clip_refs: Optional[Iterable[Any]] = None,
    context_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Persist a visual acceptance bundle manifest and return a stable ref."""

    bundle = build_visual_acceptance_bundle(
        tenant_id=tenant_id,
        project_id=project_id,
        run_id=run_id,
        workspace_id=workspace_id,
        scene=scene,
        source_kind=source_kind,
        render_status=render_status,
        renderer=renderer,
        clip_refs=clip_refs,
        context_metadata=context_metadata,
    )
    manifest_path = _bundle_manifest_path(
        tenant_id=tenant_id,
        project_id=project_id,
        run_id=run_id,
        scene_id=bundle["scene_id"],
        review_bundle_id=bundle["review_bundle_id"],
    )
    _write_bundle_manifest(bundle, manifest_path)

    artifact_id: Optional[str] = None
    try:
        artifact_id = _upsert_bundle_artifact(
            workspace_id=str(workspace_id or "").strip(),
            bundle=bundle,
            manifest_path=manifest_path,
        )
    except Exception:
        logger.warning(
            "visual acceptance bundle artifact landing failed run=%s scene=%s",
            run_id,
            bundle["scene_id"],
            exc_info=True,
        )

    return {
        "kind": VISUAL_ACCEPTANCE_ARTIFACT_KIND,
        "review_bundle_id": bundle["review_bundle_id"],
        "artifact_id": artifact_id,
        "manifest_path": str(manifest_path),
        "scene_id": bundle["scene_id"],
        "run_id": bundle["run_id"],
        "status": bundle["status"],
        "source_kind": bundle["source_kind"],
        "package_id": bundle.get("package_id"),
        "preset_id": bundle.get("preset_id"),
        "artifact_ids": bundle.get("artifact_ids", []),
        "binding_mode": bundle.get("binding_mode"),
    }


def load_visual_acceptance_bundle_for_artifact(artifact: Artifact) -> Dict[str, Any]:
    """Load the canonical bundle payload for a landed visual acceptance artifact."""

    content = dict(artifact.content or {}) if isinstance(artifact.content, dict) else {}
    metadata = dict(artifact.metadata or {}) if isinstance(artifact.metadata, dict) else {}
    manifest_payload = _load_bundle_manifest(str(metadata.get("manifest_path") or ""))
    if manifest_payload:
        return manifest_payload
    return content


def _sync_review_decision_to_run(
    *,
    bundle: Dict[str, Any],
    artifact_id: str,
    decision_payload: Dict[str, Any],
) -> None:
    tenant_id = str(bundle.get("tenant_id") or "").strip() or "default"
    project_id = str(bundle.get("project_id") or "").strip()
    run_id = str(bundle.get("run_id") or "").strip()
    scene_id = str(bundle.get("scene_id") or "").strip()
    if not project_id or not run_id or not scene_id:
        return

    try:
        try:
            from app.capabilities.multi_media_studio.models import production_run
        except ImportError:
            from backend.app.capabilities.multi_media_studio.models import production_run

        followup_actions = [
            str(item or "").strip()
            for item in (decision_payload.get("followup_actions") or [])
            if str(item or "").strip()
        ]
        followup_request_refs = [
            dict(item)
            for item in (decision_payload.get("followup_request_refs") or [])
            if isinstance(item, dict)
        ]
        downstream_action_plan = (
            dict(decision_payload.get("downstream_action_plan") or {})
            if isinstance(decision_payload.get("downstream_action_plan"), dict)
            else build_followup_action_plan(
                review_bundle_id=str(bundle.get("review_bundle_id") or artifact_id),
                decision=str(decision_payload.get("decision") or ""),
                run_id=run_id,
                scene_id=scene_id,
                source_kind=str(bundle.get("source_kind") or ""),
                package_id=str(bundle.get("package_id") or ""),
                preset_id=str(bundle.get("preset_id") or ""),
                artifact_ids=bundle.get("artifact_ids") or [],
                binding_mode=str(bundle.get("binding_mode") or ""),
                followup_actions=followup_actions,
            )
        )
        run = production_run.get_run(tenant_id, project_id, run_id)
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
            provider_metadata["visual_acceptance_state"] = decision_payload["decision"]
            provider_metadata["review_decision_ref"] = {
                "artifact_id": artifact_id,
                "decision": decision_payload["decision"],
                "reviewed_at": decision_payload["reviewed_at"],
                "reviewer_id": str(decision_payload.get("reviewer_id") or "").strip() or None,
                "followup_actions": followup_actions,
                "downstream_action_plan": downstream_action_plan,
                "followup_request_refs": followup_request_refs,
            }
            provider_metadata["downstream_action_plan"] = downstream_action_plan
            provider_metadata["followup_request_refs"] = followup_request_refs
            bundle_refs = provider_metadata.get("review_bundle_refs")
            updated_refs: List[Dict[str, Any]] = []
            for bundle_ref in bundle_refs or []:
                if not isinstance(bundle_ref, dict):
                    continue
                item = dict(bundle_ref)
                if str(item.get("artifact_id") or "").strip() == artifact_id:
                    item["status"] = decision_payload["decision"]
                    item["review_decision"] = {
                        "decision": decision_payload["decision"],
                        "reviewed_at": decision_payload["reviewed_at"],
                        "reviewer_id": str(decision_payload.get("reviewer_id") or "").strip() or None,
                        "followup_actions": followup_actions,
                        "downstream_action_plan": downstream_action_plan,
                        "followup_request_refs": followup_request_refs,
                    }
                    item["downstream_action_plan"] = downstream_action_plan
                    item["followup_request_refs"] = followup_request_refs
                updated_refs.append(item)
            if updated_refs:
                provider_metadata["review_bundle_refs"] = updated_refs
            scene_result["provider_metadata"] = provider_metadata
            updated = True
            break
        if updated:
            run["updated_at"] = _utc_now_iso()
            production_run._save_run(tenant_id, project_id, run)  # type: ignore[attr-defined]
    except Exception:
        logger.warning(
            "failed to sync visual acceptance review decision to run run=%s scene=%s",
            run_id,
            scene_id,
            exc_info=True,
        )


def persist_visual_acceptance_review_decision(
    *,
    artifact: Artifact,
    decision_payload: Dict[str, Any],
    artifacts_store: Optional[PostgresArtifactsStore] = None,
) -> Artifact:
    """Persist a review decision into artifact content/metadata and bundle manifest."""

    bundle = load_visual_acceptance_bundle_for_artifact(artifact)
    metadata = dict(artifact.metadata or {}) if isinstance(artifact.metadata, dict) else {}
    content = dict(bundle or {})
    content["workspace_id"] = str(content.get("workspace_id") or artifact.workspace_id or "").strip()
    checklist_template = content.get("checklist_template")
    normalized_scores = normalize_review_checklist_scores(
        decision_payload.get("checklist_scores") if isinstance(decision_payload, dict) else None,
        checklist_template=checklist_template if isinstance(checklist_template, list) else None,
    )
    decision_payload = dict(decision_payload)
    decision_payload["checklist_scores"] = normalized_scores
    decision_payload["checklist_summary"] = {
        "scored_checks": len(normalized_scores),
        "average_score": (
            round(sum(normalized_scores.values()) / len(normalized_scores), 3)
            if normalized_scores
            else None
        ),
    }
    downstream_action_plan = build_followup_action_plan(
        review_bundle_id=str(
            content.get("review_bundle_id")
            or decision_payload.get("review_bundle_id")
            or artifact.id
        ),
        decision=str(decision_payload.get("decision") or ""),
        run_id=str(content.get("run_id") or ""),
        scene_id=str(content.get("scene_id") or ""),
        source_kind=str(content.get("source_kind") or ""),
        package_id=str(content.get("package_id") or ""),
        preset_id=str(content.get("preset_id") or ""),
        artifact_ids=content.get("artifact_ids") or [],
        binding_mode=str(content.get("binding_mode") or ""),
        followup_actions=decision_payload.get("followup_actions"),
    )
    decision_payload["downstream_action_plan"] = downstream_action_plan
    history = content.get("review_decisions")
    history_items = [dict(item) for item in history if isinstance(item, dict)] if isinstance(history, list) else []
    history_items.append(dict(decision_payload))
    content["review_decisions"] = history_items
    content["latest_review_decision"] = dict(decision_payload)
    content["status"] = decision_payload["decision"]
    content["downstream_action_plan"] = dict(downstream_action_plan)

    metadata["visual_acceptance_state"] = decision_payload["decision"]
    metadata["review_decision"] = dict(decision_payload)
    metadata["review_decision_count"] = len(history_items)
    metadata["followup_action_ids"] = list(downstream_action_plan.get("action_ids") or [])
    metadata["downstream_lane_ids"] = list(downstream_action_plan.get("lane_ids") or [])
    metadata[FOLLOWUP_PLAN_PACK_CONSUMER_HANDOFF_READY] = bool(
        downstream_action_plan.get(FOLLOWUP_PLAN_PACK_CONSUMER_HANDOFF_READY)
    )

    manifest_path = str(metadata.get("manifest_path") or "").strip()
    if manifest_path:
        _write_bundle_manifest(content, Path(manifest_path))

    store = artifacts_store or get_visual_acceptance_artifacts_store()
    store.update_artifact(
        artifact.id,
        content=content,
        metadata=metadata,
    )
    updated_artifact = store.get_artifact(artifact.id)
    final_artifact = updated_artifact or artifact.model_copy(update={"content": content, "metadata": metadata})
    followup_request_refs = materialize_followup_request_artifacts(
        bundle=content,
        decision_payload=decision_payload,
        artifacts_store=store,
    )
    decision_payload["followup_request_refs"] = followup_request_refs
    content["latest_review_decision"] = dict(decision_payload)
    content["review_decisions"][-1] = dict(decision_payload)
    content["followup_request_refs"] = followup_request_refs
    metadata["followup_request_count"] = len(followup_request_refs)
    if manifest_path:
        _write_bundle_manifest(content, Path(manifest_path))
    store.update_artifact(
        artifact.id,
        content=content,
        metadata=metadata,
    )
    updated_artifact = store.get_artifact(artifact.id)
    final_artifact = updated_artifact or artifact.model_copy(
        update={"content": content, "metadata": metadata}
    )
    _sync_review_decision_to_run(
        bundle=content,
        artifact_id=artifact.id,
        decision_payload=decision_payload,
    )
    return final_artifact
