"""
Workflow Templates API Routes

Handles workflow template management, user-defined workflows, and version control.
"""

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Path, Depends, Query, Body
from pydantic import BaseModel

from backend.app.models.workflow_template import (
    WorkflowTemplate,
    UserWorkflow,
    WorkflowVersion,
    CreateWorkflowTemplateRequest,
    CreateUserWorkflowRequest,
    InstantiateTemplateRequest
)
from backend.app.models.playbook import HandoffPlan
from backend.app.services.workflow_template_service import WorkflowTemplateService
from backend.app.core.ports.identity_port import IdentityPort
from backend.app.routes.workspace_dependencies import get_identity_port_or_default

router = APIRouter(tags=["workflow-templates"])
logger = logging.getLogger(__name__)


@router.post("/templates")
async def create_template(
    request: CreateWorkflowTemplateRequest = Body(...),
    identity_port: IdentityPort = Depends(get_identity_port_or_default)
):
    """
    Create a new workflow template

    Returns the created template.
    """
    try:
        service = WorkflowTemplateService()
        template = service.create_template(request)
        return template.dict()
    except Exception as e:
        logger.error(f"Failed to create template: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/templates")
async def list_templates(
    category: Optional[str] = Query(None, description="Filter by category")
):
    """
    List all workflow templates

    Optionally filter by category.
    """
    try:
        service = WorkflowTemplateService()
        templates = service.list_templates(category=category)
        return {"templates": [t.dict() for t in templates], "count": len(templates)}
    except Exception as e:
        logger.error(f"Failed to list templates: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/templates/{template_id}")
async def get_template(template_id: str = Path(..., description="Template ID")):
    """
    Get a workflow template by ID

    Returns the template if found.
    """
    try:
        service = WorkflowTemplateService()
        template = service.get_template(template_id)
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")
        return template.dict()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get template: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/templates/{template_id}/instantiate")
async def instantiate_template(
    template_id: str = Path(..., description="Template ID"),
    request: InstantiateTemplateRequest = Body(...),
    workspace_id: str = Query(..., description="Workspace ID"),
    profile_id: str = Query("default-user", description="User profile ID"),
    identity_port: IdentityPort = Depends(get_identity_port_or_default)
):
    """
    Instantiate a template into a HandoffPlan

    Returns the instantiated HandoffPlan ready for execution.
    """
    try:
        service = WorkflowTemplateService()
        handoff_plan = service.instantiate_template(
            request,
            workspace_id=workspace_id,
            profile_id=profile_id
        )
        return handoff_plan.dict()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to instantiate template: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/workflows")
async def create_user_workflow(
    request: CreateUserWorkflowRequest = Body(...),
    workspace_id: str = Query(..., description="Workspace ID"),
    profile_id: str = Query("default-user", description="User profile ID"),
    identity_port: IdentityPort = Depends(get_identity_port_or_default)
):
    """
    Create a user-defined workflow

    Returns the created workflow.
    """
    try:
        service = WorkflowTemplateService()
        workflow = service.create_user_workflow(
            request,
            workspace_id=workspace_id,
            profile_id=profile_id
        )
        return workflow.dict()
    except Exception as e:
        logger.error(f"Failed to create user workflow: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/workflows")
async def list_user_workflows(
    workspace_id: Optional[str] = Query(None, description="Filter by workspace ID"),
    profile_id: Optional[str] = Query(None, description="Filter by profile ID")
):
    """
    List user-defined workflows

    Optionally filter by workspace ID or profile ID.
    """
    try:
        service = WorkflowTemplateService()
        workflows = service.list_user_workflows(
            workspace_id=workspace_id,
            profile_id=profile_id
        )
        return {"workflows": [w.dict() for w in workflows], "count": len(workflows)}
    except Exception as e:
        logger.error(f"Failed to list user workflows: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/workflows/{workflow_id}")
async def get_user_workflow(
    workflow_id: str = Path(..., description="Workflow ID"),
    workspace_id: Optional[str] = Query(None, description="Workspace ID filter")
):
    """
    Get a user-defined workflow by ID

    Returns the workflow if found.
    """
    try:
        service = WorkflowTemplateService()
        workflow = service.get_user_workflow(workflow_id, workspace_id=workspace_id)
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")
        return workflow.dict()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get user workflow: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


class UpdateWorkflowRequest(BaseModel):
    """Request model for updating a workflow"""
    name: Optional[str] = None
    description: Optional[str] = None
    steps: Optional[list] = None
    context: Optional[dict] = None
    is_public: Optional[bool] = None
    tags: Optional[list] = None
    changelog: Optional[str] = None


@router.put("/workflows/{workflow_id}")
async def update_user_workflow(
    workflow_id: str = Path(..., description="Workflow ID"),
    request: UpdateWorkflowRequest = Body(...),
    profile_id: str = Query("default-user", description="User profile ID"),
    identity_port: IdentityPort = Depends(get_identity_port_or_default)
):
    """
    Update a user-defined workflow

    Creates a new version of the workflow. Returns the updated workflow.
    """
    try:
        service = WorkflowTemplateService()
        updates = request.dict(exclude_unset=True)
        if "changelog" in updates:
            changelog = updates.pop("changelog")
        else:
            changelog = None

        workflow = service.update_user_workflow(
            workflow_id,
            updates=updates,
            profile_id=profile_id,
            changelog=changelog
        )
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")
        return workflow.dict()
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update user workflow: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/workflows/{workflow_id}/versions")
async def get_workflow_versions(workflow_id: str = Path(..., description="Workflow ID")):
    """
    Get all versions of a workflow

    Returns list of workflow versions sorted by creation date (newest first).
    """
    try:
        service = WorkflowTemplateService()
        versions = service.get_workflow_versions(workflow_id)
        return {"versions": [v.dict() for v in versions], "count": len(versions)}
    except Exception as e:
        logger.error(f"Failed to get workflow versions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/workflows/{workflow_id}/versions/{version_id}/restore")
async def restore_workflow_version(
    workflow_id: str = Path(..., description="Workflow ID"),
    version_id: str = Path(..., description="Version ID"),
    profile_id: str = Query("default-user", description="User profile ID"),
    identity_port: IdentityPort = Depends(get_identity_port_or_default)
):
    """
    Restore a workflow to a specific version

    Creates a new version with the restored content. Returns the restored workflow.
    """
    try:
        service = WorkflowTemplateService()
        workflow = service.restore_workflow_version(
            workflow_id,
            version_id=version_id,
            profile_id=profile_id
        )
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow or version not found")
        return workflow.dict()
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to restore workflow version: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

