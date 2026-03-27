"""
Workspace-scoped Agent Availability API.

Returns per-workspace agent availability instead of global status.
This prevents the UI from showing "Connected (WS)" when the connection
belongs to a different workspace.
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi import Path as PathParam
from pydantic import BaseModel

from backend.app.services.external_agents.core.registry import get_runtime_registry
from backend.app.services.external_agents.core.base_adapter import RuntimeExecRequest
from backend.app.routes.workspace_dependencies import get_workspace
from backend.app.models.workspace import Workspace

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/workspaces/{workspace_id}/agents",
    tags=["workspace-agents"],
)


class WorkspaceAgentInfo(BaseModel):
    """Agent info scoped to a specific workspace."""

    id: str
    name: str
    description: str
    status: str  # 'available', 'unavailable', 'error'
    version: str
    risk_level: str
    cli_command: Optional[str] = None
    transport: Optional[str] = None
    reason: Optional[str] = None


class WorkspaceAgentListResponse(BaseModel):
    """Response for workspace-scoped agent listing."""

    agents: List[WorkspaceAgentInfo]
    total: int
    workspace_id: str
    bridge_script_path: Optional[str] = None


class WorkspaceAgentAuthStatus(BaseModel):
    agent_id: str
    workspace_id: str
    available: bool
    transport: Optional[str] = None
    reason: Optional[str] = None
    mode: str
    status: str
    note: Optional[str] = None
    output: Optional[str] = None
    error: Optional[str] = None
    login_supported: bool = False
    logout_supported: bool = False
    manual_command: Optional[str] = None


class WorkspaceAgentAuthActionResponse(BaseModel):
    agent_id: str
    workspace_id: str
    action: str
    success: bool
    output: str = ""
    error: Optional[str] = None
    note: Optional[str] = None


async def _resolve_agent_availability(
    workspace_id: str,
    agent_id: str,
) -> tuple[Any, Dict[str, Any]]:
    registry = get_runtime_registry()
    registry.discover_agents()

    adapter = registry.get_adapter(agent_id)
    if not adapter:
        raise HTTPException(status_code=404, detail=f"Unknown agent: {agent_id}")

    transport = None
    reason = None
    if hasattr(adapter, "get_availability_detail"):
        detail = adapter.get_availability_detail(workspace_id=workspace_id)
        available = bool(detail.get("available"))
        transport = detail.get("transport")
        reason = detail.get("reason")
    else:
        available = bool(await adapter.is_available(workspace_id=workspace_id))
        detail = {"available": available}

    detail.update({"transport": transport, "reason": reason})
    return adapter, detail


async def _execute_agent_control(
    workspace: Workspace,
    agent_id: str,
    control_action: str,
):
    registry = get_runtime_registry()
    registry.discover_agents()
    adapter = registry.get_adapter(agent_id)
    if not adapter:
        raise HTTPException(status_code=404, detail=f"Unknown agent: {agent_id}")

    sandbox_path = (
        getattr(workspace, "storage_base_path", None)
        or getattr(workspace, "workspace_path", None)
        or "/tmp"
    )
    request = RuntimeExecRequest(
        task=f"__mindscape_cli_control__:{control_action}",
        sandbox_path=str(sandbox_path),
        workspace_id=workspace.id,
        auth_workspace_id=workspace.id,
        source_workspace_id=workspace.id,
        max_duration_seconds=45,
        agent_config={
            "control_action": control_action,
            "thread_id": "runtime-auth-settings",
            "conversation_context": "Runtime auth control command",
        },
    )
    return await adapter.execute(request)


def _classify_codex_status(success: bool, output: str, error: Optional[str]) -> str:
    if success:
        return "authenticated"
    lower = f"{output} {error or ''}".lower()
    auth_markers = (
        "not logged",
        "login",
        "authenticate",
        "auth",
        "credential",
    )
    if any(marker in lower for marker in auth_markers):
        return "not_authenticated"
    return "error"


@router.get("", response_model=WorkspaceAgentListResponse)
async def list_workspace_agents(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    workspace: Workspace = Depends(get_workspace),
):
    """
    List agents with per-workspace availability.

    Unlike /api/v1/agents (global), this checks whether each agent
    has an active connection for the specified workspace.
    """
    try:
        registry = get_runtime_registry()
        registry.discover_agents()

        agents = []
        for agent_name, manifest in registry.get_all_manifests().items():
            adapter = registry.get_adapter(agent_name)

            transport = None
            reason = None
            if adapter and hasattr(adapter, "get_availability_detail"):
                detail = adapter.get_availability_detail(
                    workspace_id=workspace_id,
                )
                is_available = detail["available"]
                transport = detail.get("transport")
                reason = detail.get("reason")
            elif adapter:
                is_available = await adapter.is_available(
                    workspace_id=workspace_id,
                )
            else:
                is_available = False

            agents.append(
                WorkspaceAgentInfo(
                    id=agent_name,
                    name=manifest.name,
                    description=manifest.description,
                    status="available" if is_available else "unavailable",
                    version=manifest.version,
                    risk_level=manifest.risk_level,
                    cli_command=manifest.cli_command,
                    transport=transport,
                    reason=reason,
                )
            )

        host_root = os.environ.get("HOST_PROJECT_PATH")
        if host_root:
            bridge_path = Path(host_root) / "scripts" / "start_cli_bridge.sh"
            script_path = str(bridge_path)
        else:
            project_root = Path(__file__).resolve().parents[4]
            bridge_path = project_root / "scripts" / "start_cli_bridge.sh"
            script_path = str(bridge_path) if bridge_path.exists() else None

        return WorkspaceAgentListResponse(
            agents=agents,
            total=len(agents),
            workspace_id=workspace_id,
            bridge_script_path=script_path,
        )

    except Exception as e:
        logger.error(
            f"[WorkspaceAgentsAPI] Failed to list agents for " f"{workspace_id}: {e}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{agent_id}/auth-status", response_model=WorkspaceAgentAuthStatus)
async def get_workspace_agent_auth_status(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    agent_id: str = PathParam(..., description="Agent ID"),
    workspace: Workspace = Depends(get_workspace),
):
    _, detail = await _resolve_agent_availability(workspace_id, agent_id)
    available = bool(detail.get("available"))
    transport = detail.get("transport")
    reason = detail.get("reason")

    if agent_id == "codex_cli":
        if not available:
            return WorkspaceAgentAuthStatus(
                agent_id=agent_id,
                workspace_id=workspace_id,
                available=False,
                transport=transport,
                reason=reason,
                mode="host_session",
                status="unavailable",
                note="Codex host session can only be inspected when the codex_cli surface is connected for this workspace.",
                login_supported=True,
                logout_supported=True,
                manual_command="codex login",
            )

        result = await _execute_agent_control(workspace, agent_id, "codex_login_status")
        output = result.output or ""
        status = _classify_codex_status(result.success, output, result.error)
        return WorkspaceAgentAuthStatus(
            agent_id=agent_id,
            workspace_id=workspace_id,
            available=True,
            transport=transport,
            reason=reason,
            mode="host_session",
            status=status,
            output=output or None,
            error=result.error,
            note="This checks the real host Codex CLI session, not the API-key setting.",
            login_supported=True,
            logout_supported=True,
            manual_command="codex login",
        )

    if agent_id == "claude_code_cli":
        note = (
            "Claude Code host-token sessions are managed directly on the host with "
            "`claude setup-token`. The backend cannot inspect the token state "
            "without a dedicated CLI status command."
        )
        return WorkspaceAgentAuthStatus(
            agent_id=agent_id,
            workspace_id=workspace_id,
            available=available,
            transport=transport,
            reason=reason,
            mode="host_token",
            status="manual_required" if available else "unavailable",
            note=note,
            login_supported=False,
            logout_supported=False,
            manual_command="claude setup-token",
        )

    raise HTTPException(status_code=400, detail=f"Auth status is not implemented for {agent_id}")


@router.post("/{agent_id}/login", response_model=WorkspaceAgentAuthActionResponse)
async def login_workspace_agent(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    agent_id: str = PathParam(..., description="Agent ID"),
    workspace: Workspace = Depends(get_workspace),
):
    _, detail = await _resolve_agent_availability(workspace_id, agent_id)
    if not detail.get("available"):
        raise HTTPException(
            status_code=409,
            detail=f"{agent_id} is not connected for workspace {workspace_id}",
        )

    if agent_id != "codex_cli":
        raise HTTPException(
            status_code=400,
            detail=f"Interactive login is not implemented for {agent_id}",
        )

    result = await _execute_agent_control(workspace, agent_id, "codex_login")
    return WorkspaceAgentAuthActionResponse(
        agent_id=agent_id,
        workspace_id=workspace_id,
        action="login",
        success=result.success,
        output=result.output or "",
        error=result.error,
        note=(
            "If Codex opens a browser or device-code flow on the host, finish it there "
            "and then refresh auth status."
        ),
    )


@router.post("/{agent_id}/logout", response_model=WorkspaceAgentAuthActionResponse)
async def logout_workspace_agent(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    agent_id: str = PathParam(..., description="Agent ID"),
    workspace: Workspace = Depends(get_workspace),
):
    _, detail = await _resolve_agent_availability(workspace_id, agent_id)
    if not detail.get("available"):
        raise HTTPException(
            status_code=409,
            detail=f"{agent_id} is not connected for workspace {workspace_id}",
        )

    if agent_id != "codex_cli":
        raise HTTPException(
            status_code=400,
            detail=f"Logout is not implemented for {agent_id}",
        )

    result = await _execute_agent_control(workspace, agent_id, "codex_logout")
    return WorkspaceAgentAuthActionResponse(
        agent_id=agent_id,
        workspace_id=workspace_id,
        action="logout",
        success=result.success,
        output=result.output or "",
        error=result.error,
        note="Codex host session logout was executed on the connected runtime surface.",
    )
