from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

HEALTH_METADATA_KEY = "codex_pool_health"


def coerce_json_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    return {}


def _identity_value(metadata: Dict[str, Any], key: str) -> Optional[str]:
    value = str(metadata.get(key) or "").strip()
    return value or None


def coerce_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    return None


def infer_seed_kind(metadata: Dict[str, Any], *, auth_type: str = "") -> str:
    normalized_auth_type = str(auth_type or "").strip().lower()
    if normalized_auth_type == "api_key":
        return "api_key"

    codex_home = str(
        metadata.get("CODEX_HOME")
        or metadata.get("codex_home")
        or metadata.get("host_session_home")
        or ""
    ).strip()
    normalized_home = codex_home.replace("\\", "/")
    if "/accounts/acct-" in normalized_home:
        return "account_snapshot"
    if str(metadata.get("managed_seed_source_home") or "").strip():
        return "managed_mirror"
    return "real_home"


def seed_identity_changed(
    previous_metadata: Dict[str, Any],
    next_metadata: Dict[str, Any],
) -> bool:
    previous = coerce_json_dict(previous_metadata)
    current = coerce_json_dict(next_metadata)
    identity_keys = (
        "account_key",
        "quota_scope_key",
        "quota_scope_home",
        "managed_seed_source_home",
        "CODEX_HOME",
    )
    for key in identity_keys:
        previous_value = _identity_value(previous, key)
        current_value = _identity_value(current, key)
        if previous_value and current_value and previous_value != current_value:
            return True
    return False


def default_health_state(seed_kind: str) -> str:
    return "healthy"


def read_health_metadata(
    metadata: Dict[str, Any],
    *,
    auth_type: str = "",
) -> Dict[str, Any]:
    merged_metadata = coerce_json_dict(metadata)
    raw_health = coerce_json_dict(merged_metadata.get(HEALTH_METADATA_KEY))
    seed_kind = str(raw_health.get("seed_kind") or "").strip() or infer_seed_kind(
        merged_metadata,
        auth_type=auth_type,
    )
    health_state = str(raw_health.get("health_state") or "").strip() or default_health_state(
        seed_kind
    )
    return {
        "seed_kind": seed_kind,
        "health_state": health_state,
        "last_seen_at": str(raw_health.get("last_seen_at") or "").strip() or None,
        "last_selected_at": str(raw_health.get("last_selected_at") or "").strip() or None,
        "last_success_at": str(raw_health.get("last_success_at") or "").strip() or None,
        "last_failure_at": str(raw_health.get("last_failure_at") or "").strip() or None,
        "last_failure_code": str(raw_health.get("last_failure_code") or "").strip() or None,
        "failure_scope_key": str(raw_health.get("failure_scope_key") or "").strip() or None,
        "last_requalified_at": str(raw_health.get("last_requalified_at") or "").strip()
        or None,
        "last_requalification_reason": str(
            raw_health.get("last_requalification_reason") or ""
        ).strip()
        or None,
    }


def stamp_runtime_seen(
    metadata: Dict[str, Any],
    *,
    auth_type: str = "",
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    merged_metadata = coerce_json_dict(metadata)
    health = read_health_metadata(merged_metadata, auth_type=auth_type)
    timestamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
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
    merged_metadata[HEALTH_METADATA_KEY] = health
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

    if normalized in {"401", "403", "deactivated_workspace", "unauthorized"}:
        account_key = str(metadata.get("account_key") or "").strip()
        if account_key:
            return f"account:{account_key}"
        managed_source = str(
            metadata.get("managed_seed_source_home") or metadata.get("quota_scope_home") or ""
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
    if normalized in {"401", "403", "deactivated_workspace", "unauthorized"}:
        next_health_state = "quarantined"
    elif normalized in {"timeout", "stall"}:
        next_health_state = "probation"

    health["health_state"] = next_health_state
    health["last_failure_at"] = timestamp
    health["last_failure_code"] = normalized or None
    health["failure_scope_key"] = str(failure_scope_key or "").strip() or None
    merged_metadata[HEALTH_METADATA_KEY] = health
    return merged_metadata


def health_state_rank(health_state: str) -> int:
    normalized = str(health_state or "").strip().lower()
    if normalized == "healthy":
        return 0
    if normalized == "probation":
        return 1
    if normalized == "quarantined":
        return 2
    return 3


def seed_kind_rank(seed_kind: str) -> int:
    normalized = str(seed_kind or "").strip().lower()
    if normalized == "api_key":
        return 0
    if normalized == "real_home":
        return 1
    if normalized == "managed_mirror":
        return 2
    if normalized == "account_snapshot":
        return 3
    return 4
