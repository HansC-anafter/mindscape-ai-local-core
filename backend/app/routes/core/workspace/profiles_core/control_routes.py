
import asyncio
from typing import Optional

from fastapi import APIRouter, Body, HTTPException, Path as PathParam, Query

from backend.app.models.control_knob import ControlProfile
from backend.app.services.knob_effect_compiler import KnobEffectCompiler
from backend.app.services.stores.workspace_runtime_profile_store import (
    WorkspaceRuntimeProfileStore,
)

from .state import logger, store
from .stores import get_control_profile_store

router = APIRouter()

@router.get(
    "/{workspace_id}/control-profile",
    response_model=ControlProfile,
    summary="Get workspace control profile",
    description="""
    Get the control profile (knob-based control) configuration for a workspace.

    Control Profile allows users to adjust LLM behavior through intuitive knobs:
    - Intervention Level: How proactive the AI should be
    - Convergence: How quickly to converge to decisions
    - Verbosity: Output density (one-liner to full draft)
    - Retrieval Radius: Scope of information retrieval

    **Returns:**
    - If a profile exists: Returns the configured control profile
    - If no profile exists: Returns default "advisor" preset
    """,
    tags=["control-profile"],
    responses={
        200: {"description": "Control profile retrieved successfully"},
        404: {"description": "Workspace not found"},
        500: {"description": "Internal server error"},
    },
)
async def get_control_profile(
    workspace_id: str = PathParam(..., description="Workspace ID", example="ws_123")
):
    """Get workspace control profile"""
    try:
        # Verify workspace exists
        workspace = await store.get_workspace(workspace_id)
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")

        profile_store = get_control_profile_store()
        profile = await asyncio.to_thread(
            profile_store.get_or_create_default_profile, workspace_id
        )

        return profile
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get control profile: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to get control profile: {str(e)}"
        )


@router.put(
    "/{workspace_id}/control-profile",
    response_model=ControlProfile,
    summary="Update workspace control profile",
    description="""
    Update or create the control profile configuration for a workspace.

    **Request Body:**
    The request body should contain a complete `ControlProfile` object with knob values.

    **Example Request:**
    ```json
    {
        "id": "custom",
        "name": "Custom Profile",
        "knobs": [...],
        "knob_values": {
            "intervention_level": 60,
            "convergence": 50,
            "verbosity": 70,
            "retrieval_radius": 50
        },
        "preset_id": "advisor"
    }
    ```
    """,
    tags=["control-profile"],
    responses={
        200: {"description": "Control profile updated successfully"},
        404: {"description": "Workspace not found"},
        500: {"description": "Internal server error"},
    },
)
async def update_control_profile(
    workspace_id: str = PathParam(..., description="Workspace ID", example="ws_123"),
    profile: ControlProfile = Body(..., description="Control profile configuration"),
    updated_by: Optional[str] = Query(
        None, description="User ID who updated this profile"
    ),
):
    """Update workspace control profile"""
    try:
        # Verify workspace exists
        workspace = await store.get_workspace(workspace_id)
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")

        profile_store = get_control_profile_store()
        updated_profile = await asyncio.to_thread(
            profile_store.save_control_profile,
            workspace_id=workspace_id,
            profile=profile,
            updated_by=updated_by,
        )

        return updated_profile
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update control profile: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to update control profile: {str(e)}"
        )


