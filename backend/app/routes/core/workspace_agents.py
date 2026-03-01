"""
Workspace-scoped Agent Availability API.

Returns per-workspace agent availability instead of global status.
This prevents the UI from showing "Connected (WS)" when the connection
belongs to a different workspace.
"""

import logging
import os
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi import Path as PathParam
from pydantic import BaseModel

from backend.app.services.external_agents.core.registry import get_runtime_registry
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

        if not registry._adapters:
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
