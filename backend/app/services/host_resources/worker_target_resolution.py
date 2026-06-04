"""Resolve dynamic lane worker target requests to registered runtime slots."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

from backend.app.services.stores.postgres_base import PostgresStoreBase
from backend.app.services.system_settings_store import SystemSettingsStore

from .runtime_adapter_catalog import get_runtime_adapter
from .runtime_environment_slots import normalize_host_resource_slot_metadata


def _clean_string(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _clean_int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


class RuntimeEnvironmentSlotStore(PostgresStoreBase):
    def get_runtime_environment(self, runtime_environment_id: str) -> dict[str, Any] | None:
        runtime_id = _clean_string(runtime_environment_id)
        if not runtime_id:
            return None
        try:
            with self.get_connection() as conn:
                row = conn.execute(
                    text(
                        """
                        SELECT id, name, status, extra_metadata
                        FROM runtime_environments
                        WHERE id = :runtime_id
                        """
                    ),
                    {"runtime_id": runtime_id},
                ).fetchone()
        except Exception:
            return None
        if not row:
            return None
        mapping = dict(row._mapping) if hasattr(row, "_mapping") else dict(row)
        return {
            "id": mapping.get("id"),
            "name": mapping.get("name"),
            "status": mapping.get("status"),
            "metadata": self.deserialize_json(mapping.get("extra_metadata"), default={}),
        }


def _adapter_id_for_lane(lane: dict[str, Any]) -> str | None:
    metadata = _dict(lane.get("metadata"))
    model_profile = _dict(lane.get("model_profile"))
    explicit = _clean_string(
        metadata.get("adapter_id")
        or metadata.get("runtime_adapter_id")
        or model_profile.get("adapter_id")
    )
    if explicit:
        return explicit
    if _clean_string(lane.get("resource_flavor")) == "local.mlx.vision":
        return "apple_mlx_vlm"
    return None


def _runtime_environment_id_for_lane(lane: dict[str, Any]) -> str | None:
    metadata = _dict(lane.get("metadata"))
    model_profile = _dict(lane.get("model_profile"))
    return _clean_string(
        metadata.get("runtime_environment_id")
        or metadata.get("host_resource_slot_runtime_id")
        or model_profile.get("runtime_environment_id")
    )


def _model_binding_for(
    *,
    lane: dict[str, Any],
    adapter: dict[str, Any],
    slot: dict[str, Any],
) -> dict[str, Any]:
    scope = _clean_string(slot.get("model_binding_scope")) or adapter.get(
        "default_model_binding_scope"
    )
    profile = _clean_string(slot.get("model_binding_profile")) or adapter.get(
        "default_model_binding_profile"
    )
    if not scope or not profile:
        return {"model": None, "scope": scope, "profile": profile, "source": "not_required"}
    bindings = SystemSettingsStore().get_profile_model_bindings_for_scope(scope)
    model = _clean_string(bindings.get(profile)) if isinstance(bindings, dict) else None
    return {
        "model": model,
        "scope": scope,
        "profile": profile,
        "source": f"system_settings.profile_model_bindings.{scope}.{profile}",
    }


def _endpoint_configured(slot: dict[str, Any]) -> bool:
    endpoint = _dict(slot.get("endpoint"))
    return bool(_clean_string(endpoint.get("base_url")) or _clean_string(endpoint.get("host")))


def _worker_env_for_resolution(
    *,
    lane: dict[str, Any],
    adapter: dict[str, Any],
    slot: dict[str, Any],
    model_binding: dict[str, Any],
    runtime_environment_id: str,
) -> dict[str, Any]:
    endpoint = _dict(slot.get("endpoint"))
    model_profile = _dict(lane.get("model_profile"))
    port = _clean_int(endpoint.get("port"), default=_clean_int(model_profile.get("port"), default=8211))
    env = {
        "LOCAL_CORE_RUNTIME_ADAPTER_ID": adapter["adapter_id"],
        "LOCAL_CORE_RUNTIME_ENVIRONMENT_ID": runtime_environment_id,
        "LOCAL_CORE_RUNNER_PROFILE": lane.get("runner_profile"),
        "LOCAL_CORE_RUNNER_ACCEPTED_PARTITIONS": lane.get("queue_shard"),
        "LOCAL_CORE_RUNNER_ACCEPTED_RESOURCE_CLASSES": lane.get("resource_class"),
        "LOCAL_CORE_RUNNER_ACCEPTED_CAPABILITY_CODES": "ig_analyze_pinned_reference",
        "LOCAL_CORE_RUNNER_MAX_INFLIGHT": 1,
        "LOCAL_CORE_RUNNER_RUNTIME_ID": f"{adapter['adapter_id']}:{lane.get('lane_id')}",
    }
    base_url = _clean_string(endpoint.get("base_url"))
    if base_url:
        env["LOCAL_CORE_RUNTIME_ENDPOINT"] = base_url
    if adapter["adapter_id"] == "apple_mlx_vlm":
        env["MLX_PORT"] = port
        if model_binding.get("model"):
            env["MLX_MODEL"] = model_binding["model"]
    elif adapter["adapter_id"] == "ollama_llama_cpp":
        if base_url:
            env["OLLAMA_HOST"] = base_url
        if model_binding.get("model"):
            env["OLLAMA_MODEL"] = model_binding["model"]
    else:
        if model_binding.get("model"):
            env["LOCAL_CORE_RUNTIME_MODEL"] = model_binding["model"]
    return env


def resolve_worker_target(lane: dict[str, Any], desired_worker_count: int) -> dict[str, Any]:
    desired = max(0, _clean_int(desired_worker_count, default=0))
    if desired <= 0:
        return {
            "accepted": True,
            "reason": "stop_target_does_not_require_runtime_slot",
            "worker_env": {},
        }

    adapter_id = _adapter_id_for_lane(lane)
    adapter = get_runtime_adapter(adapter_id)
    if not adapter:
        return {"accepted": False, "reason": "runtime_adapter_unknown", "adapter_id": adapter_id}
    if not adapter.get("worker_capable"):
        return {
            "accepted": False,
            "reason": "runtime_adapter_not_worker_capable",
            "adapter": adapter,
        }

    runtime_environment_id = _runtime_environment_id_for_lane(lane)
    if not runtime_environment_id:
        return {
            "accepted": False,
            "reason": "host_resource_slot_missing",
            "adapter": adapter,
        }

    runtime_environment = RuntimeEnvironmentSlotStore("core").get_runtime_environment(
        runtime_environment_id
    )
    if not runtime_environment:
        return {
            "accepted": False,
            "reason": "host_resource_slot_not_found",
            "adapter": adapter,
            "runtime_environment_id": runtime_environment_id,
        }
    if runtime_environment.get("status") not in {"active", "configured"}:
        return {
            "accepted": False,
            "reason": "host_resource_slot_inactive",
            "adapter": adapter,
            "runtime_environment": runtime_environment,
        }

    try:
        slot = normalize_host_resource_slot_metadata(runtime_environment.get("metadata") or {})
    except ValueError as exc:
        return {
            "accepted": False,
            "reason": str(exc) or "host_resource_slot_invalid",
            "adapter": adapter,
            "runtime_environment": runtime_environment,
        }
    if slot.get("adapter_id") != adapter["adapter_id"]:
        return {
            "accepted": False,
            "reason": "host_resource_slot_adapter_mismatch",
            "adapter": adapter,
            "slot": slot,
            "runtime_environment": runtime_environment,
        }
    if slot.get("worker_spawn_policy") == "never":
        return {
            "accepted": False,
            "reason": "host_resource_slot_worker_spawn_forbidden",
            "adapter": adapter,
            "slot": slot,
            "runtime_environment": runtime_environment,
        }
    if adapter.get("endpoint_required") and not _endpoint_configured(slot):
        return {
            "accepted": False,
            "reason": "host_resource_slot_endpoint_missing",
            "adapter": adapter,
            "slot": slot,
            "runtime_environment": runtime_environment,
        }

    model_binding = _model_binding_for(lane=lane, adapter=adapter, slot=slot)
    if adapter.get("model_binding_policy") == "required" and not model_binding.get("model"):
        return {
            "accepted": False,
            "reason": "model_binding_missing",
            "adapter": adapter,
            "slot": slot,
            "runtime_environment": runtime_environment,
            "model_binding": model_binding,
        }
    if adapter.get("model_binding_policy") == "forbidden" and model_binding.get("model"):
        return {
            "accepted": False,
            "reason": "model_binding_forbidden",
            "adapter": adapter,
            "slot": slot,
            "runtime_environment": runtime_environment,
            "model_binding": model_binding,
        }

    return {
        "accepted": True,
        "reason": "worker_target_resolved",
        "adapter": adapter,
        "slot": slot,
        "runtime_environment": runtime_environment,
        "model_binding": model_binding,
        "worker_env": _worker_env_for_resolution(
            lane=lane,
            adapter=adapter,
            slot=slot,
            model_binding=model_binding,
            runtime_environment_id=runtime_environment_id,
        ),
    }
