"""Workspace external agent inventory API routes."""

import logging
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Path, Query
from pydantic import BaseModel, Field

from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.external_agents.core.registry import get_runtime_registry

router = APIRouter(prefix="/api/v1/workspaces", tags=["workspace-agents"])
logger = logging.getLogger(__name__)


# ==================== Request/Response Models ====================


class AvailableAgentInfo(BaseModel):
    """Information about an available external agent"""

    agent_id: str
    name: str
    description: str
    available: bool
    version: Optional[str] = None
    risk_level: str = "high"
    requires_sandbox: bool = True


@router.get("/{workspace_id}/available-agents")
async def list_available_agents(
    workspace_id: str = Path(..., description="Workspace ID"),
    include_unavailable: bool = Query(False, description="Include unavailable agents"),
) -> List[AvailableAgentInfo]:
    """
    List available external agents for this workspace.

    Returns information about each agent including availability status.
    All workspaces have access to the same agents.
    """
    store = MindscapeStore()

    try:
        workspace = await store.get_workspace(workspace_id)
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")

        registry = get_runtime_registry()
        agents = []

        for agent_name in registry.list_agents():
            manifest = registry.get_manifest(agent_name)
            adapter = registry.get_adapter(agent_name)

            # Check availability
            available = False
            version = None
            if adapter:
                try:
                    available = await adapter.is_available()
                    version = await adapter.get_version() if available else None
                except Exception:
                    pass

            if not include_unavailable and not available:
                continue

            agents.append(
                AvailableAgentInfo(
                    agent_id=agent_name,
                    name=manifest.name if manifest else agent_name,
                    description=manifest.description if manifest else "",
                    available=available,
                    version=version,
                    risk_level=manifest.risk_level if manifest else "high",
                    requires_sandbox=manifest.requires_sandbox if manifest else True,
                )
            )

        return agents

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list agents: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
