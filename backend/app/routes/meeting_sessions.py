"""
Meeting session API endpoints.

Provides REST endpoints for managing meeting session lifecycle:
- GET active session
- POST start a new session
- POST end an active session
- GET session history for a workspace
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.models.meeting_session import MeetingSession
from app.services.stores.meeting_session_store import MeetingSessionStore

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/workspaces/{workspace_id}/meeting-sessions",
    tags=["meeting-sessions"],
)


class StartSessionRequest(BaseModel):
    thread_id: Optional[str] = None


class EndSessionRequest(BaseModel):
    state_after: Optional[dict] = None


class SessionResponse(BaseModel):
    id: str
    workspace_id: str
    thread_id: Optional[str] = None
    started_at: str
    ended_at: Optional[str] = None
    is_active: bool
    decisions: list = []
    traces: list = []
    intents_patched: list = []
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
    thread_id: Optional[str] = Query(None),
):
    """Get the currently active meeting session for a workspace/thread."""
    store = MeetingSessionStore()
    session = store.get_active_session(workspace_id, thread_id)
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
    existing = store.get_active_session(workspace_id, body.thread_id)
    if existing:
        store.end_session(existing.id)
        logger.info(
            f"[MeetingSession] Ended previous session {existing.id} "
            f"before starting new one"
        )

    new_session = MeetingSession.new(
        workspace_id=workspace_id,
        thread_id=body.thread_id,
    )
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

    ended = store.end_session(session_id, state_after=body.state_after)
    logger.info(f"[MeetingSession] Ended session {session_id}")
    return ended.to_dict()


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


@router.get("")
async def list_sessions(
    workspace_id: str,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List meeting sessions for a workspace (newest first)."""
    store = MeetingSessionStore()
    sessions = store.list_by_workspace(workspace_id, limit=limit, offset=offset)
    return {
        "sessions": [_session_to_response(s) for s in sessions],
        "total": len(sessions),
        "limit": limit,
        "offset": offset,
    }
