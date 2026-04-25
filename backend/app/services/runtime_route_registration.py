"""
Runtime route registration helpers.

Keeps built-in runtime definitions and route-slot registration payloads in one
place so runtime creation/listing and settings inventory speak the same schema.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional

from backend.app.models.runtime_environment import RuntimeEnvironment

BUILT_IN_RUNTIME_ENVIRONMENTS = [
    {
        "id": "local-core",
        "name": "Local-Core Runtime",
        "description": "Local execution environment, enabled by default",
        "icon": "desktop",
        "status": "active",
        "is_default": True,
        "isDefault": True,
        "config_url": None,
        "auth_type": "none",
        "supports_dispatch": True,
        "supports_cell": True,
        "metadata": {
            "runtime_type": "local_core",
            "capability_code": "local_core",
        },
    },
    {
        "id": "mindscape-ai-cloud-3d-mesh",
        "name": "Mindscape AI Cloud 3D Mesh",
        "description": "Configure modeled scene/person mesh runtime lanes for Blender Bridge without editing .env",
        "icon": "🧊",
        "status": "not_configured",
        "is_default": False,
        "isDefault": False,
        "config_url": None,
        "auth_type": "none",
        "supports_dispatch": True,
        "supports_cell": True,
        "metadata": {
            "runtime_type": "mindscape_ai_cloud_3d_mesh",
            "capability_code": "blender_bridge",
            "scope": "system",
        },
    },
]


def _canonicalize_slots(slots: List[Dict[str, Any]]) -> List[str]:
    canonical: List[str] = []
    for slot in slots:
        canonical.append(json.dumps(slot, sort_keys=True, ensure_ascii=False, default=str))
    return sorted(canonical)


def _get_runtime_value(runtime: RuntimeEnvironment | Mapping[str, Any], key: str) -> Any:
    if isinstance(runtime, Mapping):
        return runtime.get(key)
    if key == "metadata":
        return runtime.extra_metadata or {}
    return getattr(runtime, key, None)


def build_runtime_registration_group(
    runtime: RuntimeEnvironment | Mapping[str, Any],
    *,
    owner_kind: str = "runtime_environment",
    source: str = "runtime_environments",
    settings_anchor: str = "tab:runtime",
) -> Dict[str, Any]:
    runtime_id = str(_get_runtime_value(runtime, "id") or "").strip()
    name = str(_get_runtime_value(runtime, "name") or runtime_id).strip() or runtime_id
    status = str(_get_runtime_value(runtime, "status") or "not_configured").strip()
    auth_type = str(_get_runtime_value(runtime, "auth_type") or "none").strip()
    auth_status = str(_get_runtime_value(runtime, "auth_status") or "").strip() or None
    metadata = dict(_get_runtime_value(runtime, "metadata") or {})
    pool_group = _get_runtime_value(runtime, "pool_group")
    pool_enabled = _get_runtime_value(runtime, "pool_enabled")

    summary_parts = [f"status={status}"]
    runtime_type = str(metadata.get("runtime_type") or "").strip()
    capability_code = str(metadata.get("capability_code") or "").strip()
    if runtime_type:
        summary_parts.append(f"type={runtime_type}")
    if capability_code:
        summary_parts.append(f"capability={capability_code}")
    if pool_group:
        summary_parts.append(f"pool={pool_group}")
    if auth_type and auth_type != "none":
        summary_parts.append(f"auth={auth_type}")
    if auth_status:
        summary_parts.append(f"auth_status={auth_status}")

    slot = {
        "slot_id": f"{runtime_id}:runtime_registration:registered_runtime",
        "owner_kind": owner_kind,
        "owner_id": runtime_id,
        "owner_name": name,
        "slot_kind": "runtime_registration",
        "title": "Registered Runtime",
        "summary": "; ".join(summary_parts),
        "route_family": "runtime_registration",
        "source": source,
        "settings_anchor": settings_anchor,
        "installed": True,
        "enabled": status in {"active", "configured"},
        "evidence_path": None,
        "raw": {
            "runtime_id": runtime_id,
            "status": status,
            "auth_type": auth_type,
            "auth_status": auth_status,
            "runtime_type": runtime_type or None,
            "capability_code": capability_code or None,
            "pool_group": pool_group,
            "pool_enabled": pool_enabled,
        },
    }

    stored_slots = metadata.get("model_route_slots") or []
    stored_slot_count = metadata.get("model_route_slot_count")
    try:
        normalized_stored_count = (
            len(stored_slots) if stored_slot_count is None else int(stored_slot_count)
        )
    except (TypeError, ValueError):
        normalized_stored_count = len(stored_slots)
    registration_drift = (
        normalized_stored_count != 1
        or _canonicalize_slots([slot]) != _canonicalize_slots(
            [dict(item) for item in stored_slots if isinstance(item, dict)]
        )
    )

    return {
        "runtime_id": runtime_id,
        "name": name,
        "status": status,
        "slot_count": 1,
        "stored_slot_count": normalized_stored_count,
        "registration_drift": registration_drift,
        "slots": [slot],
    }


def sync_runtime_registration_metadata(
    runtime: RuntimeEnvironment,
    *,
    registered_at: Optional[str] = None,
) -> Dict[str, Any]:
    group = build_runtime_registration_group(runtime)
    metadata = dict(runtime.extra_metadata or {})
    metadata["model_route_slots"] = group["slots"]
    metadata["model_route_slot_count"] = group["slot_count"]
    metadata["model_route_settings_anchor"] = "tab:runtime"
    metadata["model_route_slot_registered_at"] = (
        registered_at or datetime.now(timezone.utc).isoformat()
    )
    runtime.extra_metadata = metadata
    return metadata


def attach_runtime_registration_metadata(
    runtime_payload: Mapping[str, Any],
    *,
    registered_at: Optional[str] = None,
) -> Dict[str, Any]:
    payload = dict(runtime_payload)
    metadata = dict(payload.get("metadata") or {})
    group = build_runtime_registration_group(payload)
    metadata["model_route_slots"] = group["slots"]
    metadata["model_route_slot_count"] = group["slot_count"]
    metadata["model_route_settings_anchor"] = "tab:runtime"
    if registered_at:
        metadata["model_route_slot_registered_at"] = registered_at
    payload["metadata"] = metadata
    return payload


def list_built_in_runtime_environments() -> List[Dict[str, Any]]:
    return [attach_runtime_registration_metadata(runtime) for runtime in BUILT_IN_RUNTIME_ENVIRONMENTS]


def get_built_in_runtime_environment(runtime_id: str) -> Optional[Dict[str, Any]]:
    for runtime in BUILT_IN_RUNTIME_ENVIRONMENTS:
        if runtime["id"] == runtime_id:
            return attach_runtime_registration_metadata(runtime)
    return None
