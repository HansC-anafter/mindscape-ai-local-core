"""
Deployment API routes

Provides REST API for deploying sandbox projects to target directories.
"""

import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Path as PathParam, Body
from pydantic import BaseModel, Field

from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.deployment.deployment_service import DeploymentService

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/projects/{project_id}/deploy", tags=["deployment"])

logger = logging.getLogger(__name__)

store = MindscapeStore()
deployment_service = DeploymentService(store)


class DeployRequest(BaseModel):
    """Request model for deployment"""
    sandbox_id: str = Field(..., description="Sandbox identifier")
    target_path: str = Field(..., description="Target directory path")
    files: Optional[List[str]] = Field(None, description="Optional list of specific files to deploy")
    git_branch: Optional[str] = Field(None, description="Optional Git branch name")
    commit_message: Optional[str] = Field(None, description="Optional commit message")
    auto_commit: bool = Field(False, description="Whether to automatically commit")
    auto_push: bool = Field(False, description="Whether to automatically push")


@router.post("", response_model=dict)
async def deploy_project(
    workspace_id: str = PathParam(..., description="Workspace identifier"),
    project_id: str = PathParam(..., description="Project identifier"),
    request: DeployRequest = Body(...)
):
    """
    Deploy sandbox project to target path

    Returns deployment results including copied files, Git commands, and VM commands.
    """
    try:
        result = await deployment_service.deploy_sandbox(
            workspace_id=workspace_id,
            sandbox_id=request.sandbox_id,
            target_path=request.target_path,
            files=request.files,
            git_branch=request.git_branch,
            commit_message=request.commit_message,
            auto_commit=request.auto_commit,
            auto_push=request.auto_push
        )

        if result.get("status") == "error":
            raise HTTPException(status_code=500, detail=result.get("error", "Deployment failed"))

        return result
    except ValueError as e:
        logger.error(f"Invalid deployment request: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Deployment failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

