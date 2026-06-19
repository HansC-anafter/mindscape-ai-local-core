"""
Workspace-scoped Agent Availability API compatibility entrypoint.
"""

from typing import Optional

from backend.app.services.external_agents.core.registry import get_runtime_registry

from .workspace_agents_core import account_home_routes as _account_home_routes
from .workspace_agents_core import auth_routes as _auth_routes
from .workspace_agents_core import bridge_service_routes as _bridge_service_routes
from .workspace_agents_core import listing_routes as _listing_routes
from .workspace_agents_core import runtime_control as _runtime_control
from .workspace_agents_core.account_home_paths import (
    _account_home_env,
    _default_codex_account_home_root,
    _ensure_codex_account_home_dirs,
    _has_codex_account_home_target,
    _is_managed_codex_account_home,
    _new_codex_account_home_path,
    _normalize_codex_home_path,
)
from .workspace_agents_core.account_home_probe import (
    _codex_identity_from_result,
    _persist_codex_account_home_login_metadata,
    _persist_codex_account_home_probe_result,
    _validate_codex_account_home_login_identity,
)
from .workspace_agents_core.account_home_targets import (
    _iso_value,
    _list_codex_account_home_targets,
    _resolve_codex_account_home_inputs,
)
from .workspace_agents_core.router import router
from .workspace_agents_core.runtime_control import (
    _classify_codex_status,
    _raise_agent_control_failure,
)
from .workspace_agents_core.schemas import (
    CodexAccountHomeCreateRequest,
    CodexAccountHomeTarget,
    CodexAccountHomeTargetsResponse,
    WorkspaceAgentAuthActionRequest,
    WorkspaceAgentAuthActionResponse,
    WorkspaceAgentAuthStatus,
    WorkspaceAgentInfo,
    WorkspaceAgentListResponse,
)


def _sync_listing_route_helpers() -> None:
    _listing_routes.get_runtime_registry = get_runtime_registry
    _listing_routes._resolve_agent_availability = _resolve_agent_availability
    _listing_routes._execute_agent_control = _execute_agent_control
    _listing_routes._classify_codex_status = _classify_codex_status


def _sync_account_home_route_helpers() -> None:
    _account_home_routes._account_home_env = _account_home_env
    _account_home_routes._ensure_codex_account_home_dirs = (
        _ensure_codex_account_home_dirs
    )
    _account_home_routes._has_codex_account_home_target = (
        _has_codex_account_home_target
    )
    _account_home_routes._is_managed_codex_account_home = (
        _is_managed_codex_account_home
    )
    _account_home_routes._new_codex_account_home_path = _new_codex_account_home_path
    _account_home_routes._normalize_codex_home_path = _normalize_codex_home_path
    _account_home_routes._list_codex_account_home_targets = (
        _list_codex_account_home_targets
    )
    _account_home_routes._resolve_codex_account_home_inputs = (
        _resolve_codex_account_home_inputs
    )
    _account_home_routes._persist_codex_account_home_probe_result = (
        _persist_codex_account_home_probe_result
    )
    _account_home_routes._execute_agent_control = _execute_agent_control
    _account_home_routes._raise_agent_control_failure = _raise_agent_control_failure
    _account_home_routes._resolve_agent_availability = _resolve_agent_availability


def _sync_auth_route_helpers() -> None:
    _auth_routes._ensure_codex_account_home_dirs = _ensure_codex_account_home_dirs
    _auth_routes._has_codex_account_home_target = _has_codex_account_home_target
    _auth_routes._codex_identity_from_result = _codex_identity_from_result
    _auth_routes._persist_codex_account_home_login_metadata = (
        _persist_codex_account_home_login_metadata
    )
    _auth_routes._validate_codex_account_home_login_identity = (
        _validate_codex_account_home_login_identity
    )
    _auth_routes._resolve_codex_account_home_inputs = (
        _resolve_codex_account_home_inputs
    )
    _auth_routes._execute_agent_control = _execute_agent_control
    _auth_routes._raise_agent_control_failure = _raise_agent_control_failure
    _auth_routes._resolve_agent_availability = _resolve_agent_availability


async def _resolve_agent_availability(workspace_id: str, agent_id: str):
    _runtime_control.get_runtime_registry = get_runtime_registry
    return await _runtime_control._resolve_agent_availability(workspace_id, agent_id)


