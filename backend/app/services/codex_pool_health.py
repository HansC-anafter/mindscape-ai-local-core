from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

HEALTH_METADATA_KEY = "codex_pool_health"
EXECUTABLE_SEED_KINDS = frozenset({"api_key", "real_home", "account_home"})
LEGACY_TOKEN_COPY_SEED_KINDS = frozenset({"managed_mirror", "account_snapshot"})
ACCOUNT_HOME_VALIDATION_KEYS = (
    "codex_exec_validated_at",
    "runtime_probe_validated_at",
)
AUTH_CREDENTIAL_KEYS = ("OPENAI_API_KEY", "access_token", "refresh_token")
AUTH_IDENTITY_KEYS = ("account_id", "id_token")
AUTH_MATERIAL_VERSION_KEYS = (
    "codex_auth_mtime_ns",
    "codex_auth_size",
)
AUTH_FAILURE_CODES = frozenset(
    {
        "401",
        "403",
        "auth_failure",
        "deactivated_workspace",
        "stale_refresh_token",
        "unauthorized",
    }
)
QUOTA_FAILURE_CODES = frozenset({"429", "quota", "rate_limit", "resource_exhausted"})
PROBE_METADATA_KEYS = (
    "probe_state",
    "last_probe_success_at",
    "last_probe_error_code",
    "last_probe_runtime_returncode",
    "last_probe_source_event_id",
)


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


def _runtime_codex_home_value(metadata: Dict[str, Any]) -> Optional[str]:
    value = str(
        metadata.get("CODEX_HOME")
        or metadata.get("codex_home")
        or metadata.get("host_session_home")
        or ""
    ).strip()
    return value or None


def _read_codex_seed_metadata(codex_home: str) -> Dict[str, Any]:
    if not codex_home:
        return {}
    metadata_path = Path(os.path.expanduser(codex_home)) / ".mindscape-seed.json"
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_codex_auth_payload(codex_home: str) -> Dict[str, Any]:
    if not codex_home:
        return {}
    auth_path = Path(os.path.expanduser(codex_home)) / "auth.json"
    try:
        payload = json.loads(auth_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _metadata_truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "present"}


def _auth_payload_tokens(payload: Dict[str, Any]) -> Dict[str, Any]:
    return coerce_json_dict(payload.get("tokens"))


def _auth_payload_has_runtime_credentials(payload: Dict[str, Any]) -> bool:
    tokens = _auth_payload_tokens(payload)
    return any(
        str(payload.get(key) or tokens.get(key) or "").strip()
        for key in AUTH_CREDENTIAL_KEYS
    )


def _auth_payload_has_account_identity(payload: Dict[str, Any]) -> bool:
    tokens = _auth_payload_tokens(payload)
    return any(
        str(payload.get(key) or tokens.get(key) or "").strip()
        for key in AUTH_IDENTITY_KEYS
    )


def codex_home_auth_credentials_present(codex_home: str) -> bool:
    return _auth_payload_has_runtime_credentials(_read_codex_auth_payload(codex_home))


def codex_home_auth_identity_present(codex_home: str) -> bool:
    return _auth_payload_has_account_identity(_read_codex_auth_payload(codex_home))


def _metadata_has_validation_stamp(metadata: Dict[str, Any]) -> bool:
    return any(
        str(metadata.get(key) or "").strip() for key in ACCOUNT_HOME_VALIDATION_KEYS
    )


def _metadata_has_runtime_auth_material(metadata: Dict[str, Any]) -> bool:
    if not _metadata_truthy(metadata.get("codex_auth_has_runtime_credentials")):
        return False
    return any(str(metadata.get(key) or "").strip() for key in AUTH_MATERIAL_VERSION_KEYS)


def _metadata_has_account_identity(metadata: Dict[str, Any]) -> bool:
    return any(
        str(metadata.get(key) or "").strip()
        for key in (
            "login_email",
            "account_key",
            "auth_account_id",
            "auth_chatgpt_user_id",
        )
    )


def _resolved_path_value(value: Any) -> Optional[str]:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return str(Path(os.path.expanduser(raw)).resolve())
    except OSError:
        return str(Path(os.path.expanduser(raw)))


