import logging
from typing import Optional

from fastapi import (
    APIRouter,
    HTTPException,
    Path as PathParam,
    Query,
)

from ....services.mindscape_store import MindscapeStore
from ....services.workbench_service import WorkbenchService
from ....services.ai_team_service import get_member_info
from ....services.conversation.context_builder import ContextBuilder
from ....services.system_settings_store import SystemSettingsStore

router = APIRouter()
logger = logging.getLogger(__name__)
store = MindscapeStore()


@router.get("/{workspace_id}/workbench")
async def get_workspace_workbench(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    profile_id: str = Query("default-user", description="Profile ID"),
):
    """Get workbench data for a workspace"""
    try:
        workbench_service = WorkbenchService(store=store)
        data = await workbench_service.get_workbench_data(workspace_id, profile_id)
        return data
    except Exception as e:
        logger.error(f"Failed to get workbench data: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{workspace_id}/workbench/context-token-count")
async def get_workspace_context_token_count(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    profile_id: str = Query("default-user", description="Profile ID"),
):
    """Get context token count for workspace workbench"""
    try:
        workspace = await store.get_workspace(workspace_id)
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")

        # Get model name from system settings - must be configured by user
        settings_store = SystemSettingsStore()
        chat_setting = settings_store.get_setting("chat_model")

        if not chat_setting or not chat_setting.value:
            raise ValueError(
                "LLM model not configured. Please select a model in the system settings panel."
            )

        model_name = str(chat_setting.value)
        if not model_name or model_name.strip() == "":
            raise ValueError(
                "LLM model is empty. Please select a valid model in the system settings panel."
            )

        context_builder = ContextBuilder(store=store, model_name=model_name)

        enhanced_prompt = await context_builder.build_qa_context(
            workspace_id=workspace_id,
            message="",
            profile_id=profile_id,
            workspace=workspace,
        )
        token_count = (
            context_builder.estimate_token_count(enhanced_prompt, model_name) or 0
        )

        return {
            "workspace_id": workspace_id,
            "token_count": token_count,
            "model_name": model_name,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get context token count: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{workspace_id}/ai-team-members")
async def get_ai_team_members(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    playbook_codes: Optional[str] = Query(
        None, description="Comma-separated list of playbook codes"
    ),
):
    """Get AI team members for given playbook codes"""
    try:
        playbook_codes_list = []
        if playbook_codes:
            playbook_codes_list = [
                code.strip() for code in playbook_codes.split(",") if code.strip()
            ]

        members = []
        for playbook_code in playbook_codes_list:
            member_info = get_member_info(playbook_code)
            if member_info and member_info.get("visible", True):
                members.append(member_info)

        # Sort by order
        members.sort(key=lambda m: m.get("order", 999))

        return {"members": members, "count": len(members)}
    except Exception as e:
        logger.error(f"Failed to get AI team members: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
