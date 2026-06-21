"""Pure normalization helpers for visual acceptance bundles."""

from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from .constants import IMAGE_EXTS, JSON_EXTS, MAX_ARTIFACT_ID_LENGTH, VIDEO_EXTS
from .dependencies import PostgresArtifactsStore


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat()


def storage_base() -> Path:
    return Path(os.getenv("LOCAL_STORAGE_PATH", "/tmp/vcs-storage"))


def get_visual_acceptance_artifacts_store() -> PostgresArtifactsStore:
    return PostgresArtifactsStore()


def safe_segment(value: str, fallback: str) -> str:
    candidate = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "").strip())
    return candidate or fallback


def bounded_identifier(value: str, fallback: str) -> str:
    candidate = safe_segment(value, fallback)
    if len(candidate) <= MAX_ARTIFACT_ID_LENGTH:
        return candidate
    digest = hashlib.sha1(candidate.encode("utf-8")).hexdigest()[:12]
    head = candidate[: MAX_ARTIFACT_ID_LENGTH - len(digest) - 1].rstrip("_")
    return f"{head}_{digest}" if head else digest


def bounded_execution_id(value: str, fallback: str) -> str:
    return bounded_identifier(value, fallback)


def enum_value(value: Any) -> Any:
    if hasattr(value, "value"):
        return getattr(value, "value")
    return value


def jsonable(value: Any) -> Any:
    value = enum_value(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [jsonable(item) for item in value]
    if hasattr(value, "model_dump"):
        return jsonable(value.model_dump())
    if hasattr(value, "dict"):
        return jsonable(value.dict())
    return str(value)


def field_value(obj: Any, field: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(field, default)
    return getattr(obj, field, default)


def normalized_storage_key(value: Any) -> str:
    return str(value or "").strip().lstrip("/")


def preview_kind(storage_key: str) -> Optional[str]:
    key = normalized_storage_key(storage_key)
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


def storage_capability(slot_name: str, storage_key: str) -> str:
    key = normalized_storage_key(storage_key)
    if key.startswith("video_renderer/"):
        return "video_renderer"
    if key.startswith("layer_asset_forge/"):
        return "layer_asset_forge"
    return "video_renderer" if slot_name == "final_render" else "layer_asset_forge"


def preview_url(*, tenant_id: str, slot_name: str, storage_key: Any) -> Optional[str]:
    key = normalized_storage_key(storage_key)
    if not key:
        return None
    capability = storage_capability(slot_name, key)
    tenant = safe_segment(tenant_id, "default")
    return f"/api/v1/capabilities/{capability}/storage/{tenant}/{key}"


def with_preview_refs(slot: Dict[str, Any], *, tenant_id: str) -> Dict[str, Any]:
    enriched = dict(slot)
    slot_name = str(enriched.get("slot") or "").strip()
    for field_name, preview_prefix in (
        ("storage_key", "preview"),
        ("mask_storage_key", "mask_preview"),
        ("alpha_storage_key", "alpha_preview"),
    ):
        key = normalized_storage_key(enriched.get(field_name))
        if not key:
            continue
        enriched[field_name] = key
        enriched[f"{preview_prefix}_url"] = preview_url(
            tenant_id=tenant_id,
            slot_name=slot_name,
            storage_key=key,
        )
        enriched[f"{preview_prefix}_kind"] = preview_kind(key)
    return enriched


def normalize_clip_ref(ref: Any) -> Dict[str, Any]:
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
