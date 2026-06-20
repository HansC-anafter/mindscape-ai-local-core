"""Layer Asset Forge request builders for visual follow-up dispatch."""

import uuid
from typing import Any, Dict, List

from .dispatch_payloads import _scene_payload_from_request
from .identifiers import _safe_segment


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
