"""Workspace-scoped Meeting Workbench command ledger API."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Path, Query

from backend.app.models.meeting_command import (
    MeetingCommandAcceptResponse,
    MeetingCommandEnvelope,
    MeetingCommandListResponse,
)
from backend.app.models.workspace import Workspace
from backend.app.routes.workspace_dependencies import get_orchestrator, get_store, get_workspace
from backend.app.services.conversation_orchestrator import ConversationOrchestrator
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.orchestration.meeting.meeting_command_submission import (
    MeetingCommandSubmissionError,
    MeetingCommandSubmissionService,
    get_meeting_command_store,
    validate_meeting_session,
)

router = APIRouter()


@router.post(
    "/{workspace_id}/meetings/{meeting_id}/commands",
    response_model=MeetingCommandAcceptResponse,
)
async def submit_meeting_command(
    envelope: MeetingCommandEnvelope,
    workspace_id: str = Path(..., description="Workspace ID"),
    meeting_id: str = Path(..., description="Meeting/session ID"),
    workspace: Workspace = Depends(get_workspace),
    orchestrator: ConversationOrchestrator = Depends(get_orchestrator),
    mindscape_store: MindscapeStore = Depends(get_store),
    background_tasks: BackgroundTasks = None,
) -> MeetingCommandAcceptResponse:
    """Persist a server-canonical command envelope as a ledger row."""

    service = MeetingCommandSubmissionService()
    try:
        return await service.submit_envelope(
            envelope=envelope,
            workspace_id=workspace_id,
            meeting_id=meeting_id,
            workspace=workspace,
            orchestrator=orchestrator,
            mindscape_store=mindscape_store,
            background_tasks=background_tasks,
        )
    except MeetingCommandSubmissionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.get(
    "/{workspace_id}/meetings/{meeting_id}/commands",
    response_model=MeetingCommandListResponse,
)
async def list_meeting_commands(
    workspace_id: str = Path(..., description="Workspace ID"),
    meeting_id: str = Path(..., description="Meeting/session ID"),
    limit: int = Query(100, ge=1, le=500),
) -> MeetingCommandListResponse:
    """Read the command ledger for one meeting session."""

    try:
        validate_meeting_session(workspace_id=workspace_id, meeting_id=meeting_id)
    except MeetingCommandSubmissionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    commands = get_meeting_command_store().list_by_meeting(
        workspace_id=workspace_id,
        meeting_id=meeting_id,
        limit=limit,
    )
    return MeetingCommandListResponse(
        workspace_id=workspace_id,
        meeting_id=meeting_id,
        commands=commands,
    )
