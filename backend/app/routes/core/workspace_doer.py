"""
Workspace Runtime Configuration API Routes

Unified API for configuring executor runtimes in any workspace.
All workspaces are treated equally - users explicitly choose which runtime to use.
Governance and sandbox isolation apply automatically.

Note: This was previously named "Doer Workspace" but the concept was simplified.
      Now every workspace can use external runtimes with automatic governance.
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
from backend.app.models.executor_spec import (
    ExecutorSpec,
    validate_executor_specs,
    resolve_executor_chain,
    promote_next_primary,
)

router = APIRouter(prefix="/api/v1/workspaces", tags=["workspace-agents"])
logger = logging.getLogger(__name__)


# ==================== Request/Response Models ====================


class ConfigureAgentRequest(BaseModel):
    """Request to configure executor runtime for a workspace"""

    executor_runtime: Optional[str] = Field(
        None,
        description="Executor runtime to use (e.g., 'openclaw', 'gemini_cli'). "
        "Set to null to use Mindscape LLM.",
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
    """Response containing workspace runtime configuration"""

    workspace_id: str
    executor_runtime: Optional[str]
    agent_status: Optional[dict] = None
    sandbox_config: Optional[DoerWorkspaceConfig] = None
    available_presets: List[str] = ["conservative", "balanced", "permissive"]
    agent_fallback_enabled: bool = True  # Deprecated, kept for backward compat
    fallback_model: Optional[str] = None


# ==================== API Endpoints ====================


@router.get("/{workspace_id}/agent-config")
async def get_agent_config(
    workspace_id: str = Path(..., description="Workspace ID"),
) -> AgentConfigResponse:
    """
    Get workspace runtime configuration.

    Returns the current runtime configuration including sandbox settings
    and runtime status. Works for any workspace.
    """
    store = MindscapeStore()

    try:
        workspace = await store.get_workspace(workspace_id)
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")

        # Get agent status if executor_runtime is set
        agent_status = None
        active_runtime = workspace.resolved_executor_runtime
        if active_runtime:
            try:
                from backend.app.routes.core.system_settings.governance_tools import (
                    get_agent_install_status,
                )

                status = get_agent_install_status(active_runtime)
                agent_status = {
                    "agent_id": active_runtime,
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
            executor_runtime=active_runtime,
            agent_status=agent_status,
            sandbox_config=sandbox_config,
            agent_fallback_enabled=getattr(workspace, "fallback_model", None)
            is not None,
            fallback_model=getattr(workspace, "fallback_model", None),
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
    Configure executor runtime for a workspace.

    Any workspace can use external runtimes. Governance and sandbox
    isolation apply automatically based on the configuration.
    """
    store = MindscapeStore()

    try:
        workspace = await store.get_workspace(workspace_id)
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")

        # Validate executor_runtime if provided
        if request.executor_runtime:
            registry = get_agent_registry()
            if request.executor_runtime not in registry.list_agents():
                raise HTTPException(
                    status_code=400,
                    detail=f"Unknown runtime: {request.executor_runtime}. "
                    f"Available: {', '.join(registry.list_agents())}",
                )

        # Get sandbox config from preset
        sandbox_config = None
        if request.executor_runtime:
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

        # Update workspace (fix: pass Workspace object, not dict)
        workspace.executor_runtime = request.executor_runtime
        # Dual-write: sync executor_specs
        _sync_executor_specs_from_runtime(workspace, request.executor_runtime)
        workspace.sandbox_config = (
            sandbox_config.model_dump() if sandbox_config else None
        )
        workspace.updated_at = _utc_now()
        await store.update_workspace(workspace)

        agent_desc = request.executor_runtime or "Mindscape LLM"
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

        if not workspace.executor_runtime:
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

        # Save (fix: pass Workspace object, not dict)
        workspace.sandbox_config = current_config.model_dump()
        workspace.updated_at = _utc_now()
        await store.update_workspace(workspace)

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

        # Clear config (fix: pass Workspace object, not dict)
        workspace.executor_runtime = None
        workspace.sandbox_config = None
        workspace.updated_at = _utc_now()
        await store.update_workspace(workspace)

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


