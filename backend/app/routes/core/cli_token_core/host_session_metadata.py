import hashlib
import json
import logging
import time
from typing import Any, Optional

from backend.app.services.codex_pool_health import (
    AUTH_FAILURE_CODES,
    HEALTH_METADATA_KEY,
    account_principal_identity_changed,
    auth_material_version_changed,
    auth_material_version_changed_since_failure,
    infer_seed_kind,
    is_executable_runtime_metadata,
    is_pool_member_runtime_metadata,
    read_health_metadata,
    seed_identity_changed,
    stamp_runtime_requalified,
    stamp_runtime_seen,
)

logger = logging.getLogger(__name__)

_HOST_SESSION_OWNER_CACHE: dict[str, tuple[float, Optional[str]]] = {}
_HOST_SESSION_OWNER_CACHE_TTL_SECONDS = 300.0
_HOST_SESSION_OWNER_FAILURE_CACHE_TTL_SECONDS = 5.0

_HOST_SESSION_EXECUTION_ENV_KEYS = (
    "CODEX_HOME",
    "HOME",
    "XDG_CONFIG_HOME",
    "XDG_DATA_HOME",
    "XDG_STATE_HOME",
)


def _default_pool_group_for_surface(surface: str) -> Optional[str]:
    normalized = (surface or "").strip().lower()
    if normalized == "codex_cli":
        return "codex-cli-pool"
    if normalized == "gemini_cli":
        return "gca-pool"
    return None


def _coerce_json_dict(value: Any) -> dict[str, Any]:
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


