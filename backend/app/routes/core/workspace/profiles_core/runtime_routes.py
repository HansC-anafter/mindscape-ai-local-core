
import asyncio
from typing import Optional

from fastapi import APIRouter, Body, HTTPException, Path as PathParam, Query

from backend.app.models.workspace_runtime_profile import WorkspaceRuntimeProfile

from .state import logger, store
from .stores import get_runtime_profile_store

router = APIRouter()

@router.get(
    "/{workspace_id}/runtime-profile",
    response_model=WorkspaceRuntimeProfile,
    summary="Get workspace runtime profile",
    description="""
    Get the runtime profile configuration for a workspace.

    The runtime profile defines execution contracts, interaction budgets, output contracts,
    confirmation policies, and tool policies for the workspace.

    **Returns:**
    - If a profile exists: Returns the configured runtime profile
    - If no profile exists: Returns a default profile with standard settings

    **Example Response:**
    ```json
    {
        "default_mode": "execution",
        "interaction_budget": {
            "max_questions_per_turn": 0,
            "assume_defaults": true
        },
        "output_contract": {
            "coding_style": "patch_first",
            "minimize_explanation": true
        },
        "confirmation_policy": {
            "auto_read": true,
            "confirm_external_write": true
        },
        "tool_policy": {
            "allowlist": ["code_editor", "file_manager"]
        }
    }
    ```
    """,
    tags=["runtime-profile"],
    responses={
        200: {
            "description": "Runtime profile retrieved successfully",
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
        404: {"description": "Workspace not found"},
        500: {"description": "Internal server error"},
    },
)
async def get_runtime_profile(
    workspace_id: str = PathParam(..., description="Workspace ID", example="ws_123")
):
    """
    Get workspace runtime profile

    Returns the runtime profile configuration for the workspace.
    If no profile exists, returns a default profile.
    """
    try:
        profile_store = get_runtime_profile_store()
        profile = await asyncio.to_thread(
            profile_store.get_runtime_profile, workspace_id
        )

        if not profile:
            # Return default profile if not found
            profile = await asyncio.to_thread(
                profile_store.create_default_profile, workspace_id
            )

        return profile
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get runtime profile: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to get runtime profile: {str(e)}"
        )


@router.put(
    "/{workspace_id}/runtime-profile",
    response_model=WorkspaceRuntimeProfile,
    summary="Update workspace runtime profile",
    description="""
    Update or create the runtime profile configuration for a workspace.

    **Request Body:**
    The request body should contain a complete `WorkspaceRuntimeProfile` object with all desired settings.

    **Best Practices:**
    1. Use preset templates for common configurations (see `/runtime-profile/presets`)
    2. Start with minimal changes and iterate
    3. Test configuration in a development workspace first
    4. Document changes using `updated_reason` parameter

    **Example Request (Cursor-style configuration):**
    ```json
    {
        "default_mode": "execution",
        "interaction_budget": {
            "max_questions_per_turn": 0,
            "assume_defaults": true,
            "require_assumptions_list": true
        },
        "output_contract": {
            "coding_style": "patch_first",
            "minimize_explanation": true,
            "show_rationale_level": "brief"
        },
        "confirmation_policy": {
            "auto_read": true,
            "confirm_external_write": true,
            "confirmation_format": "list_changes"
        },
        "tool_policy": {
            "allowlist": ["code_editor", "file_manager"]
        }
    }
    ```

    **Note:** Partial updates are not supported. You must provide the complete profile configuration.
    """,
    tags=["runtime-profile"],
    responses={
        200: {
            "description": "Runtime profile updated successfully",
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
        404: {"description": "Workspace not found"},
        400: {"description": "Invalid profile configuration"},
        500: {"description": "Internal server error"},
    },
)
async def update_runtime_profile(
    workspace_id: str = PathParam(..., description="Workspace ID", example="ws_123"),
    profile: WorkspaceRuntimeProfile = Body(
        ..., description="Runtime profile configuration"
    ),
    updated_by: Optional[str] = Query(
        None, description="User ID who updated this profile", example="user_456"
    ),
    updated_reason: Optional[str] = Query(
        None, description="Reason for update", example="Enable Cursor-style execution"
    ),
):
    """
    Update workspace runtime profile

    Updates or creates the runtime profile configuration for the workspace.
    """
    try:
        # Verify workspace exists
        workspace = await store.get_workspace(workspace_id)
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")

        profile_store = get_runtime_profile_store()
        updated_profile = await asyncio.to_thread(
            profile_store.save_runtime_profile,
            workspace_id=workspace_id,
            profile=profile,
            updated_by=updated_by,
            updated_reason=updated_reason,
        )

        return updated_profile
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update runtime profile: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to update runtime profile: {str(e)}"
        )


@router.delete(
    "/{workspace_id}/runtime-profile",
    status_code=204,
    summary="Delete workspace runtime profile",
    description="""
    Delete the runtime profile configuration for a workspace.

    **Warning:** This will remove all custom runtime profile settings.
    The workspace will revert to default behavior after deletion.

    **Note:** This operation cannot be undone. Consider backing up the profile
    configuration before deletion if you may need to restore it later.
    """,
    tags=["runtime-profile"],
    responses={
        204: {"description": "Runtime profile deleted successfully"},
        404: {"description": "Runtime profile not found"},
        500: {"description": "Internal server error"},
    },
)
async def delete_runtime_profile(
    workspace_id: str = PathParam(..., description="Workspace ID", example="ws_123")
):
    """
    Delete workspace runtime profile

    Removes the runtime profile configuration for the workspace.
    """
    try:
        profile_store = get_runtime_profile_store()
        deleted = await asyncio.to_thread(
            profile_store.delete_runtime_profile, workspace_id
        )

        if not deleted:
            raise HTTPException(status_code=404, detail="Runtime profile not found")

        return None
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete runtime profile: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to delete runtime profile: {str(e)}"
        )
