"""
Dashboard authentication
Pluggable design: Local mode uses default_user, Cloud mode uses site-hub token
"""

import os
import logging
from typing import Optional, List
from dataclasses import dataclass, field
from fastapi import Request, HTTPException

logger = logging.getLogger(__name__)


@dataclass
class AuthContext:
    """Authentication context (aligned with site-hub contract)"""
    user_id: str
    tenant_id: str
    workspace_ids: List[str] = field(default_factory=list)
    group_ids: List[str] = field(default_factory=list)
    is_cloud_mode: bool = False


def is_cloud_mode() -> bool:
    """
    Detect if running in Cloud mode

    Condition: SITE_HUB_API_BASE is configured (token validation happens at request time)
    """
    return bool(os.getenv("SITE_HUB_API_BASE"))


def get_default_user_id() -> str:
    """
    Get default user ID for Local mode

    Priority:
    1. default_user_id from system settings
    2. Hardcoded "default_user"
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

    return "default_user"


async def get_auth_from_site_hub_token(token: str) -> Optional[AuthContext]:
    """
    Parse identity from site-hub token (Cloud mode)

    Calls site-hub /api/v1/auth/me to validate token and get user info
    """
    try:
        import httpx

        site_hub_base = os.getenv("SITE_HUB_API_BASE")
        if not site_hub_base:
            return None

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{site_hub_base}/api/v1/auth/me",
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
                logger.warning(f"site-hub auth failed: {resp.status_code}")
                return None
    except Exception as e:
        logger.error(f"Failed to get auth from site-hub token: {e}")
        return None


async def get_current_user(request: Request) -> AuthContext:
    """
    Get current user (FastAPI Dependency)

    Hard rules:
    - R1: Do not get user_id from query parameters
    - R2: Cloud mode without valid token -> 401 (no fallback)
    """
    # Cloud mode
    if is_cloud_mode():
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            # R2: Cloud mode must have token
            raise HTTPException(
                status_code=401,
                detail="Authorization header required in cloud mode"
            )

        token = auth_header[7:]
        auth = await get_auth_from_site_hub_token(token)
        if not auth:
            # R2: token validation failed -> 401
            raise HTTPException(
                status_code=401,
                detail="Invalid or expired token"
            )
        return auth

    # Local mode: use default_user
    user_id = get_default_user_id()

    # Get user-accessible workspace IDs
    workspace_ids = []
    try:
        from ..services.mindscape_store import MindscapeStore
        store = MindscapeStore()
        workspaces = store.list_workspaces(owner_user_id=user_id, limit=200)
        workspace_ids = [ws.id for ws in workspaces if not getattr(ws, 'is_system', False)]
    except Exception as e:
        logger.warning(f"Failed to get workspace_ids: {e}")

    return AuthContext(
        user_id=user_id,
        tenant_id="local",
        workspace_ids=workspace_ids,
        group_ids=[],
        is_cloud_mode=False,
    )