def _metadata_is_copied_account_snapshot(
    metadata: Dict[str, Any],
    *,
    codex_home: Optional[str] = None,
) -> bool:
    resolved_home = _resolved_path_value(
        codex_home or _runtime_codex_home_value(metadata) or ""
    )
    if not resolved_home:
        return False
    for key in ("auth_synced_from_home", "source_home", "seed_source_home"):
        source_home = _resolved_path_value(metadata.get(key))
        if source_home and source_home != resolved_home:
            return True
    return False


def _auth_material_newer_than_copy_seed(
    metadata: Dict[str, Any],
    *,
    codex_home: Optional[str] = None,
) -> bool:
    resolved_home = _resolved_path_value(
        codex_home or _runtime_codex_home_value(metadata) or ""
    )
    if not resolved_home:
        return False
    seed_timestamp = coerce_datetime(
        metadata.get("auth_synced_at")
        or metadata.get("seed_auth_synced_at")
        or metadata.get("updated_at")
        or metadata.get("seed_updated_at")
    )
    if seed_timestamp is None:
        return False
    try:
        auth_mtime = datetime.fromtimestamp(
            (Path(resolved_home) / "auth.json").stat().st_mtime,
            tz=timezone.utc,
        )
    except OSError:
        return False
    return auth_mtime > seed_timestamp


def account_snapshot_is_adopted(
    metadata: Dict[str, Any],
    *,
    codex_home: Optional[str] = None,
) -> bool:
    """Return true only when a copied account snapshot has become a live home."""
    merged_metadata = coerce_json_dict(metadata)
    resolved_home = str(
        codex_home or _runtime_codex_home_value(merged_metadata) or ""
    ).strip()
    seed_metadata = _read_codex_seed_metadata(resolved_home) if resolved_home else {}
    validation_present = _metadata_has_validation_stamp(
        merged_metadata
    ) or _metadata_has_validation_stamp(seed_metadata)
    copied_snapshot = _metadata_is_copied_account_snapshot(
        {**seed_metadata, **merged_metadata},
        codex_home=resolved_home,
    )
    if copied_snapshot and not _auth_material_newer_than_copy_seed(
        {**seed_metadata, **merged_metadata},
        codex_home=resolved_home,
    ):
        if not validation_present:
            return False
        local_auth_present = (
            codex_home_auth_identity_present(resolved_home)
            and codex_home_auth_credentials_present(resolved_home)
        )
        metadata_auth_present = _metadata_has_runtime_auth_material(
            merged_metadata
        ) and _metadata_has_account_identity(merged_metadata)
        if not (local_auth_present or metadata_auth_present):
            return False
    if _metadata_has_validation_stamp(merged_metadata):
        return True
    if (
        _metadata_has_runtime_auth_material(merged_metadata)
        and _metadata_has_account_identity(merged_metadata)
    ):
        return True
    if not resolved_home:
        return False
    if _metadata_has_validation_stamp(seed_metadata):
        return True
    if not bool(seed_metadata.get("account_snapshot")) and not bool(
        merged_metadata.get("account_snapshot")
    ):
        return False
    return False


def _codex_home_sidecar_seed_kind(
    codex_home: str,
    metadata: Dict[str, Any],
) -> Optional[str]:
    seed_metadata = _read_codex_seed_metadata(codex_home)
    if bool(seed_metadata.get("managed_mirror")):
        return "managed_mirror"
    if bool(seed_metadata.get("account_snapshot")):
        return (
            "account_home"
            if account_snapshot_is_adopted(metadata, codex_home=codex_home)
            else "account_snapshot"
        )
    return None


