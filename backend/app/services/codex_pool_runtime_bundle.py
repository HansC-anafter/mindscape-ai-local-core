"""
Runtime bundle and candidate helpers for the Codex CLI pool.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .codex_pool_health import (
    auth_failure_scope_key,
    coerce_datetime,
    health_state_rank,
    is_executable_runtime_metadata,
    read_health_metadata,
    read_probe_metadata,
    runtime_probe_available,
    seed_kind_rank,
)

logger = logging.getLogger(__name__)

CODEX_POOL_GROUP = "codex-cli-pool"
BASE_COOLDOWN_SECONDS = 300
MAX_COOLDOWN_SECONDS = 1800
BACKOFF_MULTIPLIER = 3
AUTH_FAILURE_COOLDOWN_SECONDS = 1800
HOST_SESSION_ENV_KEYS = (
    "CODEX_HOME",
    "HOME",
    "XDG_CONFIG_HOME",
    "XDG_DATA_HOME",
    "XDG_STATE_HOME",
)


def truthy_metadata_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "present"}


def build_runtime_bundle(
    runtime: Any,
    auth_service: Any,
) -> Optional[Dict[str, Any]]:
    auth_type = str(getattr(runtime, "auth_type", "") or "none").strip().lower()
    if auth_type == "api_key":
        try:
            decrypted = auth_service.decrypt_credentials(runtime.auth_config or {})
        except Exception:
            logger.exception("Failed to decrypt Codex API key for runtime %s", runtime.id)
            return None
        api_key = str(decrypted.get("api_key") or "").strip()
        if not api_key:
            return None
        return {
            "auth_mode": "openai_api_key",
            "env": {"OPENAI_API_KEY": api_key},
            "runtime_auth_type": auth_type,
        }

    if auth_type in {"host_session", "none"}:
        metadata = dict(getattr(runtime, "extra_metadata", None) or {})
        env = host_session_env_from_metadata(metadata)
        return {
            "auth_mode": "host_session",
            "env": env,
            "runtime_auth_type": "host_session",
        }

    return None


def build_runtime_bundle_from_row(
    runtime: Dict[str, Any],
    auth_service: Any,
) -> Optional[Dict[str, Any]]:
    auth_type = str(runtime.get("auth_type") or "none").strip().lower()
    if auth_type == "api_key":
        auth_config = coerce_json_dict(runtime.get("auth_config"))
        try:
            decrypted = auth_service.decrypt_credentials(auth_config)
        except Exception:
            logger.exception(
                "Failed to decrypt Codex API key for runtime %s via raw SQL path",
                runtime.get("id"),
            )
            return None
        api_key = str(decrypted.get("api_key") or "").strip()
        if not api_key:
            return None
        return {
            "auth_mode": "openai_api_key",
            "env": {"OPENAI_API_KEY": api_key},
            "runtime_auth_type": auth_type,
        }

    if auth_type in {"host_session", "none"}:
        metadata = coerce_json_dict(runtime.get("extra_metadata"))
        env = host_session_env_from_metadata(metadata)
        return {
            "auth_mode": "host_session",
            "env": env,
            "runtime_auth_type": "host_session",
        }

    return None


def host_session_env_from_metadata(metadata: Dict[str, Any]) -> Dict[str, str]:
    env: Dict[str, str] = {}
    codex_home = (
        metadata.get("codex_home")
        or metadata.get("host_session_home")
        or metadata.get("CODEX_HOME")
    )
    if isinstance(codex_home, str) and codex_home.strip():
        env["CODEX_HOME"] = codex_home.strip()

    for key in HOST_SESSION_ENV_KEYS:
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            env[key] = value.strip()

    nested_env = metadata.get("env")
    if isinstance(nested_env, dict):
        for key in HOST_SESSION_ENV_KEYS:
            value = nested_env.get(key)
            if isinstance(value, str) and value.strip():
                env[key] = value.strip()
    return env


def count_recent_quota_errors(runtime: Any) -> int:
    return count_recent_quota_errors_from_values(
        getattr(runtime, "last_error_code", None),
        getattr(runtime, "cooldown_until", None),
    )


def count_recent_quota_errors_from_values(
    last_error_code: Any,
    cooldown_until: Any,
) -> int:
    if str(last_error_code or "") != "429":
        return 0
    if not cooldown_until:
        return 0
    if isinstance(cooldown_until, str):
        try:
            cooldown_until = datetime.fromisoformat(
                cooldown_until.replace("Z", "+00:00")
            )
        except ValueError:
            return 0
    if getattr(cooldown_until, "tzinfo", None) is None:
        cooldown_until = cooldown_until.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    if cooldown_until <= now:
        return 0

    remaining = (cooldown_until - now).total_seconds()
    if remaining <= BASE_COOLDOWN_SECONDS:
        return 0
    if remaining <= BASE_COOLDOWN_SECONDS * BACKOFF_MULTIPLIER:
        return 1
    return 2


def quota_scope_key(runtime: Any) -> Optional[str]:
    metadata = dict(getattr(runtime, "extra_metadata", None) or {})
    return quota_scope_key_from_metadata(metadata)


def quota_scope_key_from_metadata(metadata: Any) -> Optional[str]:
    metadata = coerce_json_dict(metadata)
    account_key = str(metadata.get("account_key") or "").strip()
    if account_key:
        return f"account:{account_key}"

    value = str(metadata.get("quota_scope_key") or "").strip()
    if value:
        return value

    for key in (
        "CODEX_HOME",
        "codex_home",
        "host_session_home",
        "quota_scope_home",
        "managed_seed_source_home",
        "XDG_CONFIG_HOME",
        "HOME",
    ):
        value = str(metadata.get(key) or "").strip()
        if value:
            return f"host_session:{value}"
    return None


def runtime_account_identity_payload(metadata: Any) -> Dict[str, Any]:
    metadata = coerce_json_dict(metadata)
    login_email = str(
        metadata.get("login_email")
        or metadata.get("account_email")
        or metadata.get("email")
        or ""
    ).strip().lower()
    account_label = str(metadata.get("account_label") or "").strip()
    auth_account_id = str(metadata.get("auth_account_id") or "").strip()
    auth_chatgpt_user_id = str(metadata.get("auth_chatgpt_user_id") or "").strip()
    account_key = str(metadata.get("account_key") or "").strip()
    quota_scope_key = str(metadata.get("quota_scope_key") or "").strip()

    if not account_label:
        account_label = (
            login_email
            or auth_chatgpt_user_id
            or auth_account_id
            or account_key
        )

    return {
        "identity_status": "email_verified" if login_email else "email_missing",
        "account_label": account_label or None,
        "login_email": login_email or None,
        "auth_account_id": auth_account_id or None,
        "auth_chatgpt_user_id": auth_chatgpt_user_id or None,
        "account_key": account_key or None,
        "quota_scope_key": quota_scope_key or None,
    }


def count_distinct_quota_scopes(runtimes: list[Any]) -> int:
    scopes = {
        quota_scope_key(runtime) or f"runtime:{getattr(runtime, 'id', '')}"
        for runtime in runtimes
    }
    return len(scopes)


def count_distinct_quota_scopes_from_rows(runtimes: list[Dict[str, Any]]) -> int:
    scopes = {
        quota_scope_key_from_metadata(runtime.get("extra_metadata"))
        or f"runtime:{runtime.get('id')}"
        for runtime in runtimes
    }
    return len(scopes)


def filter_runnable_candidate_runtimes(
    runtimes: list[Any],
    *,
    require_probe_available: bool = False,
) -> list[Any]:
    return [
        runtime
        for runtime in runtimes
        if is_runnable_candidate(
            auth_type=str(getattr(runtime, "auth_type", "") or ""),
            metadata=dict(getattr(runtime, "extra_metadata", None) or {}),
            require_probe_available=require_probe_available,
        )
    ]


def filter_runnable_candidate_runtime_rows(
    runtimes: list[Dict[str, Any]],
    *,
    require_probe_available: bool = False,
) -> list[Dict[str, Any]]:
    return [
        runtime
        for runtime in runtimes
        if is_runnable_candidate(
            auth_type=str(runtime.get("auth_type") or ""),
            metadata=coerce_json_dict(runtime.get("extra_metadata")),
            require_probe_available=require_probe_available,
        )
    ]


def is_runnable_candidate(
    *,
    auth_type: str,
    metadata: Dict[str, Any],
    require_probe_available: bool = False,
) -> bool:
    health = read_health_metadata(metadata, auth_type=auth_type)
    if not is_executable_runtime_metadata(metadata, auth_type=auth_type):
        return False
    if str(health.get("health_state") or "").strip().lower() == "quarantined":
        return False
    if require_probe_available and not runtime_probe_available(metadata):
        return False
    return True


def sort_candidate_runtimes(runtimes: list[Any]) -> list[Any]:
    return sorted(
        runtimes,
        key=lambda runtime: candidate_sort_key_from_values(
            auth_type=str(getattr(runtime, "auth_type", "") or ""),
            metadata=dict(getattr(runtime, "extra_metadata", None) or {}),
            pool_priority=getattr(runtime, "pool_priority", 0),
            last_used_at=getattr(runtime, "last_used_at", None),
            last_error_code=getattr(runtime, "last_error_code", None),
        ),
    )


def sort_candidate_runtime_rows(runtimes: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    return sorted(
        runtimes,
        key=lambda runtime: candidate_sort_key_from_values(
            auth_type=str(runtime.get("auth_type") or ""),
            metadata=coerce_json_dict(runtime.get("extra_metadata")),
            pool_priority=runtime.get("pool_priority"),
            last_used_at=runtime.get("last_used_at"),
            last_error_code=runtime.get("last_error_code"),
        ),
    )


def candidate_sort_key_from_values(
    *,
    auth_type: str,
    metadata: Dict[str, Any],
    pool_priority: Any,
    last_used_at: Any,
    last_error_code: Any,
) -> tuple[Any, ...]:
    health = read_health_metadata(metadata, auth_type=auth_type)
    last_success_at = coerce_datetime(health.get("last_success_at"))
    last_used_dt = coerce_datetime(last_used_at)
    return (
        health_state_rank(str(health.get("health_state") or "")),
        seed_kind_rank(str(health.get("seed_kind") or "")),
        0 if last_success_at else 1,
        -(last_success_at.timestamp()) if last_success_at else 0.0,
        int(pool_priority or 0),
        0 if last_used_dt is None else 1,
        last_used_dt or datetime.min.replace(tzinfo=timezone.utc),
        0 if not str(last_error_code or "").strip() else 1,
    )


def bundle_health_payload(
    metadata: Dict[str, Any],
    *,
    auth_type: str,
) -> Dict[str, Any]:
    health = read_health_metadata(metadata, auth_type=auth_type)
    probe = read_probe_metadata(metadata)
    return {
        "runtime_seed_kind": health.get("seed_kind"),
        "runtime_health_state": health.get("health_state"),
        "metadata_health_state": health.get("health_state"),
        "runtime_failure_scope_key": health.get("failure_scope_key"),
        "probe_state": probe.get("probe_state"),
        "last_probe_success_at": probe.get("last_probe_success_at"),
        "last_probe_error_code": probe.get("last_probe_error_code"),
        "last_probe_runtime_returncode": probe.get("last_probe_runtime_returncode"),
        "last_probe_source_event_id": probe.get("last_probe_source_event_id"),
    }


def failure_scope_key(runtime: Any, error_code: str) -> Optional[str]:
    return auth_failure_scope_key(
        dict(getattr(runtime, "extra_metadata", None) or {}),
        error_code=error_code,
        runtime_id=str(getattr(runtime, "id", "") or ""),
    )


def failure_scope_key_from_metadata(
    metadata: Any,
    *,
    error_code: str,
    runtime_id: str,
) -> Optional[str]:
    return auth_failure_scope_key(
        coerce_json_dict(metadata),
        error_code=error_code,
        runtime_id=runtime_id,
    )


def auth_failure_cooldown_seconds(error_code: str, *, cooldown_seconds: int) -> int:
    normalized = str(error_code or "").strip().lower()
    if normalized in {"timeout", "stall"}:
        return BASE_COOLDOWN_SECONDS
    return max(60, int(cooldown_seconds))


def coerce_json_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        if isinstance(parsed, dict):
            return parsed
    return {}
