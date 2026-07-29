"""Bounded owner-value, pointer, and facet normalization helpers."""

from __future__ import annotations

from typing import Any, Mapping

from .write_contracts import ProjectionFacetWrite


def bounded_owner_value(value: Any, *, depth: int = 0) -> Any:
    if depth > 3:
        return None
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:2048]
    if isinstance(value, Mapping):
        return {
            str(key)[:128]: bounded_owner_value(
                child,
                depth=depth + 1,
            )
            for key, child in list(value.items())[:64]
        }
    if isinstance(value, (list, tuple)):
        return [
            bounded_owner_value(child, depth=depth + 1)
            for child in value[:64]
        ]
    return str(value)[:2048]


def target_key(target: Mapping[str, Any]) -> str | None:
    uri = str(target.get("uri") or "").strip()
    if uri:
        return uri
    owner = str(target.get("owner_pack") or "").strip()
    kind = str(target.get("object_kind") or "").strip()
    object_id = str(target.get("object_id") or "").strip()
    if owner and kind and object_id:
        return f"mindscape://{owner}/{kind}/{object_id}"
    return None


def media_pointer(detail: Mapping[str, Any]) -> tuple[str, str] | None:
    candidates = (
        ("image", detail.get("image_url")),
        ("image", detail.get("image_relpath")),
        ("image", detail.get("preview_ref")),
        ("video", detail.get("video_url")),
        ("audio", detail.get("audio_url")),
        ("artifact", detail.get("artifact_uri")),
    )
    for kind, raw in candidates:
        pointer = str(raw or "").strip()
        if not pointer:
            continue
        if kind == "artifact":
            lowered = pointer.lower()
            if lowered.endswith((".mp4", ".mov", ".webm", ".mkv")):
                kind = "video"
            elif lowered.endswith((".mp3", ".wav", ".m4a", ".aac", ".flac")):
                kind = "audio"
            else:
                kind = "image"
        return kind, pointer[:1024]
    preview = detail.get("preview")
    if isinstance(preview, Mapping):
        for key in ("image_url", "image_relpath"):
            pointer = str(preview.get(key) or "").strip()
            if pointer:
                return "image", pointer[:1024]
    return None


def facet_rows(
    detail: Mapping[str, Any],
    *,
    object_kind: str,
) -> tuple[ProjectionFacetWrite, ...]:
    rows = [
        ProjectionFacetWrite(
            key="object_kind",
            value_type="enum",
            value=object_kind,
        )
    ]
    for key, value in detail.items():
        normalized = str(key or "").strip().lower()
        if (
            not normalized
            or len(rows) >= 32
            or normalized == "object_kind"
        ):
            continue
        if isinstance(value, bool):
            value_type = "boolean"
        elif isinstance(value, (int, float)):
            value_type = "number"
        elif isinstance(value, str) and value.strip():
            value_type = "string"
            value = value[:1024]
        else:
            continue
        rows.append(
            ProjectionFacetWrite(
                key=normalized[:128],
                value_type=value_type,
                value=value,
            )
        )
    return tuple(rows)


__all__ = [
    "bounded_owner_value",
    "facet_rows",
    "media_pointer",
    "target_key",
]
