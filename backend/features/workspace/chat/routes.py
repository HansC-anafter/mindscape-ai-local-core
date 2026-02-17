"""
Workspace Chat Routes - Refactored modular version

Handles /workspaces/{id}/chat endpoint and CTA actions.
"""

import logging
import traceback
import sys
import uuid
import json
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, Path, Body, Depends, BackgroundTasks
from fastapi.responses import StreamingResponse, JSONResponse

from backend.app.models.workspace import (
    Workspace,
    WorkspaceChatRequest,
    WorkspaceChatResponse,
)
from backend.app.routes.workspace_dependencies import get_workspace, get_orchestrator
from backend.app.services.conversation_orchestrator import ConversationOrchestrator
from backend.app.services.chat_orchestrator_service import ChatOrchestratorService

from .handlers.cta_handler import handle_cta_action
from .handlers.suggestion_handler import handle_suggestion_action
from .streaming.generator import generate_streaming_response

router = APIRouter(prefix="/api/v1/workspaces", tags=["workspaces-chat"])
logger = logging.getLogger(__name__)


@router.post("/{workspace_id}/chat", response_model=WorkspaceChatResponse)
async def workspace_chat(
    workspace_id: str = Path(..., description="Workspace ID"),
    request: WorkspaceChatRequest = Body(...),
    background_tasks: BackgroundTasks = None,
    workspace: Workspace = Depends(get_workspace),
    orchestrator: ConversationOrchestrator = Depends(get_orchestrator),
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
                project_id=workspace.primary_project_id,
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
                message_id=getattr(request, "message_id", None),
            )
            return WorkspaceChatResponse(**result)

        # Validate message
        if not request.message:
            raise HTTPException(
                status_code=400, detail="Message is required for non-CTA requests"
            )

        logger.info(
            f"WorkspaceChat: Received message request, message={request.message[:50]}..."
        )

        user_event_id = str(uuid.uuid4())
        service = ChatOrchestratorService(orchestrator)

        # stream=False: await synchronously and return display_events
        # (used by messaging_handler for LINE reply delivery)
        if not getattr(request, "stream", True):
            await service.run_background_chat(
                request=request,
                workspace=workspace,
                workspace_id=workspace_id,
                profile_id=profile_id,
                user_event_id=user_event_id,
            )

            # Fetch the generated events from DB to return to caller
            try:
                import asyncio

                loop = asyncio.get_running_loop()
                events = await loop.run_in_executor(
                    None,
                    lambda: orchestrator.store.events.get_events_by_thread(
                        workspace_id=workspace_id,
                        thread_id=None,
                        limit=5,
                    ),
                )
                display_events = [
                    {
                        "id": e.id,
                        "actor": e.actor.value if hasattr(e.actor, "value") else str(e.actor),
                        "payload": e.payload,
                        "timestamp": e.timestamp.isoformat() if e.timestamp else None,
                    }
                    for e in (events or [])
                ]
            except Exception as fetch_err:
                logger.warning(f"WorkspaceChat: Failed to fetch display_events: {fetch_err}")
                display_events = []

            return JSONResponse(
                status_code=200,
                content={
                    "status": "completed",
                    "event_id": user_event_id,
                    "workspace_id": workspace_id,
                    "display_events": display_events,
                },
            )

        # stream=True (default): fire-and-forget for web UI with SSE feedback
        if background_tasks:
            background_tasks.add_task(
                service.run_background_chat,
                request=request,
                workspace=workspace,
                workspace_id=workspace_id,
                profile_id=profile_id,
                user_event_id=user_event_id,
            )
        else:
            await service.run_background_chat(
                request=request,
                workspace=workspace,
                workspace_id=workspace_id,
                profile_id=profile_id,
                user_event_id=user_event_id,
            )

        return JSONResponse(
            status_code=202,
            content={
                "status": "accepted",
                "message": "Chat request queued for background processing",
                "task_id": user_event_id,
                "event_id": user_event_id,
                "workspace_id": workspace_id,
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Workspace chat error: {str(e)}\n{traceback.format_exc()}")
        print(f"ERROR: Workspace chat error: {str(e)}", file=sys.stderr)
        print(traceback.format_exc(), file=sys.stderr)
        # Return error response with workspace_id
        error_result = {
            "workspace_id": workspace_id,
            "display_events": [],
            "triggered_playbook": None,
            "pending_tasks": [],
        }
        return WorkspaceChatResponse(**error_result)
