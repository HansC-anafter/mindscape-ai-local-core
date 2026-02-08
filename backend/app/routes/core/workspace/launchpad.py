import logging
from typing import Any, Dict

from fastapi import (
    APIRouter,
    HTTPException,
    Path as PathParam,
    Body,
)

from ....services.mindscape_store import MindscapeStore
from ....services.workspace_seed_service import WorkspaceSeedService
from .utils import ensure_workspace_launch_status

router = APIRouter()
logger = logging.getLogger(__name__)
store = MindscapeStore()


@router.get("/{workspace_id}/launchpad")
async def get_workspace_launchpad(
    workspace_id: str = PathParam(..., description="Workspace ID")
):
    """
    Get workspace launchpad data

    Returns launchpad data for display:
    - brief: Workspace brief (1-2 paragraphs)
    - initial_intents: List of intent cards (3-7 items)
    - first_playbook: First playbook to run
    - tool_connections: Tool connection status
    - launch_status: Current launch status

    This endpoint is optimized for Launchpad display and returns only necessary data.
    """
    try:
        workspace = await store.get_workspace(workspace_id)
        if not workspace:
            # Return empty launchpad instead of 404 error
            # This allows the UI to show the setup state
            return {
                "brief": None,
                "initial_intents": [],
                "first_playbook": None,
                "tool_connections": [],
                "launch_status": "pending",
            }

        # Reconcile launch_status
        current_status = await ensure_workspace_launch_status(workspace_id, workspace)

        blueprint = workspace.workspace_blueprint
        if not blueprint:
            # Return empty launchpad if no blueprint
            return {
                "brief": None,
                "initial_intents": [],
                "first_playbook": None,
                "tool_connections": [],
                "launch_status": current_status,
            }

        return {
            "brief": blueprint.brief,
            "initial_intents": blueprint.initial_intents or [],
            "first_playbook": blueprint.first_playbook,
            "tool_connections": [
                {
                    "tool_type": conn.tool_type,
                    "danger_level": conn.danger_level,
                    "default_readonly": conn.default_readonly,
                    "allowed_roles": conn.allowed_roles,
                }
                for conn in (blueprint.tool_connections or [])
            ],
            "launch_status": current_status,
        }
    except Exception as e:
        logger.error(
            f"Error in get_workspace_launchpad for {workspace_id}: {e}", exc_info=True
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{workspace_id}/seed")
async def process_workspace_seed(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    seed_type: str = Body(..., description="Seed type: 'text' | 'file' | 'urls'"),
    payload: Any = Body(
        ...,
        description="Seed payload (text string, file data, or list of {url, note} dicts)",
    ),
    locale: str = Body("zh-TW", description="Locale for LLM generation"),
):
    """
    Process workspace seed and generate blueprint digest (MFR)

    This endpoint processes a seed input (text/file/urls) and generates a workspace blueprint
    without requiring full knowledge base import or embedding.

    Args:
        workspace_id: Workspace ID
        seed_type: Seed type ("text" | "file" | "urls")
        payload: Seed payload:
            - For "text": string
            - For "file": file data (base64 or file path)
            - For "urls": list of {"url": str, "note": str} dicts
        locale: Locale for LLM generation (default: "zh-TW")

    Returns:
        {
            "brief": str,
            "facts": List[str],
            "unknowns": List[str],
            "next_actions": List[str],
            "intents": List[Dict],
            "starter_kit_type": str,
            "first_playbook": str
        }
    """
    try:
        # Validate workspace exists
        workspace = await store.get_workspace(workspace_id)
        if not workspace:
            raise HTTPException(
                status_code=404, detail=f"Workspace {workspace_id} not found"
            )

        # Validate seed_type
        if seed_type not in ["text", "file", "urls"]:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid seed_type: {seed_type}. Must be 'text', 'file', or 'urls'",
            )

        # Process seed
        seed_service = WorkspaceSeedService(store)
        digest = await seed_service.process_seed(
            workspace_id=workspace_id,
            seed_type=seed_type,
            payload=payload,
            locale=locale,
        )

        return digest

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to process workspace seed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to process seed: {str(e)}")
