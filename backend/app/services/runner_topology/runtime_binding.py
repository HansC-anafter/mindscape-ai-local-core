"""Runtime binding helpers for runner profiles and task runtime affinity."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

from .profile_registry import RunnerProfile

_RUNTIME_AFFINITY_FIELDS = (
    "runtime_id",
    "runtime_url",
    "transport",
    "dispatch_mode",
    "site_key",
    "device_id",
)

_RUNTIME_ENV_METADATA_FIELDS = (
    "runtime_url",
    "transport",
    "dispatch_mode",
    "site_key",
    "device_id",
    "target_device_id",
)


@dataclass(frozen=True)
class RuntimeBindingTarget:
    dispatch_mode: str
    runtime_id: Optional[str]
    runtime_url: Optional[str]
    transport: Optional[str]
    site_key: Optional[str]
    device_id: Optional[str]
    via: str


def _normalized_string(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _normalize_runtime_affinity(value: Any) -> dict[str, str]:
    if isinstance(value, str):
        normalized = _normalized_string(value)
        return {"runtime_id": normalized} if normalized else {}

    if not isinstance(value, dict):
        return {}

    normalized: dict[str, str] = {}
    for key in _RUNTIME_AFFINITY_FIELDS:
        token = _normalized_string(value.get(key))
        if token:
            normalized[key] = token
    return normalized


def resolve_task_runtime_affinity(task: Any) -> dict[str, str]:
    if isinstance(task, dict):
        affinity = task.get("runtime_affinity")
        if affinity is None and isinstance(task.get("execution_context"), dict):
            affinity = task["execution_context"].get("runtime_affinity")
        return _normalize_runtime_affinity(affinity)

    affinity = getattr(task, "runtime_affinity", None)
    if affinity is not None:
        return _normalize_runtime_affinity(affinity)

    ctx = getattr(task, "execution_context", None)
    if isinstance(ctx, dict):
        return _normalize_runtime_affinity(ctx.get("runtime_affinity"))
    return {}


def resolve_runtime_binding(
    profile: RunnerProfile,
    task: Any | None = None,
) -> RuntimeBindingTarget:
    task_affinity = resolve_task_runtime_affinity(task) if task is not None else {}

    runtime_id = task_affinity.get("runtime_id") or _normalized_string(profile.runtime_id)
    dispatch_mode = (
        task_affinity.get("dispatch_mode")
        or _normalized_string(profile.dispatch_mode)
        or "docker_local"
    )
    runtime_url = task_affinity.get("runtime_url")
    transport = task_affinity.get("transport")
    site_key = task_affinity.get("site_key")
    device_id = task_affinity.get("device_id")

    if task_affinity and runtime_id:
        via = "task_runtime_affinity+runner_profile"
    elif task_affinity:
        via = "task_runtime_affinity"
    elif runtime_id:
        via = "runner_profile"
    else:
        via = "none"

    return RuntimeBindingTarget(
        dispatch_mode=dispatch_mode,
        runtime_id=runtime_id,
        runtime_url=runtime_url,
        transport=transport,
        site_key=site_key,
        device_id=device_id,
        via=via,
    )


def _load_runtime_environment_snapshot(runtime_id: str) -> Optional[dict[str, Any]]:
    normalized_runtime_id = _normalized_string(runtime_id)
    if not normalized_runtime_id or normalized_runtime_id == "local-core":
        return None

    try:
        from backend.app.database.session import get_db_postgres as get_db
    except Exception:
        try:
            from backend.app.database import get_db_postgres as get_db
        except Exception:
            return None

    try:
        from backend.app.models.runtime_environment import RuntimeEnvironment
    except Exception:
        return None

    db = None
    try:
        db = next(get_db())
        runtime = (
            db.query(RuntimeEnvironment)
            .filter(
                RuntimeEnvironment.id == normalized_runtime_id,
                RuntimeEnvironment.supports_dispatch.is_(True),
            )
            .first()
        )
        if not runtime:
            return None
        return {
            "runtime_id": normalized_runtime_id,
            "config_url": _normalized_string(getattr(runtime, "config_url", None)),
            "dispatch_mode": _normalized_string(
                (getattr(runtime, "extra_metadata", None) or {}).get("dispatch_mode")
            ),
            "metadata": dict(getattr(runtime, "extra_metadata", None) or {}),
        }
    except Exception:
        return None
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass


def _normalize_runtime_environment_metadata(snapshot: Any) -> dict[str, str]:
    if not isinstance(snapshot, dict):
        return {}

    metadata = snapshot.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}

    normalized: dict[str, str] = {}
    for key in _RUNTIME_ENV_METADATA_FIELDS:
        token = _normalized_string(metadata.get(key))
        if token:
            normalized[key] = token

    config_url = _normalized_string(snapshot.get("config_url"))
    if config_url and "runtime_url" not in normalized:
        normalized["runtime_url"] = config_url

    return normalized


def resolve_runtime_dispatch_target(
    profile: RunnerProfile,
    task: Any | None = None,
    *,
    runtime_lookup: Optional[Callable[[str], Optional[dict[str, Any]]]] = None,
) -> RuntimeBindingTarget:
    binding = resolve_runtime_binding(profile, task)
    runtime_id = binding.runtime_id

    dispatch_mode = binding.dispatch_mode
    if runtime_id and dispatch_mode == "docker_local":
        dispatch_mode = ""

    runtime_url = binding.runtime_url
    transport = binding.transport
    site_key = binding.site_key
    device_id = binding.device_id
    via = binding.via

    hydrated = False
    if runtime_id:
        snapshot = (
            runtime_lookup(runtime_id)
            if callable(runtime_lookup)
            else _load_runtime_environment_snapshot(runtime_id)
        )
        runtime_meta = _normalize_runtime_environment_metadata(snapshot)
        if runtime_meta:
            if not dispatch_mode:
                dispatch_mode = (
                    _normalized_string(runtime_meta.get("dispatch_mode"))
                    or "external_runtime"
                )
            if not runtime_url and runtime_meta.get("runtime_url"):
                runtime_url = runtime_meta["runtime_url"]
                hydrated = True
            if not transport and runtime_meta.get("transport"):
                transport = runtime_meta["transport"]
                hydrated = True
            if not site_key and runtime_meta.get("site_key"):
                site_key = runtime_meta["site_key"]
                hydrated = True
            if not device_id:
                resolved_device_id = runtime_meta.get("device_id") or runtime_meta.get(
                    "target_device_id"
                )
                if resolved_device_id:
                    device_id = resolved_device_id
                    hydrated = True

    if runtime_id and not dispatch_mode:
        dispatch_mode = "external_runtime"
    if not dispatch_mode:
        dispatch_mode = "docker_local"

    if hydrated:
        via = f"{via}+runtime_environment" if via != "none" else "runtime_environment"

    return RuntimeBindingTarget(
        dispatch_mode=dispatch_mode,
        runtime_id=runtime_id,
        runtime_url=runtime_url,
        transport=transport,
        site_key=site_key,
        device_id=device_id,
        via=via,
    )
