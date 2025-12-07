"""
Playbook Flows API routes

Manages PlaybookFlow definitions for workspace projects.
"""

import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Path, Body, Depends
from pydantic import BaseModel

from backend.app.routes.workspace_dependencies import get_workspace, get_store
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.stores.playbook_flows_store import PlaybookFlowsStore
from backend.app.models.playbook_flow import PlaybookFlow, FlowNode, FlowEdge
from backend.app.models.workspace import Workspace

router = APIRouter(prefix="/api/v1/workspaces", tags=["workspace-flows"])
logger = logging.getLogger(__name__)


class CreateFlowRequest(BaseModel):
    """Request model for creating a playbook flow"""
    name: str
    description: Optional[str] = None
    flow_definition: dict


class UpdateFlowRequest(BaseModel):
    """Request model for updating a playbook flow"""
    name: Optional[str] = None
    description: Optional[str] = None
    flow_definition: Optional[dict] = None


@router.post("/{workspace_id}/flows")
async def create_flow(
    workspace_id: str = Path(..., description="Workspace ID"),
    request: CreateFlowRequest = Body(...),
    workspace: Workspace = Depends(get_workspace),
    store: MindscapeStore = Depends(get_store)
):
    """
    Create a new PlaybookFlow

    Args:
        workspace_id: Workspace ID
        request: Flow creation request

    Returns:
        Created PlaybookFlow
    """
    try:
        import uuid
        flows_store = PlaybookFlowsStore(db_path=store.db_path)

        flow_id = f"flow_{uuid.uuid4().hex[:12]}"
        flow = PlaybookFlow(
            id=flow_id,
            name=request.name,
            description=request.description,
            flow_definition=request.flow_definition
        )

        created_flow = flows_store.create_flow(flow)
        return created_flow.model_dump(mode='json')

    except Exception as e:
        logger.error(f"Failed to create flow: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{workspace_id}/flows")
async def list_flows(
    workspace_id: str = Path(..., description="Workspace ID"),
    limit: int = 100,
    offset: int = 0,
    workspace: Workspace = Depends(get_workspace),
    store: MindscapeStore = Depends(get_store)
):
    """
    List PlaybookFlows

    Args:
        workspace_id: Workspace ID
        limit: Maximum number of flows to return
        offset: Offset for pagination

    Returns:
        List of PlaybookFlows
    """
    try:
        flows_store = PlaybookFlowsStore(db_path=store.db_path)
        flows = flows_store.list_flows(limit=limit, offset=offset)
        return {"flows": [flow.model_dump(mode='json') for flow in flows]}

    except Exception as e:
        logger.error(f"Failed to list flows: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{workspace_id}/flows/{flow_id}")
async def get_flow(
    workspace_id: str = Path(..., description="Workspace ID"),
    flow_id: str = Path(..., description="Flow ID"),
    workspace: Workspace = Depends(get_workspace),
    store: MindscapeStore = Depends(get_store)
):
    """
    Get PlaybookFlow details

    Args:
        workspace_id: Workspace ID
        flow_id: Flow ID

    Returns:
        PlaybookFlow details
    """
    try:
        flows_store = PlaybookFlowsStore(db_path=store.db_path)
        flow = flows_store.get_flow(flow_id)
        if not flow:
            raise HTTPException(status_code=404, detail="Flow not found")
        return flow.model_dump(mode='json')

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get flow: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{workspace_id}/flows/{flow_id}")
async def update_flow(
    workspace_id: str = Path(..., description="Workspace ID"),
    flow_id: str = Path(..., description="Flow ID"),
    request: UpdateFlowRequest = Body(...),
    workspace: Workspace = Depends(get_workspace),
    store: MindscapeStore = Depends(get_store)
):
    """
    Update a PlaybookFlow

    Args:
        workspace_id: Workspace ID
        flow_id: Flow ID
        request: Flow update request

    Returns:
        Updated PlaybookFlow
    """
    try:
        flows_store = PlaybookFlowsStore(db_path=store.db_path)
        flow = flows_store.get_flow(flow_id)
        if not flow:
            raise HTTPException(status_code=404, detail="Flow not found")

        if request.name is not None:
            flow.name = request.name
        if request.description is not None:
            flow.description = request.description
        if request.flow_definition is not None:
            flow.flow_definition = request.flow_definition

        updated_flow = flows_store.update_flow(flow)
        return updated_flow.model_dump(mode='json')

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update flow: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{workspace_id}/flows/{flow_id}")
async def delete_flow(
    workspace_id: str = Path(..., description="Workspace ID"),
    flow_id: str = Path(..., description="Flow ID"),
    workspace: Workspace = Depends(get_workspace),
    store: MindscapeStore = Depends(get_store)
):
    """
    Delete a PlaybookFlow

    Args:
        workspace_id: Workspace ID
        flow_id: Flow ID

    Returns:
        Deletion result
    """
    try:
        flows_store = PlaybookFlowsStore(db_path=store.db_path)
        flow = flows_store.get_flow(flow_id)
        if not flow:
            raise HTTPException(status_code=404, detail="Flow not found")

        success = flows_store.delete_flow(flow_id)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to delete flow")

        return {"success": True, "flow_id": flow_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete flow: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{workspace_id}/flows/name/{flow_name}")
async def get_flow_by_name(
    workspace_id: str = Path(..., description="Workspace ID"),
    flow_name: str = Path(..., description="Flow name"),
    workspace: Workspace = Depends(get_workspace),
    store: MindscapeStore = Depends(get_store)
):
    """
    Get PlaybookFlow by name

    Args:
        workspace_id: Workspace ID
        flow_name: Flow name

    Returns:
        PlaybookFlow details
    """
    try:
        flows_store = PlaybookFlowsStore(db_path=store.db_path)
        flow = flows_store.get_flow_by_name(flow_name)
        if not flow:
            raise HTTPException(status_code=404, detail=f"Flow with name '{flow_name}' not found")
        return flow.model_dump(mode='json')

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get flow by name: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

