import asyncio
from typing import List, Optional

from fastapi import APIRouter, Body, HTTPException, Path, Query

from ..models.graph import WorkspaceLensOverride
from ..models.lens_kernel import EffectiveLens
from ..models.preset_diff import PresetDiff
from ..services.lens.preset_diff_service import PresetDiffService
from .lens_dependencies import _session_store, get_graph_store, get_lens_resolver
from .lens_models import SetSessionOverrideRequest, SetWorkspaceOverrideRequest

router = APIRouter()


@router.get("/profiles/{preset_id}/diff", response_model=PresetDiff)
async def get_preset_diff(
    preset_id: str = Path(..., description="要比较的 Preset ID"),
    compare_with: str = Query(..., description="比较基准 Preset ID"),
):
    """
    获取两个 Preset 之间的差异

    比较 preset_id 和 compare_with 两个 Preset 的节点状态差异
    """
    graph_store = get_graph_store()
    diff_service = PresetDiffService(graph_store)

    try:
        diff = await asyncio.to_thread(diff_service.compare, preset_id, compare_with)
        return diff
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/effective-lens", response_model=EffectiveLens)
async def get_effective_lens(
    workspace_id: Optional[str] = Query(None, description="Workspace ID"),
    session_id: Optional[str] = Query(None, description="Session ID"),
    profile_id: str = Query(..., description="Profile ID"),
) -> EffectiveLens:
    """Get effective lens with three-layer stacking"""
    resolver = get_lens_resolver()
    try:
        effective_lens = await asyncio.to_thread(
            resolver.resolve,
            profile_id=profile_id,
            workspace_id=workspace_id,
            session_id=session_id,
        )
        return effective_lens
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get(
    "/workspaces/{workspace_id}/lens-overrides",
    response_model=List[WorkspaceLensOverride],
)
async def get_workspace_overrides(
    workspace_id: str = Path(..., description="Workspace ID")
) -> List[WorkspaceLensOverride]:
    """Get all workspace lens overrides"""
    store = get_graph_store()
    overrides = await asyncio.to_thread(store.get_workspace_overrides, workspace_id)
    return overrides


@router.put(
    "/workspaces/{workspace_id}/lens-overrides/{node_id}",
    response_model=WorkspaceLensOverride,
)
async def set_workspace_override(
    workspace_id: str = Path(..., description="Workspace ID"),
    node_id: str = Path(..., description="Node ID"),
    request: SetWorkspaceOverrideRequest = Body(...),
) -> WorkspaceLensOverride:
    """Set workspace lens override for a node"""
    store = get_graph_store()
    override = await asyncio.to_thread(
        store.set_workspace_override, workspace_id, node_id, request.state
    )
    return override


@router.delete("/workspaces/{workspace_id}/lens-overrides/{node_id}", status_code=204)
async def remove_workspace_override(
    workspace_id: str = Path(..., description="Workspace ID"),
    node_id: str = Path(..., description="Node ID"),
):
    """Remove workspace lens override for a node"""
    store = get_graph_store()
    await asyncio.to_thread(store.remove_workspace_override, workspace_id, node_id)


@router.get("/session/{session_id}/overrides")
async def get_session_overrides(
    session_id: str = Path(..., description="Session ID")
) -> dict:
    """Get all session overrides"""
    overrides = _session_store.get(session_id)
    return {"overrides": overrides or {}}


@router.put("/session/{session_id}/overrides/{node_id}")
async def set_session_override(
    session_id: str = Path(..., description="Session ID"),
    node_id: str = Path(..., description="Node ID"),
    request: SetSessionOverrideRequest = Body(...),
) -> dict:
    """Set session override for a node"""
    _session_store.set(session_id, node_id, request.state)
    return {"node_id": node_id, "state": request.state}


@router.delete("/session/{session_id}/overrides", status_code=204)
async def clear_session_overrides(
    session_id: str = Path(..., description="Session ID")
):
    """Clear all session overrides"""
    _session_store.clear(session_id)