@router.post("/{workspace_id}/executor-runtime")
async def set_executor_runtime(
    workspace_id: str = Path(..., description="Workspace ID"),
    agent_id: Optional[str] = Body(None, embed=True, description="Agent ID to set"),
) -> dict:
    """
    Set or clear the executor runtime for a workspace.

    If agent_id is null/None, clears the runtime (uses Mindscape LLM).
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
            "executor_runtime": agent_id,
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
        workspace.executor_runtime = update_data.get("executor_runtime")
        # Dual-write: sync executor_specs
        _sync_executor_specs_from_runtime(
            workspace, update_data.get("executor_runtime")
        )
        workspace.updated_at = update_data.get("updated_at")
        if "sandbox_config" in update_data:
            workspace.sandbox_config = update_data.get("sandbox_config")

        await store.update_workspace(workspace)

        action = f"set to {agent_id}" if agent_id else "cleared (using Mindscape LLM)"
        logger.info(f"Executor runtime {action} for workspace {workspace_id}")

        return {
            "success": True,
            "workspace_id": workspace_id,
            "executor_runtime": agent_id,
            "message": f"Executor runtime {action}",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to set executor runtime: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# Deprecated alias
@router.post("/{workspace_id}/preferred-agent", deprecated=True)
async def set_preferred_agent(
    workspace_id: str = Path(..., description="Workspace ID"),
    agent_id: Optional[str] = Body(None, embed=True, description="Agent ID to set"),
) -> dict:
    """Deprecated: use POST /{workspace_id}/executor-runtime instead."""
    logger.warning(
        f"Deprecated endpoint /preferred-agent called for workspace {workspace_id}. "
        "Use /executor-runtime instead."
    )
    return await set_executor_runtime(workspace_id=workspace_id, agent_id=agent_id)


# ==================== ExecutorSpec CRUD (P2) ====================


class AddExecutorSpecRequest(BaseModel):
    """Request to bind an executor to a workspace."""

    runtime_id: str = Field(
        ..., description="Registry key (snake_case, e.g. 'gemini_cli')"
    )
    display_name: str = Field("", description="Display name")
    is_primary: bool = Field(False, description="Set as primary executor")
    config: dict = Field(
        default_factory=dict, description="Workspace-specific config overrides"
    )
    priority: int = Field(0, description="Dispatch priority (lower = higher priority)")


@router.get("/{workspace_id}/executor-specs")
async def list_executor_specs(
    workspace_id: str = Path(..., description="Workspace ID"),
) -> dict:
    """List bound executor specs for a workspace."""
    store = MindscapeStore()
    workspace = await store.get_workspace(workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    specs = workspace.executor_specs or []
    return {
        "workspace_id": workspace_id,
        "executor_specs": specs,
        "resolved_executor_runtime": workspace.resolved_executor_runtime,
        "dispatch_chain": resolve_executor_chain(
            [ExecutorSpec.from_dict(s) for s in specs if isinstance(s, dict)]
        ),
    }


@router.post("/{workspace_id}/executor-specs")
async def add_executor_spec(
    workspace_id: str = Path(..., description="Workspace ID"),
    request: AddExecutorSpecRequest = Body(...),
) -> dict:
    """Bind a new executor to a workspace."""
    store = MindscapeStore()
    workspace = await store.get_workspace(workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    # Validate runtime exists in registry
    registry = get_agent_registry()
    if request.runtime_id not in registry.list_agents():
        raise HTTPException(
            status_code=400,
            detail=f"Unknown runtime: {request.runtime_id}. "
            f"Available: {', '.join(registry.list_agents())}",
        )

    specs = [
        ExecutorSpec.from_dict(s)
        for s in (workspace.executor_specs or [])
        if isinstance(s, dict)
    ]

    # Check duplicate
    if any(s.runtime_id == request.runtime_id for s in specs):
        raise HTTPException(
            status_code=409,
            detail=f"Runtime '{request.runtime_id}' already bound to this workspace",
        )

    # If setting as primary, demote existing primary
    if request.is_primary:
        for s in specs:
            s.is_primary = False

    # If first spec and not explicitly primary, auto-promote
    if not specs and not request.is_primary:
        request.is_primary = True

    new_spec = ExecutorSpec(
        runtime_id=request.runtime_id,
        display_name=request.display_name or request.runtime_id,
        is_primary=request.is_primary,
        config=request.config,
        priority=request.priority,
    )
    specs.append(new_spec)

    # Validate constraints
    errors = validate_executor_specs(specs)
    if errors:
        raise HTTPException(status_code=400, detail=f"Spec validation failed: {errors}")

    workspace.executor_specs = [s.to_dict() for s in specs]
    workspace.executor_runtime = workspace.resolved_executor_runtime
    workspace.updated_at = _utc_now()
    await store.update_workspace(workspace)

    return {
        "success": True,
        "workspace_id": workspace_id,
        "added": new_spec.to_dict(),
        "total_specs": len(specs),
    }


@router.delete("/{workspace_id}/executor-specs/{runtime_id}")
async def remove_executor_spec(
    workspace_id: str = Path(..., description="Workspace ID"),
    runtime_id: str = Path(..., description="Runtime ID to unbind"),
) -> dict:
    """Unbind an executor from a workspace. Auto-promotes next primary if needed."""
    store = MindscapeStore()
    workspace = await store.get_workspace(workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    specs = [
        ExecutorSpec.from_dict(s)
        for s in (workspace.executor_specs or [])
        if isinstance(s, dict)
    ]
    original_count = len(specs)
    specs = [s for s in specs if s.runtime_id != runtime_id]

    if len(specs) == original_count:
        raise HTTPException(status_code=404, detail=f"Runtime '{runtime_id}' not bound")

    # Auto-promote if primary was removed
    specs = promote_next_primary(specs)

    workspace.executor_specs = [s.to_dict() for s in specs]
    workspace.executor_runtime = workspace.resolved_executor_runtime
    workspace.updated_at = _utc_now()
    await store.update_workspace(workspace)

    return {
        "success": True,
        "workspace_id": workspace_id,
        "removed": runtime_id,
        "remaining_specs": len(specs),
    }


@router.patch("/{workspace_id}/executor-specs/{runtime_id}/primary")
async def set_primary_executor_spec(
    workspace_id: str = Path(..., description="Workspace ID"),
    runtime_id: str = Path(..., description="Runtime ID to set as primary"),
) -> dict:
    """Set a bound executor as the primary for this workspace."""
    store = MindscapeStore()
    workspace = await store.get_workspace(workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    specs = [
        ExecutorSpec.from_dict(s)
        for s in (workspace.executor_specs or [])
        if isinstance(s, dict)
    ]
    found = False
    for s in specs:
        if s.runtime_id == runtime_id:
            s.is_primary = True
            found = True
        else:
            s.is_primary = False

    if not found:
        raise HTTPException(status_code=404, detail=f"Runtime '{runtime_id}' not bound")

    workspace.executor_specs = [s.to_dict() for s in specs]
    workspace.executor_runtime = workspace.resolved_executor_runtime
    workspace.updated_at = _utc_now()
    await store.update_workspace(workspace)

    return {
        "success": True,
        "workspace_id": workspace_id,
        "primary": runtime_id,
    }


# ==================== Internal Helpers ====================


def _sync_executor_specs_from_runtime(workspace, runtime_id: Optional[str]):
    """Dual-write helper: sync executor_specs when legacy executor_runtime is set."""
    if runtime_id:
        specs = [
            ExecutorSpec.from_dict(s)
            for s in (workspace.executor_specs or [])
            if isinstance(s, dict)
        ]
        existing = [s for s in specs if s.runtime_id == runtime_id]
        if not existing:
            # Demote all existing primaries
            for s in specs:
                s.is_primary = False
            specs.append(
                ExecutorSpec(
                    runtime_id=runtime_id,
                    display_name=runtime_id,
                    is_primary=True,
                    priority=0,
                )
            )
        else:
            # Promote the matching spec to primary
            for s in specs:
                s.is_primary = s.runtime_id == runtime_id
        workspace.executor_specs = [s.to_dict() for s in specs]
    else:
        workspace.executor_specs = []
