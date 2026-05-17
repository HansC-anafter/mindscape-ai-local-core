"""Load installed capability read-model contracts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_installed_manifest(local_core_root: Path, capability: str) -> tuple[dict[str, Any], Path]:
    manifest_path = (
        local_core_root
        / "backend"
        / "app"
        / "capabilities"
        / capability
        / "manifest.yaml"
    )
    if not manifest_path.exists():
        raise FileNotFoundError(f"installed manifest not found: {manifest_path}")
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    if not isinstance(manifest, dict):
        raise ValueError(f"installed manifest must be an object: {manifest_path}")
    return manifest, manifest_path
