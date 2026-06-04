"""Resource governance context for global and workspace-scoped control."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from backend.app.dependencies.auth import AuthContext, get_default_user_id


DEFAULT_GLOBAL_ADMIN_USER_ID = "default_user"
DEFAULT_GLOBAL_ADMIN_ALIASES = {
    DEFAULT_GLOBAL_ADMIN_USER_ID,
    "default-user",
}


def _clean_string(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _clean_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in (_clean_string(raw) for raw in value) if item]


def is_global_resource_admin(auth_context: AuthContext) -> bool:
    user_id = _clean_string(getattr(auth_context, "user_id", None))
    if not user_id:
        return False
    if user_id in DEFAULT_GLOBAL_ADMIN_ALIASES:
        return True
    try:
        return user_id == _clean_string(get_default_user_id())
    except Exception:
        return False


def require_global_resource_admin(auth_context: AuthContext) -> None:
    if is_global_resource_admin(auth_context):
        return
    raise HTTPException(
        status_code=403,
        detail={
            "reason": "global_resource_admin_required",
            "user_id": _clean_string(getattr(auth_context, "user_id", None)),
        },
    )


def require_workspace_resource_access(
    auth_context: AuthContext,
    workspace_id: str | None,
) -> str:
    normalized_workspace_id = _clean_string(workspace_id)
    if not normalized_workspace_id:
        raise HTTPException(
            status_code=400,
            detail={"reason": "workspace_id_required"},
        )
    if is_global_resource_admin(auth_context):
        return normalized_workspace_id
    workspace_ids = set(_clean_string_list(getattr(auth_context, "workspace_ids", [])))
    if normalized_workspace_id not in workspace_ids:
        raise HTTPException(
            status_code=403,
            detail={
                "reason": "workspace_resource_access_denied",
                "workspace_id": normalized_workspace_id,
            },
        )
    return normalized_workspace_id


def build_resource_governance_context(
    auth_context: AuthContext,
    *,
    workspace_id: str | None = None,
    requested_mode: str | None = None,
) -> dict[str, Any]:
    workspace_ids = _clean_string_list(getattr(auth_context, "workspace_ids", []))
    requested_workspace_id = _clean_string(workspace_id)
    normalized_mode = _clean_string(requested_mode)
    is_global_admin = is_global_resource_admin(auth_context)

    selected_workspace_id: str | None = None
    if requested_workspace_id:
        selected_workspace_id = require_workspace_resource_access(
            auth_context,
            requested_workspace_id,
        )
    elif not is_global_admin:
        selected_workspace_id = workspace_ids[0] if workspace_ids else None

    mode = "global" if is_global_admin and not selected_workspace_id else "workspace"
    if normalized_mode == "workspace":
        mode = "workspace"
    if normalized_mode == "global" and is_global_admin and not selected_workspace_id:
        mode = "global"

    return {
        "mode": mode,
        "requested_mode": normalized_mode,
        "scope": "global_admin" if is_global_admin and mode == "global" else "workspace",
        "is_global_admin": is_global_admin,
        "user_id": _clean_string(getattr(auth_context, "user_id", None)),
        "tenant_id": _clean_string(getattr(auth_context, "tenant_id", None)),
        "workspace_id": selected_workspace_id,
        "workspace_ids": workspace_ids,
        "can_manage_global": is_global_admin,
        "can_manage_workspace_allocations": bool(
            is_global_admin or selected_workspace_id
        ),
        "resource_control": {
            "can_register_host_slots": is_global_admin,
            "can_manage_global_lanes": is_global_admin,
            "can_manage_workspace_allocations": bool(
                is_global_admin or selected_workspace_id
            ),
        },
    }
