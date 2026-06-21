"""Manifest and artifact persistence for visual acceptance bundles."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from .builder import build_visual_acceptance_bundle
from .constants import VISUAL_ACCEPTANCE_ARTIFACT_KIND, VISUAL_ACCEPTANCE_PLAYBOOK_CODE
from .dependencies import Artifact, ArtifactType, PrimaryActionType
from .normalizers import (
    bounded_execution_id,
    get_visual_acceptance_artifacts_store,
    safe_segment,
    storage_base,
)

logger = logging.getLogger("backend.app.services.visual_acceptance_bundle")


def bundle_manifest_path(
    *, tenant_id: str, project_id: str, run_id: str, scene_id: str, review_bundle_id: str
) -> Path:
    project_segment = safe_segment(project_id, "project")
    run_segment = safe_segment(run_id, "run")
    scene_segment = safe_segment(scene_id, "scene")
    file_name = f"{safe_segment(review_bundle_id, 'bundle')}.json"
    return (
        storage_base()
        / safe_segment(tenant_id, "default")
        / "multi_media_studio"
        / "projects"
        / project_segment
        / "visual_acceptance"
        / run_segment
        / scene_segment
        / file_name
    )


def artifact_metadata(bundle: Dict[str, Any], manifest_path: str) -> Dict[str, Any]:
    return {
        "kind": VISUAL_ACCEPTANCE_ARTIFACT_KIND,
        "review_bundle_id": bundle["review_bundle_id"],
        "run_id": bundle["run_id"],
        "scene_id": bundle["scene_id"],
        "source_kind": bundle["source_kind"],
        "visual_acceptance_state": bundle["status"],
        "owning_capability_code": bundle.get("owning_capability_code"),
        "package_id": bundle.get("package_id"),
        "preset_id": bundle.get("preset_id"),
        "artifact_ids": bundle.get("artifact_ids", []),
        "binding_mode": bundle.get("binding_mode"),
        "manifest_path": manifest_path,
    }


def write_bundle_manifest(bundle: Dict[str, Any], manifest_path: Path) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_bundle_manifest(manifest_path: str) -> Optional[Dict[str, Any]]:
    candidate = Path(str(manifest_path or "").strip())
    if not candidate.exists():
        return None
    try:
        return json.loads(candidate.read_text(encoding="utf-8"))
    except Exception:
        logger.warning(
            "failed to load visual acceptance bundle manifest: %s",
            candidate,
            exc_info=True,
        )
        return None


def upsert_bundle_artifact(
    *,
    workspace_id: str,
    bundle: Dict[str, Any],
    manifest_path: Path,
) -> Optional[str]:
    if not workspace_id:
        return None
    artifact_id = bundle["review_bundle_id"]
    metadata = artifact_metadata(bundle, str(manifest_path))
    artifact = Artifact(
        id=artifact_id,
        workspace_id=workspace_id,
        execution_id=bounded_execution_id(
            f"visual_acceptance:{bundle['run_id']}:{bundle['scene_id']}",
            "visual_acceptance",
        ),
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
    manifest_path = bundle_manifest_path(
        tenant_id=tenant_id,
        project_id=project_id,
        run_id=run_id,
        scene_id=bundle["scene_id"],
        review_bundle_id=bundle["review_bundle_id"],
    )
    write_bundle_manifest(bundle, manifest_path)

    artifact_id: Optional[str] = None
    try:
        artifact_id = upsert_bundle_artifact(
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
        "owning_capability_code": bundle.get("owning_capability_code"),
        "package_id": bundle.get("package_id"),
        "preset_id": bundle.get("preset_id"),
        "artifact_ids": bundle.get("artifact_ids", []),
        "binding_mode": bundle.get("binding_mode"),
    }


def load_visual_acceptance_bundle_for_artifact(artifact: Artifact) -> Dict[str, Any]:
    """Load the canonical bundle payload for a landed visual acceptance artifact."""
    content = dict(artifact.content or {}) if isinstance(artifact.content, dict) else {}
    metadata = dict(artifact.metadata or {}) if isinstance(artifact.metadata, dict) else {}
    manifest_payload = load_bundle_manifest(str(metadata.get("manifest_path") or ""))
    if manifest_payload:
        return manifest_payload
    return content
