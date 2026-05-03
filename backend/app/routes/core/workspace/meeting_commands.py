"""Workspace-scoped Meeting Workbench command ledger API."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Path, Query

from backend.app.models.meeting_command import (
    MeetingCommandAcceptResponse,
    MeetingCommandEnvelope,
    MeetingCommandListResponse,
    MeetingCommandRecord,
    MeetingCommandStatus,
)
from backend.app.models.workspace import Workspace
from backend.app.routes.workspace_dependencies import get_orchestrator, get_store, get_workspace
from backend.app.services.conversation_orchestrator import ConversationOrchestrator
from backend.app.services.meeting_command_dispatch import (
    dispatch_chat_for_command as _dispatch_chat_for_command,
    dispatch_meeting_orchestration_for_command as _dispatch_meeting_orchestration_for_command,
    dispatch_object_action_for_command as _dispatch_object_action_for_command,
    dispatch_playbook_for_command as _dispatch_playbook_for_command,
    should_route_chat as _should_route_chat,
    should_route_meeting_orchestration as _should_route_meeting_orchestration,
    should_route_object_action as _should_route_object_action,
    should_route_playbook as _should_route_playbook,
)
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.meeting_command_parser import (
    MeetingCommandNormalizationError,
    canonicalize_meeting_command_envelope,
)
from backend.app.services.stores.meeting_command_store import MeetingCommandStore
from backend.app.services.stores.meeting_session_store import MeetingSessionStore

router = APIRouter()

_meeting_command_store: MeetingCommandStore | None = None
_meeting_session_store: MeetingSessionStore | None = None


def _get_meeting_command_store() -> MeetingCommandStore:
    global _meeting_command_store
    if _meeting_command_store is None:
        _meeting_command_store = MeetingCommandStore()
    return _meeting_command_store


def _get_meeting_session_store() -> MeetingSessionStore:
    global _meeting_session_store
    if _meeting_session_store is None:
        _meeting_session_store = MeetingSessionStore()
    return _meeting_session_store


def _detail(code: str, message: str, **extra):
    return {"code": code, "message": message, **extra}


def _validate_path_identity(
    envelope: MeetingCommandEnvelope,
    *,
    workspace_id: str,
    meeting_id: str,
) -> None:
    if envelope.workspace_id and envelope.workspace_id != workspace_id:
        raise HTTPException(
            status_code=400,
            detail=_detail(
                "workspace_mismatch",
                "Command envelope workspace_id must match the route workspace_id.",
            ),
        )
    if envelope.meeting_id != meeting_id:
        raise HTTPException(
            status_code=400,
            detail=_detail(
                "meeting_mismatch",
                "Command envelope meeting_id must match the route meeting_id.",
            ),
        )


def _validate_meeting_session(*, workspace_id: str, meeting_id: str):
    session = _get_meeting_session_store().get_by_id(meeting_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail=_detail(
                "meeting_session_not_found",
                f"Meeting session '{meeting_id}' was not found.",
            ),
        )
    if session.workspace_id != workspace_id:
        raise HTTPException(
            status_code=404,
            detail=_detail(
                "meeting_session_not_found",
                f"Meeting session '{meeting_id}' was not found in workspace '{workspace_id}'.",
            ),
        )
    return session


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

    _validate_path_identity(envelope, workspace_id=workspace_id, meeting_id=meeting_id)
    session = _validate_meeting_session(workspace_id=workspace_id, meeting_id=meeting_id)
    try:
        canonical = canonicalize_meeting_command_envelope(
            envelope,
            workspace_id=workspace_id,
            meeting_id=meeting_id,
        )
    except MeetingCommandNormalizationError as exc:
        raise HTTPException(
            status_code=422,
            detail=_detail(
                "invalid_command_reference",
                "Meeting command contains invalid object references.",
                errors=[error.model_dump(exclude_none=True) for error in exc.errors],
            ),
        ) from exc

    now = datetime.now(timezone.utc)
    command_id = canonical.command_id or f"cmd_{uuid.uuid4().hex}"
    command = MeetingCommandRecord(
        command_id=command_id,
        workspace_id=workspace_id,
        meeting_id=meeting_id,
        thread_id=canonical.thread_id or session.thread_id or meeting_id,
        client_draft_id=canonical.client_draft_id,
        origin_surface=canonical.origin_surface,
        actor=canonical.actor,
        intent_text=canonical.intent_text,
        context_objects=canonical.context_objects,
        requested_action=canonical.requested_action,
        expected_outputs=canonical.expected_outputs,
        write_mode=canonical.write_mode,
        status=MeetingCommandStatus.ACCEPTED,
        metadata={
            **canonical.metadata,
            "meeting_mentions": canonical.meeting_mentions,
            "dispatch_status": "pending_runtime_integration",
        },
        created_at=now,
        updated_at=now,
    )
    command_store = _get_meeting_command_store()
    saved = command_store.save(command)
    dispatch_result = None
    session_store = _get_meeting_session_store()
    if _should_route_meeting_orchestration(canonical):
        try:
            command, dispatch_result = await _dispatch_meeting_orchestration_for_command(
                command=saved,
                canonical=canonical,
                session=session,
                workspace=workspace,
                store=mindscape_store,
                session_store=session_store,
                workspace_id=workspace_id,
            )
        except Exception as exc:
            command = saved.model_copy(
                update={
                    "status": MeetingCommandStatus.FAILED,
                    "metadata": {
                        **saved.metadata,
                        "dispatch_status": "failed",
                        "dispatch_error": str(exc),
                    },
                }
            )
            saved = command_store.save(command)
            raise
        saved = command_store.save(command)
    elif _should_route_object_action(canonical):
        try:
            command, dispatch_result = await _dispatch_object_action_for_command(
                command=saved,
                canonical=canonical,
                workspace_id=workspace_id,
                meeting_id=meeting_id,
            )
        except Exception as exc:
            command = saved.model_copy(
                update={
                    "status": MeetingCommandStatus.FAILED,
                    "metadata": {
                        **saved.metadata,
                        "dispatch_status": "failed",
                        "dispatch_error": str(exc),
                    },
                }
            )
            saved = command_store.save(command)
            raise
        saved = command_store.save(command)
    elif _should_route_playbook(canonical):
        try:
            command, dispatch_result = await _dispatch_playbook_for_command(
                command=saved,
                canonical=canonical,
                workspace=workspace,
                orchestrator=orchestrator,
                meeting_id=meeting_id,
            )
        except Exception as exc:
            command = saved.model_copy(
                update={
                    "status": MeetingCommandStatus.FAILED,
                    "metadata": {
                        **saved.metadata,
                        "dispatch_status": "failed",
                        "dispatch_error": str(exc),
                    },
                }
            )
            saved = command_store.save(command)
            raise
        saved = command_store.save(command)
    elif _should_route_chat(canonical):
        try:
            command, dispatch_result = await _dispatch_chat_for_command(
                command=saved,
                canonical=canonical,
                workspace=workspace,
                orchestrator=orchestrator,
                meeting_id=meeting_id,
                background_tasks=background_tasks,
            )
        except Exception as exc:
            command = saved.model_copy(
                update={
                    "status": MeetingCommandStatus.FAILED,
                    "metadata": {
                        **saved.metadata,
                        "dispatch_status": "failed",
                        "dispatch_error": str(exc),
                    },
                }
            )
            saved = command_store.save(command)
            raise
        saved = command_store.save(command)
    return MeetingCommandAcceptResponse(
        workspace_id=workspace_id,
        meeting_id=meeting_id,
        command_id=saved.command_id,
        status=saved.status,
        command=saved,
        dispatch_result=dispatch_result,
    )


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

    _validate_meeting_session(workspace_id=workspace_id, meeting_id=meeting_id)
    commands = _get_meeting_command_store().list_by_meeting(
        workspace_id=workspace_id,
        meeting_id=meeting_id,
        limit=limit,
    )
    return MeetingCommandListResponse(
        workspace_id=workspace_id,
        meeting_id=meeting_id,
        commands=commands,
    )
