"""
Projects API routes for Workspace-based projects
"""

import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Path, Body, Depends
from pydantic import BaseModel

from backend.app.routes.workspace_dependencies import get_workspace, get_store
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.project.project_manager import ProjectManager
from backend.app.models.workspace import Workspace
from backend.app.models.project import Project, ProjectSuggestion

router = APIRouter(prefix="/api/v1/workspaces", tags=["workspace-projects"])
logger = logging.getLogger(__name__)


class CreateProjectRequest(BaseModel):
    """Request model for creating a project"""
    suggestion: Optional[ProjectSuggestion] = None
    project_type: Optional[str] = None
    title: Optional[str] = None
    flow_id: Optional[str] = None
    initiator_user_id: Optional[str] = None
    human_owner_user_id: Optional[str] = None
    ai_pm_id: Optional[str] = None


@router.get("/{workspace_id}/projects")
async def list_projects(
    workspace_id: str = Path(..., description="Workspace ID"),
    state: Optional[str] = None,
    limit: int = 100,
    workspace: Workspace = Depends(get_workspace),
    store: MindscapeStore = Depends(get_store)
):
    """
    List projects in workspace
    
    Args:
        workspace_id: Workspace ID
        state: Optional state filter (open, closed, archived)
        limit: Maximum number of projects to return
        
    Returns:
        List of projects
    """
    try:
        project_manager = ProjectManager(store)
        projects = await project_manager.list_projects(
            workspace_id=workspace_id,
            state=state,
            limit=limit
        )
        return {"projects": [p.model_dump(mode='json') for p in projects]}
    except Exception as e:
        logger.error(f"Failed to list projects: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{workspace_id}/projects/{project_id}")
async def get_project(
    workspace_id: str = Path(..., description="Workspace ID"),
    project_id: str = Path(..., description="Project ID"),
    workspace: Workspace = Depends(get_workspace),
    store: MindscapeStore = Depends(get_store)
):
    """
    Get project details
    
    Args:
        workspace_id: Workspace ID
        project_id: Project ID
        
    Returns:
        Project details
    """
    try:
        project_manager = ProjectManager(store)
        project = await project_manager.get_project(project_id, workspace_id=workspace_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        return project.model_dump(mode='json')
    except PermissionError as e:
        logger.error(f"Permission error getting project: {e}")
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get project: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{workspace_id}/projects")
async def create_project(
    workspace_id: str = Path(..., description="Workspace ID"),
    request: CreateProjectRequest = Body(...),
    workspace: Workspace = Depends(get_workspace),
    store: MindscapeStore = Depends(get_store)
):
    """
    Create new project
    
    Args:
        workspace_id: Workspace ID
        request: Project creation request (can use suggestion or direct fields)
        
    Returns:
        Created project
    """
    try:
        project_manager = ProjectManager(store)
        
        # If suggestion is provided, use it
        if request.suggestion:
            suggestion = request.suggestion
            if suggestion.mode != 'project':
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid suggestion mode: {suggestion.mode}. Expected 'project'"
                )
            
            if not suggestion.project_type or not suggestion.project_title or not suggestion.flow_id:
                raise HTTPException(
                    status_code=400,
                    detail="Suggestion must include project_type, project_title, and flow_id"
                )
            
            # Use default initiator_user_id from identity port
            from backend.app.routes.workspace_dependencies import get_identity_port_or_default
            identity_port = get_identity_port_or_default()
            initiator_user_id = identity_port.get_current_user_id()
            
            project = await project_manager.create_project(
                project_type=suggestion.project_type,
                title=suggestion.project_title,
                workspace_id=workspace_id,
                flow_id=suggestion.flow_id,
                initiator_user_id=initiator_user_id,
                metadata={
                    'initial_spec_md': suggestion.initial_spec_md,
                    'confidence': suggestion.confidence
                } if suggestion.initial_spec_md else {}
            )
        else:
            # Direct creation
            if not request.project_type or not request.title or not request.flow_id:
                raise HTTPException(
                    status_code=400,
                    detail="project_type, title, and flow_id are required"
                )
            
            from backend.app.routes.workspace_dependencies import get_identity_port_or_default
            identity_port = get_identity_port_or_default()
            initiator_user_id = request.initiator_user_id or identity_port.get_current_user_id()
            
            project = await project_manager.create_project(
                project_type=request.project_type,
                title=request.title,
                workspace_id=workspace_id,
                flow_id=request.flow_id,
                initiator_user_id=initiator_user_id,
                human_owner_user_id=request.human_owner_user_id,
                ai_pm_id=request.ai_pm_id
            )
        
        return {"project": project.model_dump(mode='json')}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create project: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

