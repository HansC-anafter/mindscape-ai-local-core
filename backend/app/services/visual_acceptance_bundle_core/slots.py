"""Slot and lineage collection for visual acceptance bundles."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from .constants import LINEAGE_KEYS
from .normalizers import (
    field_value,
    jsonable,
    normalize_clip_ref,
    with_preview_refs,
)


def collect_object_asset_slots(scene: Any, *, tenant_id: str) -> List[Dict[str, Any]]:
    slots: List[Dict[str, Any]] = []
    assets = field_value(scene, "object_assets", []) or []
    for index, asset in enumerate(assets):
        payload = jsonable(asset)
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
            with_preview_refs(
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
                    "source_reference_fingerprint": payload.get(
                        "source_reference_fingerprint"
                    ),
                    "metadata": metadata,
                },
                tenant_id=tenant_id,
            )
        )
    return slots


def collect_render_slots(
    clip_refs: Iterable[Any], *, tenant_id: str
) -> List[Dict[str, Any]]:
    slots: List[Dict[str, Any]] = []
    for index, ref in enumerate(clip_refs):
        payload = normalize_clip_ref(ref)
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        slots.append(
            with_preview_refs(
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


def collect_lineage(context_metadata: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    metadata = dict(context_metadata or {})
    lineage: Dict[str, Any] = {
        key: str(metadata.get(key) or "").strip() or None for key in LINEAGE_KEYS
    }
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
