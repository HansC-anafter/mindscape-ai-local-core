"""
Workspace Agent Configuration API Routes

Unified API for configuring external agents in any workspace.
All workspaces are treated equally - users explicitly choose which agent to use.
Governance and sandbox isolation apply automatically.

Note: This was previously named "Doer Workspace" but the concept was simplified.
      Now every workspace can use external agents with automatic governance.
"""

import logging
from typing import Optional, List
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


from fastapi import APIRouter, HTTPException, Path, Body, Query
from pydantic import BaseModel, Field

from backend.app.models.doer_workspace_config import (
    DoerWorkspaceConfig,
    DoerWorkspaceConfigUpdate,
    DOER_CONFIG_PRESETS,
    get_default_doer_config,
)
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.external_agents.core.registry import get_agent_registry

router = APIRouter(prefix="/api/v1/workspaces", tags=["workspace-agents"])
logger = logging.getLogger(__name__)


# ==================== Request/Response Models ====================


class ConfigureAgentRequest(BaseModel):
    """Request to configure external agent for a workspace"""

    preferred_agent: Optional[str] = Field(
        None,
        description="External agent to use (e.g., 'openclaw', 'aider'). Set to null to use Mindscape LLM.",
    )
    config_preset: Optional[str] = Field(
        "balanced",
        description="Sandbox configuration preset: conservative | balanced | permissive",
    )
    custom_config: Optional[DoerWorkspaceConfigUpdate] = Field(
        None, description="Custom sandbox configuration overrides"
    )


class AvailableAgentInfo(BaseModel):
    """Information about an available external agent"""

    agent_id: str
    name: str
    description: str
    available: bool
    version: Optional[str] = None
    risk_level: str = "high"
    requires_sandbox: bool = True


class AgentConfigResponse(BaseModel):
    """Response containing workspace agent configuration"""

    workspace_id: str
    preferred_agent: Optional[str]
    agent_status: Optional[dict] = None
    sandbox_config: Optional[DoerWorkspaceConfig] = None
    available_presets: List[str] = ["conservative", "balanced", "permissive"]
    agent_fallback_enabled: bool = True


# ==================== API Endpoints ====================


@router.get("/{workspace_id}/agent-config")
async def get_agent_config(
    workspace_id: str = Path(..., description="Workspace ID"),
) -> AgentConfigResponse:
    """
    Get workspace agent configuration.

    Returns the current agent configuration including sandbox settings
    and agent status. Works for any workspace.
    """
    store = MindscapeStore()

    try:
        workspace = await store.get_workspace(workspace_id)
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")

        # Get agent status if preferred_agent is set
        agent_status = None
        if workspace.preferred_agent:
            try:
                from backend.app.routes.core.system_settings.governance_tools import (
                    get_agent_install_status,
                )

                status = get_agent_install_status(workspace.preferred_agent)
                agent_status = {
                    "agent_id": workspace.preferred_agent,
                    "status": status.status,
                    "cli_available": status.cli_available,
                    "version": status.version,
                }
            except Exception as e:
                logger.warning(f"Failed to get agent status: {e}")

        # Parse sandbox_config
        sandbox_config = None
        if workspace.sandbox_config:
            try:
                sandbox_config = DoerWorkspaceConfig(**workspace.sandbox_config)
            except Exception as e:
                logger.warning(f"Failed to parse sandbox_config: {e}")

        return AgentConfigResponse(
            workspace_id=workspace_id,
            preferred_agent=workspace.preferred_agent,
            agent_status=agent_status,
            sandbox_config=sandbox_config,
            agent_fallback_enabled=getattr(workspace, "agent_fallback_enabled", True),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get agent config: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{workspace_id}/agent-config")
async def configure_agent(
    workspace_id: str = Path(..., description="Workspace ID"),
    request: ConfigureAgentRequest = Body(...),
) -> AgentConfigResponse:
    """
    Configure external agent for a workspace.

    Any workspace can use external agents. Governance and sandbox
    isolation apply automatically based on the configuration.
    """
    store = MindscapeStore()

    try:
        workspace = await store.get_workspace(workspace_id)
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")

        # Validate preferred_agent if provided
        if request.preferred_agent:
            registry = get_agent_registry()
            if request.preferred_agent not in registry.list_agents():
                raise HTTPException(
                    status_code=400,
                    detail=f"Unknown agent: {request.preferred_agent}. "
                    f"Available: {', '.join(registry.list_agents())}",
                )

        # Get sandbox config from preset
        sandbox_config = None
        if request.preferred_agent:
            preset_name = request.config_preset or "balanced"
            if preset_name not in DOER_CONFIG_PRESETS:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unknown preset: {preset_name}. "
                    f"Available: {', '.join(DOER_CONFIG_PRESETS.keys())}",
                )

            sandbox_config = DOER_CONFIG_PRESETS[preset_name].model_copy()

            # Apply custom overrides
            if request.custom_config:
                for field, value in request.custom_config.model_dump(
                    exclude_none=True
                ).items():
                    setattr(sandbox_config, field, value)

            sandbox_config.updated_at = _utc_now()

        # Update workspace
        await store.update_workspace(
            workspace_id,
            {
                "preferred_agent": request.preferred_agent,
                "sandbox_config": (
                    sandbox_config.model_dump() if sandbox_config else None
                ),
                "updated_at": _utc_now(),
            },
        )

        agent_desc = request.preferred_agent or "Mindscape LLM"
        logger.info(f"Workspace {workspace_id} configured to use {agent_desc}")

        return await get_agent_config(workspace_id)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to configure agent: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{workspace_id}/agent-config")
