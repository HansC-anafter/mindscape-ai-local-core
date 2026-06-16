from __future__ import annotations

from typing import Any, Dict

from .codex_pool_health_core import (
    AUTH_FAILURE_CODES,
    AUTH_MATERIAL_VERSION_KEYS,
    HEALTH_METADATA_KEY,
    INCONCLUSIVE_PROBE_FAILURE_CODES,
    LEGACY_TOKEN_COPY_SEED_KINDS,
    QUOTA_FAILURE_CODES,
    coerce_datetime,
    coerce_json_dict,
)
from .codex_pool_health_seed import (
    account_snapshot_is_adopted,
    default_health_state,
    infer_seed_kind,
    normalize_seed_kind,
    runtime_account_identity_present,
    runtime_codex_home,
)


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
    if normalized in INCONCLUSIVE_PROBE_FAILURE_CODES:
        return "probe_inconclusive"
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
