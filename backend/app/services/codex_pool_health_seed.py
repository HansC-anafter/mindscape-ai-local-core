from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from .codex_pool_health_core import (
    AUTH_MATERIAL_VERSION_KEYS,
    EXECUTABLE_SEED_KINDS,
    LEGACY_TOKEN_COPY_SEED_KINDS,
    _identity_value,
    _metadata_has_account_identity,
    _metadata_has_runtime_auth_material,
    _metadata_has_validation_stamp,
    _metadata_truthy,
    _read_codex_seed_metadata,
    _resolved_path_value,
    _runtime_codex_home_value,
    codex_home_auth_credentials_present,
    codex_home_auth_identity_present,
    coerce_datetime,
    coerce_json_dict,
)


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
