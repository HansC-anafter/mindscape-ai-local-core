from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .codex_pool_health_core import (
    AUTH_MATERIAL_VERSION_KEYS,
    HEALTH_METADATA_KEY,
    coerce_json_dict,
)
from .codex_pool_health_metadata import probe_state_for_error_code, read_health_metadata
from .codex_pool_health_seed import (
    _auth_material_newer_than_copy_seed,
    _metadata_is_copied_account_snapshot,
    default_health_state,
    normalize_seed_kind,
)


def stamp_runtime_seen(
    metadata: Dict[str, Any],
    *,
    auth_type: str = "",
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    merged_metadata = coerce_json_dict(metadata)
    health = read_health_metadata(merged_metadata, auth_type=auth_type)
    timestamp = (
        now or datetime.now(timezone.utc)
    ).astimezone(timezone.utc).isoformat()
    health["last_seen_at"] = timestamp
    merged_metadata[HEALTH_METADATA_KEY] = health
    return merged_metadata


def stamp_runtime_selected(
    metadata: Dict[str, Any],
    *,
    auth_type: str = "",
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    merged_metadata = coerce_json_dict(metadata)
    health = read_health_metadata(merged_metadata, auth_type=auth_type)
    timestamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
    health["last_selected_at"] = timestamp
    merged_metadata[HEALTH_METADATA_KEY] = health
    return merged_metadata


def stamp_runtime_success(
    metadata: Dict[str, Any],
    *,
    auth_type: str = "",
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    merged_metadata = coerce_json_dict(metadata)
    health = read_health_metadata(merged_metadata, auth_type=auth_type)
    timestamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
    health["health_state"] = "healthy"
    health["last_success_at"] = timestamp
    health["last_failure_code"] = None
    health["last_failure_at"] = None
    health["failure_scope_key"] = None
    for key in AUTH_MATERIAL_VERSION_KEYS:
        health.pop(f"failure_{key}", None)
    _stamp_account_snapshot_probe_validated(merged_metadata, health, timestamp=timestamp)
    merged_metadata[HEALTH_METADATA_KEY] = health
    return merged_metadata


def stamp_runtime_probe_success(
    metadata: Dict[str, Any],
    *,
    returncode: Optional[int] = 0,
    source_event_id: str = "",
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    merged_metadata = coerce_json_dict(metadata)
    timestamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
    merged_metadata["probe_state"] = "available"
    merged_metadata["last_probe_success_at"] = timestamp
    merged_metadata["last_probe_error_code"] = None
    merged_metadata["last_probe_runtime_returncode"] = returncode
    if source_event_id:
        merged_metadata["last_probe_source_event_id"] = str(source_event_id).strip()
    return merged_metadata


def stamp_runtime_probe_failure(
    metadata: Dict[str, Any],
    *,
    error_code: str,
    returncode: Optional[int] = None,
    source_event_id: str = "",
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    merged_metadata = coerce_json_dict(metadata)
    merged_metadata["probe_state"] = probe_state_for_error_code(error_code)
    merged_metadata["last_probe_error_code"] = str(error_code or "").strip().lower() or None
    merged_metadata["last_probe_runtime_returncode"] = returncode
    if source_event_id:
        merged_metadata["last_probe_source_event_id"] = str(source_event_id).strip()
    return merged_metadata


def stamp_runtime_requalified(
    metadata: Dict[str, Any],
    *,
    reason: str,
    auth_type: str = "",
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    merged_metadata = coerce_json_dict(metadata)
    health = read_health_metadata(merged_metadata, auth_type=auth_type)
    timestamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
    health["health_state"] = "healthy"
    health["last_requalified_at"] = timestamp
    health["last_requalification_reason"] = str(reason or "").strip() or "manual_override"
    health["last_failure_code"] = None
    health["failure_scope_key"] = None
    for key in AUTH_MATERIAL_VERSION_KEYS:
        health.pop(f"failure_{key}", None)
    merged_metadata[HEALTH_METADATA_KEY] = health
    return merged_metadata


def stamp_runtime_retired(
    metadata: Dict[str, Any],
    *,
    reason: str,
    auth_type: str = "",
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    merged_metadata = coerce_json_dict(metadata)
    health = read_health_metadata(merged_metadata, auth_type=auth_type)
    timestamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
    health["health_state"] = "quarantined"
    health["last_failure_at"] = timestamp
    health["last_failure_code"] = str(reason or "").strip() or "retired"
    health["failure_scope_key"] = None
    health["last_requalified_at"] = None
    health["last_requalification_reason"] = "retired_from_pool"
    merged_metadata[HEALTH_METADATA_KEY] = health
    return merged_metadata


def auth_failure_scope_key(
    metadata: Dict[str, Any],
    *,
    error_code: str,
    runtime_id: str = "",
) -> Optional[str]:
    normalized = str(error_code or "").strip().lower()
    if normalized in {"timeout", "stall"}:
        runtime_value = str(runtime_id or "").strip()
        return f"runtime:{runtime_value}" if runtime_value else None

    if normalized in {
        "401",
        "403",
        "auth_failure",
        "stale_refresh_token",
        "unauthorized",
    }:
        runtime_value = str(runtime_id or "").strip()
        return f"runtime:{runtime_value}" if runtime_value else None

    if normalized == "deactivated_workspace":
        account_key = str(metadata.get("account_key") or "").strip()
        if account_key:
            return f"account:{account_key}"
        managed_source = str(
            metadata.get("managed_seed_source_home")
            or metadata.get("quota_scope_home")
            or ""
        ).strip()
        if managed_source:
            return f"seed:{managed_source}"
    return None


def stamp_runtime_failure(
    metadata: Dict[str, Any],
    *,
    error_code: str,
    auth_type: str = "",
    failure_scope_key: Optional[str] = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    merged_metadata = coerce_json_dict(metadata)
    health = read_health_metadata(merged_metadata, auth_type=auth_type)
    timestamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
    normalized = str(error_code or "").strip().lower()

    next_health_state = health.get("health_state") or default_health_state(
        str(health.get("seed_kind") or "")
    )
    if normalized in {
        "401",
        "403",
        "auth_failure",
        "deactivated_workspace",
        "missing_refresh_token",
        "stale_refresh_token",
        "unauthorized",
    }:
        next_health_state = "quarantined"
        for key in AUTH_MATERIAL_VERSION_KEYS:
            value = str(merged_metadata.get(key) or "").strip()
            if value:
                health[f"failure_{key}"] = value
    elif normalized in {"429", "quota", "rate_limit", "resource_exhausted"}:
        next_health_state = "healthy"
        _stamp_account_snapshot_probe_validated(
            merged_metadata,
            health,
            timestamp=timestamp,
        )
    elif normalized in {"timeout", "stall"}:
        next_health_state = "probation"

    health["health_state"] = next_health_state
    health["last_failure_at"] = timestamp
    health["last_failure_code"] = normalized or None
    health["failure_scope_key"] = str(failure_scope_key or "").strip() or None
    merged_metadata[HEALTH_METADATA_KEY] = health
    return merged_metadata


def _stamp_account_snapshot_probe_validated(
    metadata: Dict[str, Any],
    health: Dict[str, Any],
    *,
    timestamp: str,
) -> None:
    seed_kind = normalize_seed_kind(health.get("seed_kind"))
    if seed_kind != "account_snapshot" and not bool(metadata.get("account_snapshot")):
        return
    if _metadata_is_copied_account_snapshot(
        metadata,
    ) and not _auth_material_newer_than_copy_seed(metadata):
        return
    metadata["runtime_probe_validated_at"] = timestamp
    health["seed_kind"] = "account_home"
