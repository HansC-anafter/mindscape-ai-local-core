"""Capability manifest helpers for ToolEmbeddingService."""

from __future__ import annotations

from pathlib import Path

import yaml


def get_capability_manifest_context(
    *,
    cache: dict[str, str | None],
    capability_code: str,
    services_dir: Path,
) -> str | None:
    """Return cached multilingual manifest metadata for embedding enrichment."""
    if capability_code in cache:
        return cache[capability_code]

    manifest_path = services_dir / "capabilities" / capability_code / "manifest.yaml"
    if not manifest_path.is_file():
        cache[capability_code] = None
        return None

    try:
        data = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    except Exception:
        cache[capability_code] = None
        return None

    parts: list[str] = []
    zh_name = data.get("display_name_zh")
    if zh_name:
        parts.append(str(zh_name))

    description = data.get("description", "")
    if description and not str(description).isascii():
        parts.append(str(description)[:200])
    elif zh_name:
        english_description = data.get("description", "")
        if english_description:
            parts.append(str(english_description)[:120])

    result = " ".join(parts) if parts else None
    cache[capability_code] = result
    return result
