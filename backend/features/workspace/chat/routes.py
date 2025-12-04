"""
Workspace Chat Routes - Refactored modular version

Handles /workspaces/{id}/chat endpoint and CTA actions.
"""

import logging
import traceback
import sys
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, Path, Body, Depends
from fastapi.responses import StreamingResponse

from backend.app.models.workspace import Workspace, WorkspaceChatRequest, WorkspaceChatResponse
from backend.app.routes.workspace_dependencies import (
    get_workspace,
    get_orchestrator
)
from backend.app.services.conversation_orchestrator import ConversationOrchestrator

from .handlers.cta_handler import handle_cta_action
from .handlers.suggestion_handler import handle_suggestion_action
from .streaming.generator import generate_streaming_response

router = APIRouter(prefix="/api/v1/workspaces", tags=["workspaces-chat"])
logger = logging.getLogger(__name__)


@router.post("/{workspace_id}/chat", response_model=WorkspaceChatResponse)
async def workspace_chat(
    workspace_id: str = Path(..., description="Workspace ID"),
    request: WorkspaceChatRequest = Body(...),
    workspace: Workspace = Depends(get_workspace),
    orchestrator: ConversationOrchestrator = Depends(get_orchestrator)
):
    """
    Workspace chat endpoint - unified entry point for all interactions

    Handles:
    - User messages
    - File uploads
    - Playbook triggering
    - QA responses
    - CTA actions (via timeline_item_id + action)
    - Dynamic suggestion actions (via action + action_params)
    """
    try:
        profile_id = workspace.owner_user_id

        # Handle CTA actions
        if request.timeline_item_id and request.action:
            result = await handle_cta_action(
                orchestrator=orchestrator,
                workspace_id=workspace_id,
                profile_id=profile_id,
                timeline_item_id=request.timeline_item_id,
                action=request.action,
                confirm=request.confirm,
                project_id=workspace.primary_project_id
            )
            return WorkspaceChatResponse(**result)

        # Handle suggestion actions
        if request.action and not request.timeline_item_id:
            result = await handle_suggestion_action(
                orchestrator=orchestrator,
                workspace_id=workspace_id,
                profile_id=profile_id,
                action=request.action,
                action_params=request.action_params or {},
                project_id=workspace.primary_project_id,
                message_id=getattr(request, 'message_id', None)
            )
            return WorkspaceChatResponse(**result)

        # Validate message
        if not request.message:
            raise HTTPException(status_code=400, detail="Message is required for non-CTA requests")

        logger.info(f"WorkspaceChat: Received message request, stream={request.stream}, message={request.message[:50]}...")
        print(f"WorkspaceChat: Received message request, stream={request.stream}, message={request.message[:50]}...", file=sys.stderr)

        # Handle streaming requests
        if request.stream:
            logger.info(f"WorkspaceChat: Using STREAMING path (bypasses route_message)")
            print(f"WorkspaceChat: Using STREAMING path (bypasses route_message)", file=sys.stderr)

            return StreamingResponse(
                generate_streaming_response(
                    request=request,
                    workspace=workspace,
                    workspace_id=workspace_id,
                    profile_id=profile_id,
                    orchestrator=orchestrator
                ),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no"
                }
            )

        # Non-streaming mode (existing logic)
        result = await orchestrator.route_message(
            workspace_id=workspace_id,
            profile_id=profile_id,
            message=request.message,
            files=request.files,
            mode=request.mode,
            project_id=workspace.primary_project_id,
            workspace=workspace
        )

        return WorkspaceChatResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Workspace chat error: {str(e)}\n{traceback.format_exc()}")
        print(f"ERROR: Workspace chat error: {str(e)}", file=sys.stderr)
        print(traceback.format_exc(), file=sys.stderr)
        raise HTTPException(status_code=500, detail=f"Failed to process workspace chat: {str(e)}")