def infer_seed_kind(metadata: Dict[str, Any], *, auth_type: str = "") -> str:
    normalized_auth_type = str(auth_type or "").strip().lower()
    if normalized_auth_type == "api_key":
        return "api_key"

    explicit_seed_kind = normalize_seed_kind(
        metadata.get("codex_seed_kind") or metadata.get("seed_kind")
    )
    if bool(metadata.get("account_snapshot")):
        return (
            "account_home"
            if account_snapshot_is_adopted(metadata)
            else "account_snapshot"
        )
    if explicit_seed_kind == "account_snapshot":
        return (
            "account_home"
            if account_snapshot_is_adopted(metadata)
            else "account_snapshot"
        )
    if explicit_seed_kind in EXECUTABLE_SEED_KINDS | LEGACY_TOKEN_COPY_SEED_KINDS:
        return explicit_seed_kind

    codex_home = str(_runtime_codex_home_value(metadata) or "").strip()
    normalized_home = codex_home.replace("\\", "/")
    if bool(metadata.get("managed_mirror")) or str(
        metadata.get("managed_seed_source_home") or ""
    ).strip():
        return "managed_mirror"
    if "/accounts/acct-" in normalized_home:
        sidecar_seed_kind = _codex_home_sidecar_seed_kind(codex_home, metadata)
        if sidecar_seed_kind:
            return sidecar_seed_kind
        return "account_home"
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
        "login_email",
        "auth_account_id",
        "auth_chatgpt_user_id",
    )
    for key in identity_keys:
        previous_value = _identity_value(previous, key)
        current_value = _identity_value(current, key)
        if previous_value and current_value and previous_value != current_value:
            return True
    return False


def account_principal_identity_changed(
    previous_metadata: Dict[str, Any],
    next_metadata: Dict[str, Any],
) -> bool:
    previous = coerce_json_dict(previous_metadata)
    current = coerce_json_dict(next_metadata)
    for key in (
        "account_key",
        "login_email",
        "auth_account_id",
        "auth_chatgpt_user_id",
    ):
        previous_value = _identity_value(previous, key)
        current_value = _identity_value(current, key)
        if previous_value and current_value and previous_value != current_value:
            return True
    return False


def auth_material_version_changed(
    previous_metadata: Dict[str, Any],
    next_metadata: Dict[str, Any],
) -> bool:
    previous = coerce_json_dict(previous_metadata)
    current = coerce_json_dict(next_metadata)
    for key in AUTH_MATERIAL_VERSION_KEYS:
        previous_value = _identity_value(previous, key)
        current_value = _identity_value(current, key)
        if previous_value and current_value and previous_value != current_value:
            return True
    return False


def auth_material_version_changed_since_failure(
    metadata: Dict[str, Any],
    health: Dict[str, Any],
) -> bool:
    current = coerce_json_dict(metadata)
    previous = coerce_json_dict(health)
    has_current_version = False
    has_failure_version = False
    for key in AUTH_MATERIAL_VERSION_KEYS:
        previous_value = _identity_value(previous, f"failure_{key}")
        current_value = _identity_value(current, key)
        has_current_version = has_current_version or bool(current_value)
        has_failure_version = has_failure_version or bool(previous_value)
        if previous_value and current_value and previous_value != current_value:
            return True
    if has_current_version and not has_failure_version:
        return True
    return False


def default_health_state(seed_kind: str) -> str:
    return "healthy"


def normalize_seed_kind(seed_kind: Any) -> str:
    return str(seed_kind or "").strip().lower()


def is_executable_seed_kind(seed_kind: Any) -> bool:
    return normalize_seed_kind(seed_kind) in EXECUTABLE_SEED_KINDS


def runtime_codex_home(metadata: Dict[str, Any]) -> Optional[str]:
    return _runtime_codex_home_value(metadata)


def runtime_account_identity_present(metadata: Dict[str, Any]) -> bool:
    if any(
        str(metadata.get(key) or "").strip()
        for key in (
            "login_email",
            "account_key",
            "auth_account_id",
            "auth_chatgpt_user_id",
        )
    ):
        return True
    codex_home = str(_runtime_codex_home_value(metadata) or "").strip()
    return bool(codex_home and codex_home_auth_identity_present(codex_home))


def runtime_auth_credentials_present(metadata: Dict[str, Any]) -> bool:
    if _metadata_truthy(metadata.get("codex_auth_has_runtime_credentials")):
        return True
    codex_home = str(_runtime_codex_home_value(metadata) or "").strip()
    return bool(codex_home and codex_home_auth_credentials_present(codex_home))


