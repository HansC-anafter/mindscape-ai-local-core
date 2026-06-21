"""Build visual acceptance bundle payloads."""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

from .constants import REVIEW_STATUS_PENDING, SOURCE_KIND_VR_RENDER
from .dependencies import (
    build_review_checklist_template,
    resolve_explicit_owner_capability_code,
)
from .normalizers import (
    bounded_identifier,
    field_value,
    jsonable,
    safe_segment,
    utc_now_iso,
)
from .slots import collect_lineage, collect_object_asset_slots, collect_render_slots


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
    scene_id = str(field_value(scene, "scene_id", "") or "").strip() or "scene"
    review_bundle_id = bounded_identifier(
        (
            f"vrb_{safe_segment(run_id, 'run')}"
            f"_{safe_segment(scene_id, 'scene')}"
            f"_{safe_segment(source_kind, 'source')}"
        ),
        "vrb_bundle",
    )
    snapshot = field_value(scene, "object_workload_snapshot", None)
    snapshot_payload = jsonable(snapshot) if snapshot is not None else None
    scene_manifest = jsonable(field_value(scene, "scene_manifest", {}) or {})
    lineage = collect_lineage(context_metadata)
    slots = collect_object_asset_slots(scene, tenant_id=tenant_id)
    slots.extend(collect_render_slots(list(clip_refs or []), tenant_id=tenant_id))

    source_kind_value = str(source_kind or "").strip() or SOURCE_KIND_VR_RENDER
    owning_capability_code = resolve_explicit_owner_capability_code(
        context_metadata=context_metadata,
    )
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
        "owning_capability_code": owning_capability_code,
        "package_id": lineage.get("package_id"),
        "preset_id": lineage.get("preset_id"),
        "artifact_ids": list(lineage.get("artifact_ids") or []),
        "checklist_template": build_review_checklist_template(source_kind_value),
        "scene_context": {
            "scene_payload": jsonable(scene),
            "scene_manifest": scene_manifest,
            "object_workload_snapshot": snapshot_payload,
        },
        "source_metadata": jsonable(context_metadata or {}),
        "slots": slots,
        "created_at": utc_now_iso(),
    }