async def update_agent_config(
    workspace_id: str = Path(..., description="Workspace ID"),
    request: DoerWorkspaceConfigUpdate = Body(...),
) -> AgentConfigResponse:
    """
    Update sandbox configuration.

    Only updates the specified fields, preserving existing values.
    """
    store = MindscapeStore()

    try:
        workspace = await store.get_workspace(workspace_id)
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")

        if not workspace.preferred_agent:
            raise HTTPException(
                status_code=400,
                detail="No agent configured. Use POST /agent-config first.",
            )

        # Get current config
        current_config = (
            DoerWorkspaceConfig(**workspace.sandbox_config)
            if workspace.sandbox_config
            else get_default_doer_config()
        )

        # Apply updates
        for field, value in request.model_dump(exclude_none=True).items():
            setattr(current_config, field, value)

        current_config.updated_at = _utc_now()

        # Save
        await store.update_workspace(
            workspace_id,
            {
                "sandbox_config": current_config.model_dump(),
                "updated_at": _utc_now(),
            },
        )

        logger.info(f"Updated agent config for workspace {workspace_id}")

        return await get_agent_config(workspace_id)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update agent config: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{workspace_id}/agent-config")
async def clear_agent_config(
    workspace_id: str = Path(..., description="Workspace ID"),
) -> dict:
    """
    Clear external agent configuration.

    Removes external agent and sandbox settings, reverting to Mindscape LLM.
    """
    store = MindscapeStore()

    try:
        workspace = await store.get_workspace(workspace_id)
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")

        await store.update_workspace(
            workspace_id,
            {
                "preferred_agent": None,
                "sandbox_config": None,
                "updated_at": _utc_now(),
            },
        )

        logger.info(f"Cleared agent config for workspace {workspace_id}")

        return {
            "success": True,
            "workspace_id": workspace_id,
            "message": "Agent configuration cleared, using Mindscape LLM",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to clear agent config: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


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

        registry = get_agent_registry()
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


@router.post("/{workspace_id}/preferred-agent")
async def set_preferred_agent(
    workspace_id: str = Path(..., description="Workspace ID"),
    agent_id: Optional[str] = Body(None, embed=True, description="Agent ID to set"),
) -> dict:
    """
    Set or clear the preferred agent for a workspace.

    If agent_id is null/None, clears the preferred agent (uses Mindscape LLM).
    Sandbox configuration will be set to 'balanced' preset automatically.
    """
    store = MindscapeStore()

    try:
        workspace = await store.get_workspace(workspace_id)
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")

        # Validate agent if provided
        if agent_id:
            registry = get_agent_registry()
            if agent_id not in registry.list_agents():
                raise HTTPException(
                    status_code=400,
                    detail=f"Unknown agent: {agent_id}. "
                    f"Available: {', '.join(registry.list_agents())}",
                )

        # Prepare update
        update_data = {
            "preferred_agent": agent_id,
            "updated_at": _utc_now(),
        }

        # Auto-set sandbox config when selecting an agent
        if agent_id and not workspace.sandbox_config:
            default_config = get_default_doer_config()
            update_data["sandbox_config"] = default_config.model_dump(mode="json")

        # Clear sandbox config when clearing agent
        if not agent_id:
            update_data["sandbox_config"] = None

        # Apply updates to workspace object
        workspace.preferred_agent = update_data.get("preferred_agent")
        workspace.updated_at = update_data.get("updated_at")
        if "sandbox_config" in update_data:
            workspace.sandbox_config = update_data.get("sandbox_config")

        await store.update_workspace(workspace)

        action = f"set to {agent_id}" if agent_id else "cleared (using Mindscape LLM)"
        logger.info(f"Preferred agent {action} for workspace {workspace_id}")

        return {
            "success": True,
            "workspace_id": workspace_id,
            "preferred_agent": agent_id,
            "message": f"Preferred agent {action}",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to set preferred agent: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
