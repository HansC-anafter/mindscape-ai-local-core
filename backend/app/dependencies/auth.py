"""
Dashboard authentication
Pluggable design: Local mode uses default_user, Cloud mode uses cloud-integration token
"""

import logging
from dataclasses import dataclass, field
from typing import List, Optional
from urllib.parse import urlsplit

from fastapi import HTTPException, Request

from ..utils.cloud_integration import (
    get_cloud_integration_api_base,
    is_cloud_mode_enabled,
)

logger = logging.getLogger(__name__)

LOCAL_CONTROL_OPERATOR_USER_ID = "local-core-control-plane"
DEFAULT_LOCAL_USER_ID = "default-user"
_LOCAL_OPERATOR_HOSTNAMES = {"localhost", "127.0.0.1", "::1"}


@dataclass
class AuthContext:
    """Authentication context (aligned with cloud-integration contract)"""
    user_id: str
    tenant_id: str
    workspace_ids: List[str] = field(default_factory=list)
    group_ids: List[str] = field(default_factory=list)
    is_cloud_mode: bool = False


def is_cloud_mode() -> bool:
    """
    Detect if running in Cloud mode

    Condition: cloud-integration API base is configured
    """
    return is_cloud_mode_enabled()


def get_default_user_id() -> str:
    """
    Get default user ID for Local mode

    Priority:
    1. default_user_id from system settings
    2. Canonical local profile "default-user"
    """
    try:
        from ..services.system_settings_store import SystemSettingsStore
        from ..services.mindscape_store import MindscapeStore

        store = MindscapeStore()
        settings_store = SystemSettingsStore(db_path=store.db_path)

        user_setting = settings_store.get_setting("default_user_id")
        if user_setting and user_setting.value:
            return user_setting.value
    except Exception as e:
        logger.warning(f"Failed to get default_user_id: {e}")

    return DEFAULT_LOCAL_USER_ID


async def get_auth_from_cloud_integration_token(token: str) -> Optional[AuthContext]:
    """
    Parse identity from cloud-integration token (Cloud mode)

    Calls cloud-integration /api/v1/auth/me to validate token and get user info
    """
    try:
        import httpx

        api_base = get_cloud_integration_api_base()
        if not api_base:
            return None

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{api_base}/api/v1/auth/me",
                headers={"Authorization": f"Bearer {token}"},
                timeout=5.0
            )
            if resp.status_code == 200:
                data = resp.json()
                return AuthContext(
                    user_id=data.get("user_id", ""),
                    tenant_id=data.get("tenant_id", ""),
                    workspace_ids=data.get("workspace_ids", []),
                    group_ids=data.get("group_ids", []),
                    is_cloud_mode=True,
                )
            else:
                logger.warning(f"cloud-integration auth failed: {resp.status_code}")
                return None
    except Exception as e:
        logger.error(f"Failed to get auth from cloud-integration token: {e}")
        return None


async def get_auth_from_cloud_generation_token(token: str) -> Optional[AuthContext]:
    """Backward-compatible alias."""
    return await get_auth_from_cloud_integration_token(token)


async def get_auth_from_site_hub_token(token: str) -> Optional[AuthContext]:
    """
    Backward-compatible alias.
    Prefer get_auth_from_cloud_integration_token().
    """
    return await get_auth_from_cloud_integration_token(token)


def _get_local_workspace_ids(user_id: str) -> List[str]:
    """Load local workspace scope only for callers that explicitly need it."""
    try:
        from ..services.mindscape_store import MindscapeStore

        store = MindscapeStore()
        workspaces = store.list_workspaces(owner_user_id=user_id, limit=200)
        return [ws.id for ws in workspaces if not getattr(ws, 'is_system', False)]
    except Exception as e:
        logger.warning(f"Failed to get workspace_ids: {e}")
        return []


def _validate_local_operator_origin(request: Request) -> None:
    """Reject browser policy traffic that did not originate on loopback."""
    origin = request.headers.get("origin")
    if origin is None:
        origin = request.headers.get("Origin")
    if origin is None:
        return
    if not isinstance(origin, str) or not origin or origin != origin.strip():
        raise HTTPException(
            status_code=403,
            detail="local_operator_origin_forbidden",
        )

    try:
        parsed = urlsplit(origin)
        parsed_port = parsed.port
    except ValueError as exc:
        raise HTTPException(
            status_code=403,
            detail="local_operator_origin_forbidden",
        ) from exc

    if (
        parsed.scheme not in {"http", "https"}
        or parsed.hostname not in _LOCAL_OPERATOR_HOSTNAMES
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
        or (parsed_port is not None and not 1 <= parsed_port <= 65535)
    ):
        raise HTTPException(
            status_code=403,
            detail="local_operator_origin_forbidden",
        )


async def _get_authenticated_context(
    request: Request,
    *,
    include_local_workspace_ids: bool,
    local_user_id: Optional[str] = None,
    allow_cloud_auth: bool = True,
    enforce_local_operator_origin: bool = False,
) -> AuthContext:
    """Resolve an authenticated identity with an optional workspace projection."""
    # Cloud mode
    if is_cloud_mode():
        if not allow_cloud_auth:
            raise HTTPException(
                status_code=403,
                detail="cloud_operator_role_required",
            )
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            # R2: Cloud mode must have token
            raise HTTPException(
                status_code=401,
                detail="Authorization header required in cloud mode"
            )

        token = auth_header[7:]
        auth = await get_auth_from_cloud_integration_token(token)
        if not auth:
            # R2: token validation failed -> 401
            raise HTTPException(
                status_code=401,
                detail="Invalid or expired token"
            )
        return auth

    # Local mode: use default_user
    if enforce_local_operator_origin:
        _validate_local_operator_origin(request)
    user_id = local_user_id or get_default_user_id()

    workspace_ids = (
        _get_local_workspace_ids(user_id)
        if include_local_workspace_ids
        else []
    )

    return AuthContext(
        user_id=user_id,
        tenant_id="local",
        workspace_ids=workspace_ids,
        group_ids=[],
        is_cloud_mode=False,
    )


async def get_current_user(request: Request) -> AuthContext:
    """
    Get the current user with local workspace scope (FastAPI dependency).

    Hard rules:
    - R1: Do not get user_id from query parameters
    - R2: Cloud mode without valid token -> 401 (no fallback)
    """
    cached = getattr(request.state, "mindscape_auth_context", None)
    if isinstance(cached, AuthContext):
        return cached
    context = await _get_authenticated_context(
        request,
        include_local_workspace_ids=True,
    )
    request.state.mindscape_auth_context = context
    return context


async def get_current_identity(request: Request) -> AuthContext:
    """Get only the authenticated identity without loading workspace scope."""
    scoped_context = getattr(request.state, "mindscape_auth_context", None)
    if isinstance(scoped_context, AuthContext):
        return scoped_context

    cached = getattr(request.state, "mindscape_identity_context", None)
    if isinstance(cached, AuthContext):
        return cached

    context = await _get_authenticated_context(
        request,
        include_local_workspace_ids=False,
    )
    request.state.mindscape_identity_context = context
    return context


async def get_current_operator(request: Request) -> AuthContext:
    """Authenticate loopback control traffic without local identity reads."""
    return await _get_authenticated_context(
        request,
        include_local_workspace_ids=False,
        local_user_id=LOCAL_CONTROL_OPERATOR_USER_ID,
        allow_cloud_auth=False,
        enforce_local_operator_origin=True,
    )
