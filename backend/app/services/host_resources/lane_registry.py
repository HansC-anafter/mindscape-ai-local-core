"""Static host resource lane registry for the P0 control plane."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any

import yaml


DEFAULT_LANES: dict[str, dict[str, Any]] = {
    "mlx:qwen9b_4bit_vision": {
        "lane_id": "mlx:qwen9b_4bit_vision",
        "label": "MLX Qwen9B 4bit Vision",
        "kind": "mlx",
        "requirements": {
            "memory_mb": 7168,
            "memory_source": "declared",
            "cpu_weight": 2,
            "exclusive_groups": ["apple_metal_heavy", "mlx_vision_llm"],
        },
    },
    "comfyui_runtime:flux2_klein_true_v2_q6_local": {
        "lane_id": "comfyui_runtime:flux2_klein_true_v2_q6_local",
        "label": "FLUX2 Klein True V2 Q6 Local Lane",
        "kind": "comfyui",
        "requirements": {
            "memory_mb": None,
            "memory_source": "unknown",
            "cpu_weight": 4,
            "exclusive_groups": ["apple_metal_heavy", "comfyui_generation"],
        },
    },
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


def _load_manifest_lane_overlays() -> dict[str, dict[str, Any]]:
    lanes: dict[str, dict[str, Any]] = {}
    capabilities_dir = _capabilities_dir()
    if not capabilities_dir.exists():
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
    return lanes


def load_lane_registry() -> dict[str, dict[str, Any]]:
    lanes = _overlay_lanes(DEFAULT_LANES, _load_manifest_lane_overlays())
    raw_json = os.getenv("LOCAL_CORE_HOST_RESOURCE_LANES_JSON")
    if not raw_json:
        return copy.deepcopy(lanes)
    try:
        return _overlay_lanes(lanes, json.loads(raw_json))
    except Exception:
        return copy.deepcopy(lanes)


def get_lane(lane_id: str | None) -> dict[str, Any] | None:
    if not lane_id:
        return None
    return load_lane_registry().get(lane_id)
