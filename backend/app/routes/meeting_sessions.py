"""
Meeting session API endpoints.

Provides REST endpoints for managing meeting session lifecycle:
- GET active session
- POST start a new session
- POST end an active session
- GET session history for a workspace
"""

import logging
import uuid
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.app.models.meeting_session import MeetingSession
from backend.app.models.mindscape import EventActor, EventType, MindEvent
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.stores.meeting_session_store import MeetingSessionStore

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/workspaces/{workspace_id}/meeting-sessions",
    tags=["meeting-sessions"],
)


class StartSessionRequest(BaseModel):
    project_id: Optional[str] = None
    thread_id: Optional[str] = None
    meeting_type: str = "general"
    agenda: List[str] = Field(default_factory=list)
    success_criteria: List[str] = Field(default_factory=list)
    max_rounds: Optional[int] = None


class EndSessionRequest(BaseModel):
    state_after: Optional[dict] = None
    minutes_md: Optional[str] = None
    action_items: Optional[List[dict]] = None


class SessionResponse(BaseModel):
    id: str
    workspace_id: str
    project_id: Optional[str] = None
    thread_id: Optional[str] = None
    started_at: str
    ended_at: Optional[str] = None
    is_active: bool
    decisions: list = []
    traces: list = []
    intents_patched: list = []
    status: str = "planned"
    meeting_type: str = "general"
    agenda: list = []
    success_criteria: list = []
    round_count: int = 0
    max_rounds: int = 5
    action_items: list = []
    minutes_md: str = ""
    metadata: dict = {}


def _session_to_response(session: MeetingSession) -> dict:
    d = session.to_dict()
    # Remove state snapshots from list responses for brevity
    d.pop("state_before", None)
    d.pop("state_after", None)
    d.pop("state_diff", None)
    return d


@router.get("/active")
async def get_active_session(
    workspace_id: str,
    project_id: Optional[str] = Query(None),
    thread_id: Optional[str] = Query(None),
):
    """Get the currently active meeting session for a workspace/thread."""
    store = MeetingSessionStore()
    session = store.get_active_session(workspace_id, project_id, thread_id)
    if not session:
        raise HTTPException(status_code=404, detail="No active session found")
    return session.to_dict()


@router.post("/start")
async def start_session(
    workspace_id: str,
    body: StartSessionRequest,
):
    """Start a new meeting session. Ends any existing active session first."""
    store = MeetingSessionStore()

    # End any existing active session
    existing = store.get_active_session(workspace_id, body.project_id, body.thread_id)
    if existing:
        store.end_session(existing.id)
        logger.info(
            f"[MeetingSession] Ended previous session {existing.id} "
            f"before starting new one"
        )

    new_session = MeetingSession.new(
        workspace_id=workspace_id,
        project_id=body.project_id,
        thread_id=body.thread_id,
        meeting_type=body.meeting_type,
        agenda=body.agenda,
        success_criteria=body.success_criteria,
        max_rounds=body.max_rounds or 5,
    )
    new_session.start()
    store.create(new_session)
    logger.info(f"[MeetingSession] Started session {new_session.id}")
    return new_session.to_dict()


@router.post("/{session_id}/end")
async def end_session(
    workspace_id: str,
    session_id: str,
    body: EndSessionRequest,
):
    """End a meeting session and optionally record state_after."""
    store = MeetingSessionStore()
    session = store.get_by_id(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.workspace_id != workspace_id:
        raise HTTPException(status_code=403, detail="Workspace mismatch")
    if not session.is_active:
        raise HTTPException(status_code=409, detail="Session already ended")

    if body.minutes_md is not None:
        session.minutes_md = body.minutes_md
    if body.action_items is not None:
        session.action_items = body.action_items
    if body.minutes_md is not None:
        event_store = MindscapeStore()
        workspace = await event_store.get_workspace(workspace_id)
        profile_id = workspace.owner_user_id if workspace else "default-user"
        minutes_event = MindEvent(
            # Keep ID stable per session while staying within 36-char event ID limit.
            id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{session.id}:minutes")),
            actor=EventActor.ASSISTANT,
            channel="meeting",
            profile_id=profile_id,
            project_id=session.project_id,
            workspace_id=workspace_id,
            thread_id=session.thread_id,
            event_type=EventType.MESSAGE,
            payload={
                "message": body.minutes_md,
                "meeting_session_id": session.id,
                "project_id": session.project_id,
                "is_meeting_minutes": True,
            },
            entity_ids=[],
            metadata={
                "meeting_session_id": session.id,
                "project_id": session.project_id,
            },
        )
        # Keep ID stable per close call to avoid duplicate minutes messages.
        try:
            event_store.create_event(minutes_event)
        except Exception:
            logger.warning(
                "[MeetingSession] Failed to persist minutes message",
                exc_info=True,
            )

    store.update(session)
    ended = store.end_session(session_id, state_after=body.state_after)
    logger.info(f"[MeetingSession] Ended session {session_id}")
    return ended.to_dict()


@router.post("/{session_id}/abort")
async def abort_session(
    workspace_id: str,
    session_id: str,
):
    """Abort an active session."""
    store = MeetingSessionStore()
    session = store.get_by_id(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.workspace_id != workspace_id:
        raise HTTPException(status_code=403, detail="Workspace mismatch")
    if not session.is_active:
        raise HTTPException(status_code=409, detail="Session already ended")

    session.abort(reason="aborted via API")
    store.update(session)
    return session.to_dict()


@router.get("/{session_id}")
async def get_session(workspace_id: str, session_id: str):
    """Get a specific meeting session by ID."""
    store = MeetingSessionStore()
    session = store.get_by_id(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.workspace_id != workspace_id:
        raise HTTPException(status_code=403, detail="Workspace mismatch")
    return session.to_dict()


@router.get("/{session_id}/events")
async def get_session_events(
    workspace_id: str,
    session_id: str,
    limit: int = Query(500, ge=1, le=2000),
):
    """Get replay events bound to a meeting session."""
    session_store = MeetingSessionStore()
    session = session_store.get_by_id(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.workspace_id != workspace_id:
        raise HTTPException(status_code=403, detail="Workspace mismatch")

    store = MindscapeStore()
    events = store.get_events_by_meeting_session(
        meeting_session_id=session_id,
        workspace_id=workspace_id,
        limit=limit,
    )
    return {
        "session_id": session_id,
        "workspace_id": workspace_id,
        "events": [e.model_dump(mode="json") for e in events],
        "total": len(events),
    }


@router.get("")
async def list_sessions(
    workspace_id: str,
    project_id: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List meeting sessions for a workspace (newest first)."""
    store = MeetingSessionStore()
    sessions = store.list_by_workspace(
        workspace_id,
        project_id=project_id,
        limit=limit,
        offset=offset,
    )
    return {
        "sessions": [_session_to_response(s) for s in sessions],
        "total": len(sessions),
        "limit": limit,
        "offset": offset,
    }