async def _execute_agent_control(workspace, agent_id: str, control_action: str, inputs=None):
    _runtime_control.get_runtime_registry = get_runtime_registry
    return await _runtime_control._execute_agent_control(
        workspace,
        agent_id,
        control_action,
        inputs,
    )


async def list_workspace_agents(*args, **kwargs):
    _sync_listing_route_helpers()
    return await _listing_routes.list_workspace_agents(*args, **kwargs)


async def get_workspace_agent_auth_status(*args, **kwargs):
    _sync_listing_route_helpers()
    return await _listing_routes.get_workspace_agent_auth_status(*args, **kwargs)


async def get_workspace_agent_bridge_service(*args, **kwargs):
    return await _bridge_service_routes.get_workspace_agent_bridge_service(
        *args,
        **kwargs,
    )


async def start_workspace_agent_bridge_service(*args, **kwargs):
    return await _bridge_service_routes.start_workspace_agent_bridge_service(
        *args,
        **kwargs,
    )


async def restart_workspace_agent_bridge_service(*args, **kwargs):
    return await _bridge_service_routes.restart_workspace_agent_bridge_service(
        *args,
        **kwargs,
    )


async def list_workspace_agent_account_homes(*args, **kwargs):
    _sync_account_home_route_helpers()
    return await _account_home_routes.list_workspace_agent_account_homes(
        *args,
        **kwargs,
    )


async def create_workspace_agent_account_home(*args, **kwargs):
    _sync_account_home_route_helpers()
    return await _account_home_routes.create_workspace_agent_account_home(
        *args,
        **kwargs,
    )


async def delete_workspace_agent_account_home(*args, **kwargs):
    _sync_account_home_route_helpers()
    return await _account_home_routes.delete_workspace_agent_account_home(
        *args,
        **kwargs,
    )


async def probe_workspace_agent_account_home(*args, **kwargs):
    _sync_account_home_route_helpers()
    return await _account_home_routes.probe_workspace_agent_account_home(
        *args,
        **kwargs,
    )


async def login_workspace_agent(
    workspace_id: str,
    agent_id: str,
    payload: Optional[WorkspaceAgentAuthActionRequest] = None,
    workspace=None,
):
    _sync_auth_route_helpers()
    return await _auth_routes.login_workspace_agent(
        workspace_id=workspace_id,
        agent_id=agent_id,
        payload=payload,
        workspace=workspace,
    )


async def logout_workspace_agent(
    workspace_id: str,
    agent_id: str,
    payload: Optional[WorkspaceAgentAuthActionRequest] = None,
    workspace=None,
):
    _sync_auth_route_helpers()
    return await _auth_routes.logout_workspace_agent(
        workspace_id=workspace_id,
        agent_id=agent_id,
        payload=payload,
        workspace=workspace,
    )


__all__ = [
    "router",
    "WorkspaceAgentInfo",
    "WorkspaceAgentListResponse",
    "WorkspaceAgentAuthStatus",
    "WorkspaceAgentAuthActionResponse",
    "WorkspaceAgentAuthActionRequest",
    "CodexAccountHomeCreateRequest",
    "CodexAccountHomeTarget",
    "CodexAccountHomeTargetsResponse",
    "_account_home_env",
    "_default_codex_account_home_root",
    "_new_codex_account_home_path",
    "_normalize_codex_home_path",
    "_is_managed_codex_account_home",
    "_ensure_codex_account_home_dirs",
    "_has_codex_account_home_target",
    "_iso_value",
    "_list_codex_account_home_targets",
    "_resolve_codex_account_home_inputs",
    "_codex_identity_from_result",
    "_persist_codex_account_home_probe_result",
    "_persist_codex_account_home_login_metadata",
    "_validate_codex_account_home_login_identity",
    "_resolve_agent_availability",
    "_execute_agent_control",
    "_raise_agent_control_failure",
    "_classify_codex_status",
    "list_workspace_agents",
    "get_workspace_agent_auth_status",
    "get_workspace_agent_bridge_service",
    "start_workspace_agent_bridge_service",
    "restart_workspace_agent_bridge_service",
    "list_workspace_agent_account_homes",
    "create_workspace_agent_account_home",
    "delete_workspace_agent_account_home",
    "probe_workspace_agent_account_home",
    "login_workspace_agent",
    "logout_workspace_agent",
]
