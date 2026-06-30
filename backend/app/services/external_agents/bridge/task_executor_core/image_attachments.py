"""Image attachment helpers for host-side CLI dispatch."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Iterable, List


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
DEFAULT_MAX_CODEX_IMAGE_ATTACHMENTS = 4


def _text(value: Any) -> str:
    return str(value or "").strip()


def _attachment_path(item: Any) -> str:
    if isinstance(item, str):
        return item.strip()
    if not isinstance(item, dict):
        return ""
    for key in ("file_path", "local_path", "path"):
        value = _text(item.get(key))
        if value:
            return value
    return ""


def _is_image_attachment(item: Any, path: str) -> bool:
    if isinstance(item, dict):
        content_type = _text(item.get("content_type")).lower()
        if content_type.startswith("image/"):
            return True
        for key in ("detected_type", "file_type", "mime_type"):
            value = _text(item.get(key)).lower()
            if value.startswith("image/") or value in {
                "image",
                "png",
                "jpg",
                "jpeg",
                "webp",
                "gif",
                "bmp",
            }:
                return True
    return Path(path).suffix.lower() in IMAGE_SUFFIXES


def _max_image_attachments() -> int:
    raw = os.environ.get("MINDSCAPE_CODEX_MAX_IMAGE_ATTACHMENTS", "").strip()
    if not raw:
        return DEFAULT_MAX_CODEX_IMAGE_ATTACHMENTS
    try:
        return max(0, min(12, int(raw)))
    except ValueError:
        return DEFAULT_MAX_CODEX_IMAGE_ATTACHMENTS


def resolve_codex_image_paths(
    uploaded_files: Iterable[Any],
    *,
    max_items: int | None = None,
) -> List[str]:
    """Return local image paths that the host-side Codex CLI can attach."""

    limit = _max_image_attachments() if max_items is None else max(0, max_items)
    if limit == 0:
        return []

    paths: List[str] = []
    seen: set[str] = set()
    for item in uploaded_files or []:
        path = _attachment_path(item)
        if not path or path.startswith(("http://", "https://")):
            continue
        if not _is_image_attachment(item, path):
            continue
        resolved = str(Path(path).expanduser().resolve(strict=False))
        if resolved in seen or not os.path.isfile(resolved):
            continue
        seen.add(resolved)
        paths.append(resolved)
        if len(paths) >= limit:
            break
    return paths


def build_codex_image_args(uploaded_files: Iterable[Dict[str, Any]]) -> List[str]:
    """Build flat Codex CLI image attachment arguments."""

    args: List[str] = []
    for path in resolve_codex_image_paths(uploaded_files):
        args.extend(["--image", path])
    return args
