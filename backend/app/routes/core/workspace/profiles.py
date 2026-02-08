import logging
from typing import Optional

from fastapi import (
    APIRouter,
    HTTPException,
    Path as PathParam,
    Query,
    Body,
)

from ....models.workspace_runtime_profile import WorkspaceRuntimeProfile
from ....models.control_knob import ControlProfile
from ....services.mindscape_store import MindscapeStore
from ....services.stores.workspace_runtime_profile_store import (
    WorkspaceRuntimeProfileStore,
)
from ....services.stores.control_profile_store import ControlProfileStore
from ....services.stores.runtime_profile_presets import (
    get_preset_templates,
)
from ....services.knob_effect_compiler import KnobEffectCompiler
from ....services.knob_presets import PRESETS

router = APIRouter()
logger = logging.getLogger(__name__)
store = MindscapeStore()


# Initialize runtime profile store
def get_runtime_profile_store() -> WorkspaceRuntimeProfileStore:
    """Get runtime profile store instance"""
    return WorkspaceRuntimeProfileStore(store.db_path)


# Initialize control profile store
def get_control_profile_store() -> ControlProfileStore:
    """Get control profile store instance"""
    return ControlProfileStore(store.db_path)


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
        profile = profile_store.get_runtime_profile(workspace_id)

        if not profile:
            # Return default profile if not found
            profile = profile_store.create_default_profile(workspace_id)

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
        updated_profile = profile_store.save_runtime_profile(
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
        deleted = profile_store.delete_runtime_profile(workspace_id)

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
                                "label": "安全模板",
                                "description": "嚴格確認政策、完整品質關卡、保守工具政策",
                                "icon": "🛡️",
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
            "label": "安全模板",
            "description": "嚴格確認政策、完整品質關卡、保守工具政策",
            "icon": "🛡️",
        },
        "agile": {
            "name": "agile",
            "label": "敏捷模板",
            "description": "最小確認、快速執行、寬鬆工具政策",
            "icon": "⚡",
        },
        "research": {
            "name": "research",
            "label": "研究模板",
            "description": "詳細輸出、引用要求、完整決策日誌",
            "icon": "🔬",
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
        updated_profile = profile_store.save_runtime_profile(
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
        profile = profile_store.get_or_create_default_profile(workspace_id)

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
        updated_profile = profile_store.save_control_profile(
            workspace_id=workspace_id, profile=profile, updated_by=updated_by
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
        "input_text": "我有這些會議記錄",
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
                "intervention_level": ("更主動", "更旁觀"),
                "convergence": ("更收斂", "更發散"),
                "verbosity": ("更詳細", "更簡潔"),
                "retrieval_radius": ("更廣檢索", "更窄檢索"),
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
            runtime_profile_store = WorkspaceRuntimeProfileStore(db_path=store.db_path)
            base_runtime_profile = runtime_profile_store.get_runtime_profile(
                workspace_id
            )
            if not base_runtime_profile:
                base_runtime_profile = runtime_profile_store.create_default_profile(
                    workspace_id
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
            # TODO: Future enhancement: call fast LLM to generate actual output comparison
            if left_prompt:
                left_output = f"提示詞補丁預覽：\n{left_prompt[:300]}{'...' if len(left_prompt) > 300 else ''}\n\n[注意：這是提示詞差異預覽，非實際 LLM 輸出]"
            else:
                left_output = "[左邊設定：無提示詞變更]"

            if right_prompt:
                right_output = f"提示詞補丁預覽：\n{right_prompt[:300]}{'...' if len(right_prompt) > 300 else ''}\n\n[注意：這是提示詞差異預覽，非實際 LLM 輸出]"
            else:
                right_output = "[右邊設定：無提示詞變更]"

        except Exception as e:
            logger.warning(f"Failed to generate preview prompts: {e}", exc_info=True)
            left_output = "[預覽生成失敗]"
            right_output = "[預覽生成失敗]"

        return {
            "left_output": left_output,
            "right_output": right_output,
            "diff_summary": diff_summary,
            "preview_disclaimer": "預覽顯示提示詞差異，實際輸出可能略有不同",
            "preview_model": "prompt-preview",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate compare preview: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to generate compare preview: {str(e)}"
        )


@router.get(
    "/control-profile/presets",
    summary="Get control profile preset templates",
    description="""
    Get available control profile preset templates.

    Presets provide pre-configured knob values for common use cases:
    - **observer**: Low intervention, organize only
    - **advisor**: Medium-high intervention, proactive suggestions
    - **executor**: High intervention, ready-to-confirm drafts
    """,
    tags=["control-profile"],
    responses={200: {"description": "List of available preset templates"}},
)
async def get_control_profile_presets():
    """Get available control profile preset templates"""
    presets = [
        {
            "id": "observer",
            "name": "整理模式",
            "description": "只整理資訊，不主動建議",
            "icon": "👁️",
            "knob_values": PRESETS["observer"].knob_values,
        },
        {
            "id": "advisor",
            "name": "提案模式",
            "description": "主動提出建議和選項",
            "icon": "💡",
            "knob_values": PRESETS["advisor"].knob_values,
        },
        {
            "id": "executor",
            "name": "可直接交付",
            "description": "直接產出可確認的草稿",
            "icon": "🚀",
            "knob_values": PRESETS["executor"].knob_values,
        },
    ]
    return {"presets": presets}
