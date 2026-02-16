"""
Agent Registry API Routes

Provides endpoints for fetching available external agents.
"""

import logging
import os
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.app.services.external_agents.core.registry import get_agent_registry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])


class AgentInfo(BaseModel):
    """Agent information for frontend display."""

    id: str
    name: str
    description: str
    status: str  # 'available', 'unavailable', 'error'
    version: str
    risk_level: str
    cli_command: Optional[str] = None


class AgentListResponse(BaseModel):
    """Response for agent listing."""

    agents: List[AgentInfo]
    total: int
    bridge_script_path: Optional[str] = None


@router.get("", response_model=AgentListResponse)
async def list_agents():
    """
    List all registered external agents.

    Returns agent metadata from AGENT.md manifests and availability status.
    """
    try:
        registry = get_agent_registry()

        # Ensure discovery has run
        if not registry._adapters:
            registry.discover_agents()

        # Get availability for all agents
        availability = await registry.check_availability()

        agents = []
        for agent_name, manifest in registry.get_all_manifests().items():
            is_available = availability.get(agent_name, False)

            agents.append(
                AgentInfo(
                    id=agent_name,
                    name=manifest.name,
                    description=manifest.description,
                    status="available" if is_available else "unavailable",
                    version=manifest.version,
                    risk_level=manifest.risk_level,
                    cli_command=manifest.cli_command,
                )
            )

        # Resolve bridge script path on the host filesystem
        # HOST_PROJECT_PATH is set in docker-compose.yml to the host's project root
        host_root = os.environ.get("HOST_PROJECT_PATH")
        if host_root:
            bridge_path = Path(host_root) / "scripts" / "start_cli_bridge.sh"
            script_path = str(bridge_path)
        else:
            # Fallback for non-Docker environments
            project_root = Path(__file__).resolve().parents[4]
            bridge_path = project_root / "scripts" / "start_cli_bridge.sh"
            script_path = str(bridge_path) if bridge_path.exists() else None

        logger.info(f"[AgentsAPI] Listed {len(agents)} agents")
        return AgentListResponse(
            agents=agents,
            total=len(agents),
            bridge_script_path=script_path,
        )

    except Exception as e:
        logger.error(f"[AgentsAPI] Failed to list agents: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{agent_id}")
async def get_agent(agent_id: str):
    """
    Get details for a specific agent.
    """
    try:
        registry = get_agent_registry()
        manifest = registry.get_manifest(agent_id)

        if not manifest:
            raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")

        adapter = registry.get_adapter(agent_id)
        is_available = await adapter.is_available() if adapter else False

        return AgentInfo(
            id=agent_id,
            name=manifest.name,
            description=manifest.description,
            status="available" if is_available else "unavailable",
            version=manifest.version,
            risk_level=manifest.risk_level,
            cli_command=manifest.cli_command,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[AgentsAPI] Failed to get agent {agent_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
