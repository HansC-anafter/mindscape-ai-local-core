import logging
import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi import Path as PathParam

from backend.app.models.workspace import Workspace
from backend.app.routes.workspace_dependencies import get_workspace
from backend.app.services.external_agents.core.registry import get_runtime_registry

from .runtime_control import (
    _classify_codex_status,
    _execute_agent_control,
    _resolve_agent_availability,
)
from .schemas import (
    WorkspaceAgentAuthStatus,
    WorkspaceAgentInfo,
    WorkspaceAgentListResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()


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
