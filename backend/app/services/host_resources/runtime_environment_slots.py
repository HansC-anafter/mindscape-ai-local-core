"""Host resource slot metadata validation for runtime environments."""

from __future__ import annotations

from typing import Any

from .runtime_adapter_catalog import get_runtime_adapter, require_runtime_adapter


def _clean_string(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _clean_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    cleaned: list[str] = []
    for item in value:
        normalized = _clean_string(item)
        if normalized and normalized not in cleaned:
            cleaned.append(normalized)
    return cleaned


def _source_from_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    nested = metadata.get("host_resource_slot")
    if isinstance(nested, dict):
        return dict(nested)
    if metadata.get("resource_kind") == "host_resource_slot" or metadata.get("adapter_id"):
        return dict(metadata)
    return {}


def normalize_host_resource_slot_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    source = _source_from_metadata(metadata if isinstance(metadata, dict) else {})
    if not source:
        raise ValueError("host_resource_slot_missing")

    adapter_id = _clean_string(source.get("adapter_id") or source.get("runtime_adapter_id"))
    adapter = require_runtime_adapter(adapter_id)

    endpoint = source.get("endpoint") if isinstance(source.get("endpoint"), dict) else {}
    endpoint = dict(endpoint or {})
    base_url = _clean_string(endpoint.get("base_url") or source.get("base_url"))
    host = _clean_string(endpoint.get("host") or source.get("host"))
    port = endpoint.get("port", source.get("port"))
    try:
        normalized_port = int(port) if port is not None and str(port).strip() else None
    except Exception:
        normalized_port = None

    capabilities = _clean_list(source.get("capabilities")) or list(adapter["default_capabilities"])
    permission_scopes = _clean_list(source.get("permission_scopes")) or list(
        adapter["permission_scopes"]
    )
    transport = _clean_string(source.get("transport") or endpoint.get("transport"))
    if transport and transport not in adapter["transports"]:
        raise ValueError("host_resource_slot_transport_mismatch")

    worker_spawn_policy = (
        _clean_string(source.get("worker_spawn_policy")) or adapter["worker_spawn_policy"]
    )
    if not adapter["worker_capable"]:
        worker_spawn_policy = "never"

    return {
        "resource_kind": "host_resource_slot",
        "adapter_id": adapter["adapter_id"],
        "adapter_category": adapter["category"],
        "platform": _clean_string(source.get("platform")),
        "transport": transport or adapter["transports"][0],
        "capabilities": capabilities,
        "permission_scopes": permission_scopes,
        "endpoint": {
            "kind": _clean_string(endpoint.get("kind")) or "http",
            "base_url": base_url,
            "host": host,
            "port": normalized_port,
            "health_path": _clean_string(endpoint.get("health_path") or source.get("health_path")),
        },
        "model_binding_scope": (
            _clean_string(source.get("model_binding_scope"))
            or adapter["default_model_binding_scope"]
        ),
        "model_binding_profile": (
            _clean_string(source.get("model_binding_profile"))
            or adapter["default_model_binding_profile"]
        ),
        "worker_spawn_policy": worker_spawn_policy,
        "raw": source,
    }


def get_host_resource_slot_adapter_id(metadata: dict[str, Any]) -> str | None:
    try:
        slot = normalize_host_resource_slot_metadata(metadata)
    except ValueError:
        return None
    adapter = get_runtime_adapter(slot.get("adapter_id"))
    return adapter["adapter_id"] if adapter else None
