from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from backend.app.routes.core.cli_token_core.host_session_metadata import (
    _load_workspace_owner_user_id,
)
from backend.app.routes.core.cli_token_core.host_session_registration import (
    _register_host_session_runtime,
)
from backend.app.routes.core.cli_token_core.schemas import (
    RegisterHostSessionRuntimeBatchRequest,
    RegisterHostSessionRuntimeRequest,
)

_HOST_SESSION_SURFACE = "codex_cli"


def _validate_host_session_surface(request: RegisterHostSessionRuntimeRequest) -> str:
    surface_name = str(request.surface or "").strip().lower()
    if surface_name != _HOST_SESSION_SURFACE:
        raise HTTPException(
            status_code=400,
            detail=(
                "Host-session runtime registration is not implemented for "
                f"{surface_name}"
            ),
        )
    return surface_name


def _resolve_host_session_owner(
    request: RegisterHostSessionRuntimeRequest,
    *,
    owner_user_id: str | None = None,
) -> str:
    resolved = str(owner_user_id or request.owner_user_id or "").strip()
    if not resolved:
        resolved = _load_workspace_owner_user_id(request.workspace_id) or ""
    if not resolved:
        raise HTTPException(
            status_code=404,
            detail=f"Workspace not found or owner unavailable: {request.workspace_id}",
        )
    return resolved


def _register_host_session_runtime_request(
    request: RegisterHostSessionRuntimeRequest,
    *,
    owner_user_id: str | None = None,
) -> dict[str, Any]:
    _validate_host_session_surface(request)
    resolved_owner_user_id = _resolve_host_session_owner(
        request,
        owner_user_id=owner_user_id,
    )
    runtime = _register_host_session_runtime(
        owner_user_id=resolved_owner_user_id,
        request=request,
    )
    return {
        "registered": True,
        "runtime_id": runtime.get("runtime_id") or runtime.get("id"),
        "owner_user_id": resolved_owner_user_id,
        "runtime": runtime,
    }


def _validate_batch_scope(
    request: RegisterHostSessionRuntimeBatchRequest,
) -> tuple[str, str]:
    runtimes = request.runtimes
    workspace_id = str(runtimes[0].workspace_id or "").strip()
    surface_name = _validate_host_session_surface(runtimes[0])
    owner_hints = {
        str(item.owner_user_id or "").strip()
        for item in runtimes
        if str(item.owner_user_id or "").strip()
    }

    for item in runtimes[1:]:
        if str(item.workspace_id or "").strip() != workspace_id:
            raise HTTPException(
                status_code=400,
                detail="Host-session runtime batch must contain one workspace",
            )
        if _validate_host_session_surface(item) != surface_name:
            raise HTTPException(
                status_code=400,
                detail="Host-session runtime batch must contain one surface",
            )
    if len(owner_hints) > 1:
        raise HTTPException(
            status_code=400,
            detail="Host-session runtime batch must contain one owner",
        )
    return workspace_id, next(iter(owner_hints), "")


def _register_host_session_runtime_batch_request(
    request: RegisterHostSessionRuntimeBatchRequest,
) -> dict[str, Any]:
    _workspace_id, owner_hint = _validate_batch_scope(request)
    owner_user_id = _resolve_host_session_owner(
        request.runtimes[0],
        owner_user_id=owner_hint,
    )
    responses = [
        _register_host_session_runtime_request(
            item,
            owner_user_id=owner_user_id,
        )
        for item in request.runtimes
    ]
    primary = dict(responses[0])
    registered_runtime_ids = [
        str(item.get("runtime_id") or "").strip()
        for item in responses
        if str(item.get("runtime_id") or "").strip()
    ]
    primary["registered_runtime_ids"] = registered_runtime_ids
    primary["registered_runtime_count"] = len(registered_runtime_ids)
    return primary
