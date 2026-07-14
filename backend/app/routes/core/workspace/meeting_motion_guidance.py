"""Workspace-scoped motion practice guidance WebSocket."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from backend.app.models.meeting_motion_guidance import (
    MeetingMotionGuidanceClientMessage,
    MeetingMotionGuidanceEvent,
)
from backend.app.models.workspace import Workspace
from backend.app.routes.workspace_dependencies import get_workspace
from backend.app.services.orchestration.meeting.motion_guidance_service import (
    MeetingMotionGuidanceService,
    MotionGuidanceError,
    MotionGuidanceSession,
)

router = APIRouter()
GuidanceSessionKey = tuple[str, str, str]
_GUIDANCE_CONNECTIONS: dict[GuidanceSessionKey, set[WebSocket]] = {}


def get_motion_guidance_service() -> MeetingMotionGuidanceService:
    """Return the bounded motion guidance service."""

    return MeetingMotionGuidanceService()


async def _send_event(websocket: WebSocket, event: MeetingMotionGuidanceEvent) -> None:
    await websocket.send_text(json.dumps(event.model_dump(mode="json", exclude_none=True)))


def _session_key(session: MotionGuidanceSession) -> GuidanceSessionKey:
    return (session.workspace_id, session.meeting_id, session.practice_session_id)


def _register_connection(session: MotionGuidanceSession, websocket: WebSocket) -> None:
    _GUIDANCE_CONNECTIONS.setdefault(_session_key(session), set()).add(websocket)


def _unregister_connection(session: MotionGuidanceSession, websocket: WebSocket) -> None:
    key = _session_key(session)
    peers = _GUIDANCE_CONNECTIONS.get(key)
    if not peers:
        return
    peers.discard(websocket)
    if not peers:
        _GUIDANCE_CONNECTIONS.pop(key, None)


def _should_broadcast_event(event: MeetingMotionGuidanceEvent) -> bool:
    return event.type in {"guidance_cue", "guidance_suppressed", "interrupted"}


async def _broadcast_event(
    session: MotionGuidanceSession,
    event: MeetingMotionGuidanceEvent,
) -> None:
    peers = list(_GUIDANCE_CONNECTIONS.get(_session_key(session), set()))
    stale: list[WebSocket] = []
    for peer in peers:
        try:
            await _send_event(peer, event)
        except Exception:
            stale.append(peer)
    for peer in stale:
        _unregister_connection(session, peer)


def _error_event(
    *,
    session: MotionGuidanceSession,
    reason: str,
    message: str,
    recoverable: bool,
) -> MeetingMotionGuidanceEvent:
    return MeetingMotionGuidanceEvent(
        type="session_error",
        workspace_id=session.workspace_id,
        meeting_id=session.meeting_id,
        practice_session_id=session.practice_session_id,
        state=session.state,
        reason=reason,
        message=message,
        recoverable=recoverable,
    )


@router.websocket(
    "/{workspace_id}/meetings/{meeting_id}/motion-guidance/{practice_session_id}/stream"
)
async def stream_motion_practice_guidance(
    websocket: WebSocket,
    workspace_id: str,
    meeting_id: str,
    practice_session_id: str,
    workspace: Workspace = Depends(get_workspace),
    service: MeetingMotionGuidanceService = Depends(get_motion_guidance_service),
) -> None:
    """Run one bounded motion guidance session over a single WebSocket."""

    _ = workspace
    await websocket.accept()
    session = MotionGuidanceSession(
        workspace_id=workspace_id,
        meeting_id=meeting_id,
        practice_session_id=practice_session_id,
    )
    _register_connection(session, websocket)
    close_sent = False
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                payload: Any = json.loads(raw)
                message = MeetingMotionGuidanceClientMessage.model_validate(payload)
            except json.JSONDecodeError:
                await _send_event(
                    websocket,
                    _error_event(
                        session=session,
                        reason="invalid_json",
                        message="Motion guidance messages must be JSON.",
                        recoverable=True,
                    ),
                )
                continue
            except ValidationError as exc:
                await _send_event(
                    websocket,
                    _error_event(
                        session=session,
                        reason="invalid_message",
                        message=str(exc.errors()[0].get("msg") or "Invalid message."),
                        recoverable=True,
                    ),
                )
                continue

            try:
                event = service.handle_message(session=session, message=message)
            except MotionGuidanceError as exc:
                await _send_event(
                    websocket,
                    _error_event(
                        session=session,
                        reason=exc.reason,
                        message=exc.message,
                        recoverable=exc.recoverable,
                    ),
                )
                if not exc.recoverable:
                    close_sent = True
                    await websocket.close(code=4400, reason=exc.reason)
                    break
                continue

            if event is None:
                continue
            if _should_broadcast_event(event):
                await _broadcast_event(session, event)
            else:
                await _send_event(websocket, event)
            if event.type == "session_closed":
                close_sent = True
                await websocket.close(code=1000, reason="session_closed")
                break
    except WebSocketDisconnect:
        pass
    finally:
        session.state = "closed"
        _unregister_connection(session, websocket)
        if not close_sent:
            try:
                await websocket.close()
            except Exception:
                pass


__all__ = [
    "get_motion_guidance_service",
    "router",
    "stream_motion_practice_guidance",
]
