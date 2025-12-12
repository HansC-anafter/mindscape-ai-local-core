"""
Blueprint API routes

Provides endpoints for listing and loading workspace blueprints.
"""

import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Path as PathParam, Body, Query, Depends
from pydantic import BaseModel, Field

from backend.app.services.blueprint import BlueprintLoader, BlueprintInfo, BlueprintLoadResult
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.routes.workspace_dependencies import get_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/blueprints", tags=["blueprints"])


class LoadBlueprintRequest(BaseModel):
    """Request to load a blueprint"""
    owner_user_id: str = Field(..., description="Owner user ID for the workspace")
    workspace_title: Optional[str] = Field(None, description="Optional workspace title (defaults to blueprint title)")
    workspace_description: Optional[str] = Field(None, description="Optional workspace description")


class BlueprintResponse(BaseModel):
    """Blueprint information response"""
    blueprint_id: str
    title: str
    description: str
    version: str
    workspace_type: Optional[str] = None


class ListBlueprintsResponse(BaseModel):
    """Response for listing blueprints"""
    blueprints: List[BlueprintResponse]


class LoadBlueprintResponse(BaseModel):
    """Response for loading a blueprint"""
    workspace_id: str
    blueprint_id: str
    artifacts_created: int
    playbooks_recommended: List[str]


@router.get("", response_model=ListBlueprintsResponse)
async def list_blueprints(
    store: MindscapeStore = Depends(get_store)
):
    """
    List all available blueprints

    Returns a list of all blueprints that can be loaded to create workspaces.
    """
    try:
        loader = BlueprintLoader(store)
        blueprints = loader.list_blueprints()

        blueprint_responses = [
            BlueprintResponse(
                blueprint_id=bp.blueprint_id,
                title=bp.title,
                description=bp.description,
                version=bp.version,
                workspace_type=bp.workspace_type
            )
            for bp in blueprints
        ]

        return ListBlueprintsResponse(blueprints=blueprint_responses)
    except Exception as e:
        logger.error(f"Failed to list blueprints: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list blueprints: {str(e)}")


@router.get("/{blueprint_id}", response_model=BlueprintResponse)
async def get_blueprint(
    blueprint_id: str = PathParam(..., description="Blueprint identifier"),
    store: MindscapeStore = Depends(get_store)
):
    """
    Get blueprint information

    Returns detailed information about a specific blueprint.
    """
    try:
        loader = BlueprintLoader(store)
        blueprint_info = loader.get_blueprint_info(blueprint_id)

        if not blueprint_info:
            raise HTTPException(status_code=404, detail=f"Blueprint not found: {blueprint_id}")

        return BlueprintResponse(
            blueprint_id=blueprint_info.blueprint_id,
            title=blueprint_info.title,
            description=blueprint_info.description,
            version=blueprint_info.version,
            workspace_type=blueprint_info.workspace_type
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get blueprint {blueprint_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get blueprint: {str(e)}")


@router.post("/{blueprint_id}/load", response_model=LoadBlueprintResponse, status_code=201)
async def load_blueprint(
    blueprint_id: str = PathParam(..., description="Blueprint identifier"),
    request: LoadBlueprintRequest = Body(...),
    store: MindscapeStore = Depends(get_store)
):
    """
    Load a blueprint and create a workspace

    Creates a new workspace based on the blueprint configuration, including:
    - Workspace with appropriate workspace_type
    - Initial artifacts from blueprint templates
    - Recommended playbooks list

    The actual playbook files are not copied - they remain in the global playbook library.
    """
    try:
        loader = BlueprintLoader(store)
        result = loader.load_blueprint(
            blueprint_id=blueprint_id,
            owner_user_id=request.owner_user_id,
            workspace_title=request.workspace_title,
            workspace_description=request.workspace_description
        )

        return LoadBlueprintResponse(
            workspace_id=result.workspace_id,
            blueprint_id=result.blueprint_id,
            artifacts_created=result.artifacts_created,
            playbooks_recommended=result.playbooks_recommended
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to load blueprint {blueprint_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to load blueprint: {str(e)}")