def _normalize_host_session_account_identity(metadata: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(metadata)
    email = str(
        normalized.get("login_email")
        or normalized.get("account_email")
        or normalized.get("email")
        or ""
    ).strip().lower()
    if email:
        normalized["login_email"] = email
        normalized.pop("account_email", None)
        normalized.pop("email", None)

    account_label = str(normalized.get("account_label") or "").strip()
    if not account_label:
        for key in (
            "login_email",
            "auth_chatgpt_user_id",
            "auth_account_id",
            "account_key",
        ):
            value = str(normalized.get(key) or "").strip()
            if value:
                account_label = value
                break
    if account_label:
        normalized["account_label"] = account_label
    return normalized


def _host_session_execution_env_changed(
    previous_metadata: dict[str, Any],
    merged_metadata: dict[str, Any],
) -> bool:
    for key in _HOST_SESSION_EXECUTION_ENV_KEYS:
        previous_value = str(previous_metadata.get(key) or "").strip()
        next_value = str(merged_metadata.get(key) or "").strip()
        if previous_value != next_value:
            return True
    return False


def _prepare_host_session_runtime_metadata(
    *,
    existing_metadata: Any,
    incoming_metadata: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    previous_metadata = _coerce_json_dict(existing_metadata)
    merged_metadata = dict(previous_metadata)
    merged_metadata.update(_normalize_host_session_account_identity(incoming_metadata))

    previous_health = read_health_metadata(previous_metadata, auth_type="host_session")
    next_seed_kind = infer_seed_kind(merged_metadata, auth_type="host_session")
    previous_seed_kind = str(previous_health.get("seed_kind") or "").strip().lower()
    previous_failure_code = str(previous_health.get("last_failure_code") or "").strip().lower()
    auth_failure_active = previous_failure_code in AUTH_FAILURE_CODES
    reset_reason = "account_identity_changed"
    if auth_failure_active:
        principal_identity_changed = account_principal_identity_changed(
            previous_metadata,
            merged_metadata,
        )
        material_changed = auth_material_version_changed(
            previous_metadata,
            merged_metadata,
        ) or auth_material_version_changed_since_failure(
            merged_metadata,
            previous_health,
        )
        execution_env_changed = _host_session_execution_env_changed(
            previous_metadata,
            merged_metadata,
        )
        reset_runtime_health = (
            principal_identity_changed or material_changed or execution_env_changed
        )
        if execution_env_changed and not (
            principal_identity_changed or material_changed
        ):
            reset_reason = "execution_env_changed"
        elif material_changed and not principal_identity_changed:
            reset_reason = "auth_material_changed"
    else:
        reset_runtime_health = seed_identity_changed(previous_metadata, merged_metadata)
        reset_runtime_health = reset_runtime_health or (
            bool(previous_seed_kind)
            and bool(next_seed_kind)
            and previous_seed_kind != next_seed_kind
        )
    reset_runtime_health = reset_runtime_health or (
        previous_failure_code == "legacy_token_copy_seed"
        and is_executable_runtime_metadata(merged_metadata, auth_type="host_session")
    )
    if reset_runtime_health:
        merged_health = _coerce_json_dict(merged_metadata.get(HEALTH_METADATA_KEY))
        merged_health["seed_kind"] = next_seed_kind
        merged_health["health_state"] = "healthy"
        merged_metadata[HEALTH_METADATA_KEY] = merged_health
        merged_metadata = stamp_runtime_requalified(
            merged_metadata,
            auth_type="host_session",
            reason=reset_reason,
        )

    merged_metadata = stamp_runtime_seen(
        merged_metadata,
        auth_type="host_session",
    )
    return merged_metadata, reset_runtime_health


def _effective_host_session_pool_enabled(
    metadata: dict[str, Any],
    *,
    requested_pool_enabled: bool,
) -> bool:
    if not requested_pool_enabled:
        return False
    return is_pool_member_runtime_metadata(metadata, auth_type="host_session")


def _is_plain_host_session_metadata(metadata: dict[str, Any]) -> bool:
    return not str(metadata.get("CODEX_HOME") or metadata.get("codex_home") or "").strip()


def _clear_stale_shadow_marker(
    metadata: dict[str, Any],
    *,
    pool_enabled: bool,
) -> dict[str, Any]:
    if pool_enabled and _is_plain_host_session_metadata(metadata):
        metadata.pop("shadowed_by_runtime_id", None)
    return metadata


def _can_shadow_host_session_candidate(
    candidate_metadata: dict[str, Any],
    *,
    request_workspace_id: str,
) -> bool:
    if not is_executable_runtime_metadata(candidate_metadata, auth_type="host_session"):
        return False
    health = read_health_metadata(candidate_metadata, auth_type="host_session")
    if str(health.get("seed_kind") or "").strip().lower() == "real_home":
        return False
    candidate_workspace_id = str(
        candidate_metadata.get("last_workspace_id") or ""
    ).strip()
    request_workspace_id = str(request_workspace_id or "").strip()
    return bool(candidate_workspace_id and request_workspace_id) and (
        candidate_workspace_id == request_workspace_id
    )


def _load_workspace_owner_user_id(workspace_id: str) -> Optional[str]:
    workspace_id = str(workspace_id or "").strip()
    if not workspace_id:
        return None
    now = time.monotonic()
    cached = _HOST_SESSION_OWNER_CACHE.get(workspace_id)
    if cached and cached[0] > now:
        return cached[1]

    try:
        from backend.app.services.stores.postgres.workspaces_store import PostgresWorkspacesStore

        workspace = PostgresWorkspacesStore().get_workspace_sync(workspace_id)
        owner_user_id = getattr(workspace, "owner_user_id", None) if workspace else None
        _HOST_SESSION_OWNER_CACHE[workspace_id] = (
            now + _HOST_SESSION_OWNER_CACHE_TTL_SECONDS,
            owner_user_id,
        )
        return owner_user_id
    except Exception as exc:
        stale_owner_user_id = cached[1] if cached else None
        if stale_owner_user_id:
            _HOST_SESSION_OWNER_CACHE[workspace_id] = (
                now + _HOST_SESSION_OWNER_FAILURE_CACHE_TTL_SECONDS,
                stale_owner_user_id,
            )
            logger.warning(
                (
                    "Failed to resolve workspace owner for host-session runtime "
                    "registration; using cached owner for workspace=%s: %s"
                ),
                workspace_id,
                exc,
            )
            return stale_owner_user_id

        _HOST_SESSION_OWNER_CACHE[workspace_id] = (
            now + _HOST_SESSION_OWNER_FAILURE_CACHE_TTL_SECONDS,
            None,
        )
        logger.warning(
            (
                "Failed to resolve workspace owner for host-session runtime "
                "registration; suppressing repeated lookup briefly for workspace=%s: %s"
            ),
            workspace_id,
            exc,
        )
        return None


def _stable_host_session_runtime_id(
    *,
    owner_user_id: str,
    surface: str,
    client_id: Optional[str],
    metadata: dict[str, Any],
    workspace_id: Optional[str] = None,
    explicit_runtime_id: Optional[str] = None,
) -> str:
    explicit = str(explicit_runtime_id or "").strip()
    if explicit:
        return explicit

    home_hint = ""
    for key in (
        "CODEX_HOME",
        "codex_home",
        "host_session_home",
        "HOME",
        "XDG_CONFIG_HOME",
    ):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            home_hint = value.strip()
            break
    if not home_hint:
        home_hint = str(client_id or "default").strip() or "default"

    digest_parts = [owner_user_id, surface]
    workspace_scope = str(workspace_id or "").strip()
    if workspace_scope and _is_plain_host_session_metadata(metadata):
        digest_parts.append(workspace_scope)
    digest_parts.append(home_hint)
    digest = hashlib.sha1("|".join(digest_parts).encode("utf-8")).hexdigest()[:12]
    normalized_surface = "".join(
        ch if ch.isalnum() or ch in ("-", "_") else "-"
        for ch in (surface or "cli")
    ).strip("-") or "cli"
    return f"runtime-{normalized_surface}-{digest}"
