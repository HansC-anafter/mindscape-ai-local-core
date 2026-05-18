
import asyncio
from typing import Optional

from fastapi import APIRouter, Body, HTTPException, Path as PathParam, Query

from backend.app.models.workspace_runtime_profile import WorkspaceRuntimeProfile
from backend.app.services.stores.runtime_profile_presets import get_preset_templates

from .state import logger, store
from .stores import get_runtime_profile_store

router = APIRouter()

@router.get(
    "/runtime-profile/presets",
    summary="Get runtime profile preset templates",
    description="""
    Get available runtime profile preset templates.

    Preset templates provide pre-configured runtime profiles for common use cases:

    - **security**: Strict confirmation policies, complete quality gates, conservative tool policies
    - **agile**: Minimal confirmation, fast execution, relaxed tool policies
    - **research**: Detailed output, citation requirements, complete decision logs

    **Usage:**
    1. Get available presets using this endpoint
    2. Apply a preset using `POST /{workspace_id}/runtime-profile/apply-preset`
    3. Optionally customize the applied preset using `PUT /{workspace_id}/runtime-profile`
    """,
    tags=["runtime-profile"],
    responses={
        200: {
            "description": "List of available preset templates",
            "content": {
                "application/json": {
                    "example": {
                        "presets": [
                            {
                                "name": "security",
                                "label": "Security template",
                                "description": "Strict confirmation policies, complete quality gates, and conservative tool policies",
                                "icon": "shield",
                            },
                        ]
                    }
                }
            },
        }
    },
)
async def get_runtime_profile_presets():
    """
    Get available runtime profile preset templates

    Returns list of available preset template names and their descriptions.
    """
    presets = {
        "security": {
            "name": "security",
            "label": "Security template",
            "description": "Strict confirmation policies, complete quality gates, and conservative tool policies",
            "icon": "shield",
        },
        "agile": {
            "name": "agile",
            "label": "Agile template",
            "description": "Minimal confirmation, fast execution, and relaxed tool policies",
            "icon": "bolt",
        },
        "research": {
            "name": "research",
            "label": "Research template",
            "description": "Detailed output, citation requirements, and complete decision logs",
            "icon": "research",
        },
    }
    return {"presets": list(presets.values())}


@router.post(
    "/{workspace_id}/runtime-profile/apply-preset",
    response_model=WorkspaceRuntimeProfile,
    summary="Apply preset template to runtime profile",
    description="""
    Apply a preset template to create or update the workspace runtime profile.

    **Available Presets:**
    - `security`: Strict confirmation policies, complete quality gates, conservative tool policies
    - `agile`: Minimal confirmation, fast execution, relaxed tool policies
    - `research`: Detailed output, citation requirements, complete decision logs

    **Example Request:**
    ```json
    {
        "preset_name": "agile"
    }
    ```

    **Best Practices:**
    1. Use presets as a starting point for new workspaces
    2. Customize the applied preset if needed using `PUT /{workspace_id}/runtime-profile`
    3. Document why you chose a specific preset using `updated_reason`
    """,
    tags=["runtime-profile"],
    responses={
        200: {
            "description": "Preset applied successfully",
            "content": {
                "application/json": {
                    "example": {
                        "default_mode": "execution",
                        "interaction_budget": {
                            "max_questions_per_turn": 0,
                            "assume_defaults": True,
                        },
                    }
                }
            },
        },
        400: {"description": "Invalid preset name"},
        404: {"description": "Workspace not found"},
        500: {"description": "Internal server error"},
    },
)
async def apply_runtime_profile_preset(
    workspace_id: str = PathParam(..., description="Workspace ID", example="ws_123"),
    preset_name: str = Body(
        ...,
        embed=True,
        description="Preset template name (security, agile, research)",
        example="agile",
    ),
    updated_by: Optional[str] = Query(
        None, description="User ID who applied this preset", example="user_456"
    ),
    updated_reason: Optional[str] = Query(
        None,
        description="Reason for applying preset",
        example="Setting up development workspace",
    ),
):
    """
    Apply a preset template to workspace runtime profile

    Creates or updates the runtime profile using a preset template.
    """
    try:
        # Verify workspace exists
        workspace = await store.get_workspace(workspace_id)
        if not workspace:
            raise HTTPException(
                status_code=404, detail=f"Workspace {workspace_id} not found"
            )

        # Get preset template
        preset_templates = get_preset_templates()
        if preset_name not in preset_templates:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid preset name: {preset_name}. Available presets: {', '.join(preset_templates.keys())}",
            )

        # Create profile from preset
        preset_func = preset_templates[preset_name]
        profile = preset_func(workspace_id)

        # Save profile
        profile_store = get_runtime_profile_store()
        updated_profile = await asyncio.to_thread(
            profile_store.save_runtime_profile,
            workspace_id=workspace_id,
            profile=profile,
            updated_by=updated_by,
            updated_reason=updated_reason or f"Applied {preset_name} preset template",
        )

        logger.info(f"Applied {preset_name} preset to workspace {workspace_id}")
        return updated_profile
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to apply preset: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to apply preset: {str(e)}")