@router.post(
    "/{workspace_id}/control-profile/compare-preview",
    summary="Compare preview for control profile",
    description="""
    Generate a comparison preview showing output differences between two control profiles.

    This endpoint uses a fast model to generate preview outputs for the same input
    with different control profile settings, allowing users to see the effect of knob adjustments.

    **Request Body:**
    ```json
    {
        "input_text": "I have these meeting notes",
        "left_profile": {...},
        "right_profile": {...}
    }
    ```

    **Returns:**
    - left_output: Output with left profile
    - right_output: Output with right profile
    - diff_summary: Rule-based difference summary
    - preview_disclaimer: Disclaimer about preview accuracy
    """,
    tags=["control-profile"],
    responses={
        200: {"description": "Comparison preview generated successfully"},
        404: {"description": "Workspace not found"},
        500: {"description": "Internal server error"},
    },
)
async def compare_preview(
    workspace_id: str = PathParam(..., description="Workspace ID", example="ws_123"),
    input_text: str = Body(..., description="User input text for comparison"),
    left_profile: ControlProfile = Body(
        ..., description="Left profile (usually current)"
    ),
    right_profile: ControlProfile = Body(
        ..., description="Right profile (usually new/preset)"
    ),
):
    """
    Compare preview: Show output differences between two control profiles

    v2.4: Uses rule-based diff summary (not LLM-generated) for reliability
    """
    try:
        # Verify workspace exists
        workspace = await store.get_workspace(workspace_id)
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")

        # v2.4: Rule-based difference summary
        def compute_diff_summary(left: ControlProfile, right: ControlProfile) -> str:
            """Rule-based diff summary (not LLM-generated)"""
            diffs = []
            knob_labels = {
                "intervention_level": ("more proactive", "more observational"),
                "convergence": ("more convergent", "more divergent"),
                "verbosity": ("more detailed", "more concise"),
                "retrieval_radius": ("broader retrieval", "narrower retrieval"),
            }

            for knob_id, (high_label, low_label) in knob_labels.items():
                left_val = left.knob_values.get(knob_id, 50)
                right_val = right.knob_values.get(knob_id, 50)
                delta = right_val - left_val

                if abs(delta) >= 10:  # Only show significant differences
                    label = high_label if delta > 0 else low_label
                    diffs.append(f"{label} ({'+' if delta > 0 else ''}{delta})")

            if not diffs:
                return "Settings difference is minimal"
            return "Right side: " + ", ".join(diffs)

        diff_summary = compute_diff_summary(left_profile, right_profile)

        # Generate preview outputs using compiled profiles
        # Note: This is a simplified preview - full implementation would call LLM
        try:
            runtime_profile_store = WorkspaceRuntimeProfileStore()
            base_runtime_profile = await asyncio.to_thread(
                runtime_profile_store.get_runtime_profile, workspace_id
            )
            if not base_runtime_profile:
                base_runtime_profile = await asyncio.to_thread(
                    runtime_profile_store.create_default_profile, workspace_id
                )

            compiler = KnobEffectCompiler(knobs=left_profile.knobs)
            left_prompt, _, _, _ = compiler.compile(
                control_profile=left_profile, base_runtime_profile=base_runtime_profile
            )

            compiler_right = KnobEffectCompiler(knobs=right_profile.knobs)
            right_prompt, _, _, _ = compiler_right.compile(
                control_profile=right_profile, base_runtime_profile=base_runtime_profile
            )

            # For now, return prompt previews (actual LLM generation can be added later)
            # A future enhancement can call a fast LLM to generate actual output comparison.
            if left_prompt:
                left_output = f"Prompt patch preview:\n{left_prompt[:300]}{'...' if len(left_prompt) > 300 else ''}\n\n[Note: this is a prompt-diff preview, not actual LLM output]"
            else:
                left_output = "[Left settings: no prompt changes]"

            if right_prompt:
                right_output = f"Prompt patch preview:\n{right_prompt[:300]}{'...' if len(right_prompt) > 300 else ''}\n\n[Note: this is a prompt-diff preview, not actual LLM output]"
            else:
                right_output = "[Right settings: no prompt changes]"

        except Exception as e:
            logger.warning(f"Failed to generate preview prompts: {e}", exc_info=True)
            left_output = "[Preview generation failed]"
            right_output = "[Preview generation failed]"

        return {
            "left_output": left_output,
            "right_output": right_output,
            "diff_summary": diff_summary,
            "preview_disclaimer": "Preview shows prompt differences; actual output may vary slightly",
            "preview_model": "prompt-preview",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate compare preview: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to generate compare preview: {str(e)}"
        )
