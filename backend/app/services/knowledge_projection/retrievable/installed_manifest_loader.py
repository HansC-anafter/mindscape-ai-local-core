"""Bounded loader for installed knowledge-projection manifest slices."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from backend.app.services.runtime_pack_hygiene import (
    is_ignored_runtime_pack_dir,
)

from .adapter_registry import register_manifest

logger = logging.getLogger(__name__)


def hydrate_installed_projection_manifests(
    capabilities_root: Path | None = None,
) -> dict[str, Any]:
    """Register only manifests that declare the projection contract key."""

    root = (
        Path(capabilities_root)
        if capabilities_root is not None
        else Path(__file__).resolve().parents[3] / "capabilities"
    )
    scanned_manifest_count = 0
    parsed_manifest_count = 0
    registered_capability_count = 0
    registered_descriptor_count = 0
    errors: list[dict[str, str]] = []
    if not root.exists() or not root.is_dir():
        raise RuntimeError(
            "knowledge_projection_capabilities_root_unavailable"
        )

    for capability_dir in sorted(root.iterdir()):
        if (
            not capability_dir.is_dir()
            or is_ignored_runtime_pack_dir(capability_dir.name)
        ):
            continue
        manifest_path = capability_dir / "manifest.yaml"
        if not manifest_path.exists():
            continue
        scanned_manifest_count += 1
        try:
            raw_manifest = manifest_path.read_text(encoding="utf-8")
            if "knowledge_projections" not in raw_manifest:
                continue
            parsed_manifest_count += 1
            manifest = yaml.safe_load(raw_manifest)
            if not isinstance(manifest, dict):
                raise ValueError(
                    "knowledge_projection_manifest_root_invalid"
                )
            descriptors = register_manifest(
                capability_dir.name,
                manifest,
                capability_dir,
            )
            registered_capability_count += 1
            registered_descriptor_count += len(descriptors)
        except Exception as exc:
            errors.append(
                {
                    "capability_code": capability_dir.name,
                    "error": str(exc),
                }
            )
            logger.error(
                "Installed knowledge projection manifest rejected for %s: %s",
                capability_dir.name,
                exc,
                exc_info=True,
            )

    return {
        "status": "ready" if not errors else "degraded",
        "scanned_manifest_count": scanned_manifest_count,
        "parsed_manifest_count": parsed_manifest_count,
        "registered_capability_count": registered_capability_count,
        "registered_descriptor_count": registered_descriptor_count,
        "errors": errors,
    }


__all__ = ["hydrate_installed_projection_manifests"]
