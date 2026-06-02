"""Static host resource lane registry for the P0 control plane."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

from .dynamic_lane_store import list_dynamic_lanes


DEFAULT_LANES: dict[str, dict[str, Any]] = {
    "runner:browser_local": {
        "lane_id": "runner:browser_local",
        "label": "Browser Runner",
        "kind": "runner",
        "requirements": {
            "memory_mb": 0,
            "memory_source": "not_applicable",
            "cpu_weight": 1,
            "exclusive_groups": ["browser_local"],
        },
    },
    "runner:default_local": {
        "lane_id": "runner:default_local",
        "label": "Default Runner",
        "kind": "runner",
        "requirements": {
            "memory_mb": 0,
            "memory_source": "not_applicable",
            "cpu_weight": 1,
            "exclusive_groups": ["default_local"],
        },
    },
    "runner:vision_local": {
        "lane_id": "runner:vision_local",
        "label": "Vision Runner",
        "kind": "runner",
        "requirements": {
            "memory_mb": 0,
            "memory_source": "not_applicable",
            "cpu_weight": 1,
            "exclusive_groups": ["vision_local"],
        },
    },
}

_manifest_lane_overlay_signature_cache: tuple[tuple[str, int, int], ...] | None = None
_manifest_lane_overlays_cache: dict[str, dict[str, Any]] | None = None


def _overlay_lanes(base: dict[str, dict[str, Any]], raw: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(raw, dict):
        return base
    lanes = copy.deepcopy(base)
    for lane_id, override in raw.items():
        if not isinstance(lane_id, str) or not isinstance(override, dict):
            continue
        current = lanes.get(lane_id, {"lane_id": lane_id, "requirements": {}})
        merged = copy.deepcopy(current)
        for key, value in override.items():
            if key == "requirements" and isinstance(value, dict):
                requirements = dict(merged.get("requirements") or {})
                requirements.update(value)
                merged["requirements"] = requirements
            else:
                merged[key] = value
        merged.setdefault("lane_id", lane_id)
        merged.setdefault("label", lane_id)
        merged.setdefault("requirements", {})
        lanes[lane_id] = merged
    return lanes


def _capabilities_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "capabilities"


def clear_lane_registry_cache() -> None:
    global _manifest_lane_overlay_signature_cache, _manifest_lane_overlays_cache
    _manifest_lane_overlay_signature_cache = None
    _manifest_lane_overlays_cache = None


def _manifest_overlay_signature(
    capabilities_dir: Path,
) -> tuple[tuple[str, int, int], ...]:
    if not capabilities_dir.exists():
        return ()
    signature: list[tuple[str, int, int]] = []
    for manifest_path in sorted(capabilities_dir.glob("*/manifest.yaml")):
        try:
            stat = manifest_path.stat()
        except OSError:
            continue
        signature.append(
            (
                str(manifest_path),
                int(stat.st_mtime_ns),
                int(stat.st_size),
            )
        )
    return tuple(signature)


def _load_manifest_lane_overlays() -> dict[str, dict[str, Any]]:
    global _manifest_lane_overlay_signature_cache, _manifest_lane_overlays_cache
    lanes: dict[str, dict[str, Any]] = {}
    capabilities_dir = _capabilities_dir()
    signature = _manifest_overlay_signature(capabilities_dir)
    if (
        _manifest_lane_overlay_signature_cache == signature
        and _manifest_lane_overlays_cache is not None
    ):
        return copy.deepcopy(_manifest_lane_overlays_cache)
    if not signature:
        _manifest_lane_overlay_signature_cache = signature
        _manifest_lane_overlays_cache = {}
        return lanes
    for manifest_path in sorted(capabilities_dir.glob("*/manifest.yaml")):
        try:
            manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        raw_lanes = manifest.get("host_resource_lanes")
        if not isinstance(raw_lanes, dict):
            continue
        for lane_id, lane in raw_lanes.items():
            if isinstance(lane_id, str) and isinstance(lane, dict):
                lanes[lane_id] = lane
    _manifest_lane_overlay_signature_cache = signature
    _manifest_lane_overlays_cache = copy.deepcopy(lanes)
    return lanes


def load_lane_registry() -> dict[str, dict[str, Any]]:
    lanes = _overlay_lanes(DEFAULT_LANES, _load_manifest_lane_overlays())
    for lane in list_dynamic_lanes():
        lane_id = lane.get("lane_id")
        if isinstance(lane_id, str) and lane_id.strip():
            lanes[lane_id] = lane
    return copy.deepcopy(lanes)


def get_lane(lane_id: str | None) -> dict[str, Any] | None:
    if not lane_id:
        return None
    return load_lane_registry().get(lane_id)