def read_probe_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    merged_metadata = coerce_json_dict(metadata)
    probe_state = str(merged_metadata.get("probe_state") or "unknown").strip().lower()
    return {
        "probe_state": probe_state or "unknown",
        "last_probe_success_at": str(
            merged_metadata.get("last_probe_success_at") or ""
        ).strip()
        or None,
        "last_probe_error_code": str(
            merged_metadata.get("last_probe_error_code") or ""
        ).strip()
        or None,
        "last_probe_runtime_returncode": merged_metadata.get(
            "last_probe_runtime_returncode"
        ),
        "last_probe_source_event_id": str(
            merged_metadata.get("last_probe_source_event_id") or ""
        ).strip()
        or None,
    }


def runtime_probe_available(metadata: Dict[str, Any]) -> bool:
    probe = read_probe_metadata(metadata)
    return probe.get("probe_state") == "available" and bool(
        coerce_datetime(probe.get("last_probe_success_at"))
    )


def probe_state_for_error_code(error_code: Any) -> str:
    normalized = str(error_code or "").strip().lower()
    if normalized in QUOTA_FAILURE_CODES:
        return "quota_limited"
    if normalized in AUTH_FAILURE_CODES:
        return "auth_failed"
    return "runtime_failed"


def is_executable_runtime_metadata(
    metadata: Dict[str, Any],
    *,
    auth_type: str = "",
) -> bool:
    merged_metadata = coerce_json_dict(metadata)
    health = read_health_metadata(merged_metadata, auth_type=auth_type)
    seed_kind = normalize_seed_kind(health.get("seed_kind"))
    if seed_kind == "api_key":
        return True
    if seed_kind == "real_home":
        return bool(runtime_codex_home(merged_metadata))
    if seed_kind == "account_home":
        return bool(runtime_codex_home(merged_metadata)) and runtime_account_identity_present(
            merged_metadata
        )
    if seed_kind == "account_snapshot":
        return False
    return False


def is_pool_member_runtime_metadata(
    metadata: Dict[str, Any],
    *,
    auth_type: str = "",
) -> bool:
    merged_metadata = coerce_json_dict(metadata)
    health = read_health_metadata(merged_metadata, auth_type=auth_type)
    seed_kind = normalize_seed_kind(health.get("seed_kind"))
    if seed_kind == "managed_mirror":
        return False
    if seed_kind == "api_key":
        return True
    if seed_kind in {"real_home", "account_home"}:
        return bool(runtime_codex_home(merged_metadata))
    return False


def is_legacy_token_copy_seed_kind(seed_kind: Any) -> bool:
    return normalize_seed_kind(seed_kind) in LEGACY_TOKEN_COPY_SEED_KINDS


def read_health_metadata(
    metadata: Dict[str, Any],
    *,
    auth_type: str = "",
) -> Dict[str, Any]:
    merged_metadata = coerce_json_dict(metadata)
    raw_health = coerce_json_dict(merged_metadata.get(HEALTH_METADATA_KEY))
    inferred_seed_kind = infer_seed_kind(
        merged_metadata,
        auth_type=auth_type,
    )
    raw_seed_kind = normalize_seed_kind(raw_health.get("seed_kind"))
    seed_kind = raw_seed_kind or inferred_seed_kind
    if raw_seed_kind == "account_snapshot":
        seed_kind = (
            inferred_seed_kind
            if inferred_seed_kind == "account_home"
            and account_snapshot_is_adopted(merged_metadata)
            else "account_snapshot"
        )
    elif raw_seed_kind == "account_home" and inferred_seed_kind == "account_snapshot":
        seed_kind = "account_snapshot"
    elif raw_seed_kind == "managed_mirror" and not is_legacy_token_copy_seed_kind(
        inferred_seed_kind
    ):
        seed_kind = inferred_seed_kind
    health_state = str(raw_health.get("health_state") or "").strip() or default_health_state(
        seed_kind
    )
    health_payload = {
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
    for key in AUTH_MATERIAL_VERSION_KEYS:
        failure_key = f"failure_{key}"
        value = str(raw_health.get(failure_key) or "").strip()
        if value:
            health_payload[failure_key] = value
    return health_payload


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
    if normalized == "account_home":
        return 2
    if normalized == "managed_mirror":
        return 3
    if normalized == "account_snapshot":
        return 4
    return 5
