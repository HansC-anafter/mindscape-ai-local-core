"""Workspace-scoped Meeting Engine voice turn API."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Path

from backend.app.models.meeting_voice import (
    MeetingVoiceTurnRequest,
    MeetingVoiceTurnResponse,
)
from backend.app.models.workspace import Workspace
from backend.app.routes.workspace_dependencies import get_orchestrator, get_store, get_workspace
from backend.app.services.conversation_orchestrator import ConversationOrchestrator
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.orchestration.meeting.meeting_command_submission import (
    MeetingCommandSubmissionError,
)
from backend.app.services.orchestration.meeting.voice_ingress import (
    MeetingVoiceIngressError,
    MeetingVoiceIngressService,
)

router = APIRouter()


@router.post(
    "/{workspace_id}/meetings/{meeting_id}/voice-turns",
    response_model=MeetingVoiceTurnResponse,
)
async def submit_meeting_voice_turn(
    payload: MeetingVoiceTurnRequest,
    workspace_id: str = Path(..., description="Workspace ID"),
    meeting_id: str = Path(..., description="Meeting/session ID"),
    workspace: Workspace = Depends(get_workspace),
    orchestrator: ConversationOrchestrator = Depends(get_orchestrator),
    mindscape_store: MindscapeStore = Depends(get_store),
    background_tasks: BackgroundTasks = None,
) -> MeetingVoiceTurnResponse:
    """Transcribe one bounded voice turn and submit one command when non-empty."""

    service = MeetingVoiceIngressService()
    try:
        return await service.submit_voice_turn(
            request=payload,
            workspace_id=workspace_id,
            meeting_id=meeting_id,
            workspace=workspace,
            orchestrator=orchestrator,
            mindscape_store=mindscape_store,
            background_tasks=background_tasks,
        )
    except MeetingVoiceIngressError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except MeetingCommandSubmissionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
