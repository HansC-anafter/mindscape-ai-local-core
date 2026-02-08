"""
Projects API routes for Workspace-based projects - Flow Execution
"""

import logging
from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Path, Body, Depends
from pydantic import BaseModel

from backend.app.routes.workspace_dependencies import get_workspace, get_store
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.project.project_manager import ProjectManager
from backend.app.services.project.flow_executor import FlowExecutor, FlowExecutionError
from backend.app.models.workspace import Workspace
from backend.app.services.project.artifact_registry_service import (
    ArtifactRegistryService,
)

router = APIRouter()
logger = logging.getLogger(__name__)


class ExecuteFlowRequest(BaseModel):
    """Request model for executing a project flow"""

    resume_from: Optional[str] = None
    preserve_artifacts: bool = True
    max_retries: int = 3


@router.post(
    "/{workspace_id}/projects/{project_id}/execute-flow", response_model=Dict[str, Any]
)
async def execute_project_flow(
    workspace_id: str = Path(..., description="Workspace ID"),
    project_id: str = Path(..., description="Project ID"),
    request: ExecuteFlowRequest = Body(...),
    workspace: Workspace = Depends(get_workspace),
    store: MindscapeStore = Depends(get_store),
):
    """
    Execute PlaybookFlow for a project

    Starts or resumes flow execution for the specified project.
    Supports partial retry from a specific node and artifact preservation.

    Args:
        workspace_id: Workspace ID
        project_id: Project ID
        request: Flow execution request with optional resume_from, preserve_artifacts, max_retries

    Returns:
        Flow execution result with node outcomes
    """
    try:
        project_manager = ProjectManager(store)
        project = await project_manager.get_project(
            project_id, workspace_id=workspace_id
        )
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        from backend.app.routes.workspace_dependencies import (
            get_identity_port_or_default,
        )

        identity_port = get_identity_port_or_default()
        context = await identity_port.get_current_context(workspace_id=workspace_id)
        profile_id = context.actor_id

        flow_executor = FlowExecutor(store)
        result = await flow_executor.execute_flow(
            project_id=project_id,
            workspace_id=workspace_id,
            profile_id=profile_id,
            resume_from=request.resume_from,
            preserve_artifacts=request.preserve_artifacts,
            max_retries=request.max_retries,
        )

        return {"status": "executing", "execution_result": result}

    except FlowExecutionError as e:
        logger.error(f"Flow execution error: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError as e:
        logger.error(f"Permission error executing flow: {e}")
        raise HTTPException(status_code=403, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to execute flow: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/{workspace_id}/projects/{project_id}/flow-status", response_model=Dict[str, Any]
)
async def get_flow_status(
    workspace_id: str = Path(..., description="Workspace ID"),
    project_id: str = Path(..., description="Project ID"),
    workspace: Workspace = Depends(get_workspace),
    store: MindscapeStore = Depends(get_store),
):
    """
    Get flow execution status for a project

    Returns current flow execution status including completed nodes,
    failed nodes, and checkpoint information.

    Args:
        workspace_id: Workspace ID
        project_id: Project ID

    Returns:
        Flow execution status
    """
    try:
        project_manager = ProjectManager(store)
        project = await project_manager.get_project(
            project_id, workspace_id=workspace_id
        )
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        artifact_registry = ArtifactRegistryService(store)
        artifacts = await artifact_registry.list_artifacts(project_id=project_id)

        checkpoint = project.metadata.get("last_checkpoint")

        return {
            "project_id": project_id,
            "flow_id": project.flow_id,
            "status": "ready",
            "artifacts_count": len(artifacts),
            "checkpoint": checkpoint,
            "artifacts": [
                {
                    "artifact_id": a.artifact_id,
                    "type": a.type,
                    "created_by": a.created_by,
                    "created_at": a.created_at.isoformat(),
                }
                for a in artifacts[:10]
            ],
        }

    except PermissionError as e:
        logger.error(f"Permission error getting flow status: {e}")
        raise HTTPException(status_code=403, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get flow status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
