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
        "missing_refresh_token",
        "stale_refresh_token",
        "unauthorized",
    }
)
QUOTA_FAILURE_CODES = frozenset({"429", "quota", "rate_limit", "resource_exhausted"})
INCONCLUSIVE_PROBE_FAILURE_CODES = frozenset(
    {
        "timeout",
        "runtime_error",
        "probe_transport_error",
        "codex_cli_panic",
        "token_refresh_persist_failed",
    }
)
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
