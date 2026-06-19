"""Workspace-scoped WebRTC media signaling routes."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, Path, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from backend.app.models.media_transport import (
    MediaSignalEvent,
    MediaSignalMessage,
    MediaSignalParticipant,
)
from backend.app.models.workspace import Workspace
from backend.app.routes.workspace_dependencies import get_workspace
from backend.app.services.orchestration.meeting.device_binding_registry import (
    DeviceBindingRegistry,
    get_device_binding_registry,
)
from backend.app.services.orchestration.meeting.webrtc_signaling_registry import (
    MAX_WEBRTC_SIGNAL_MESSAGE_BYTES,
    WebRTCSignalingRegistry,
    WebRTCSignalingRegistryError,
    get_webrtc_signaling_registry,
)

router = APIRouter()


async def _send_event(websocket: WebSocket, event: MediaSignalEvent) -> None:
    await websocket.send_text(json.dumps(event.model_dump(mode="json", exclude_none=True)))


@router.websocket(
    "/{workspace_id}/device-bindings/{device_session_id}/media-sessions/{media_session_id}/signal"
)
async def signal_device_media_session(
    websocket: WebSocket,
    workspace_id: str = Path(..., description="Workspace ID"),
    device_session_id: str = Path(..., description="Bound source device session ID"),
    media_session_id: str = Path(..., description="WebRTC media session ID"),
    workspace: Workspace = Depends(get_workspace),
    device_registry: DeviceBindingRegistry = Depends(get_device_binding_registry),
    signaling_registry: WebRTCSignalingRegistry = Depends(get_webrtc_signaling_registry),
) -> None:
    """Run LAN-only WebRTC signaling between a workspace and one source device."""

    _ = workspace
    await websocket.accept()
    participant: MediaSignalParticipant | None = None

    try:
        first_message = await _receive_signal_message(websocket)
        participant = _participant_from_join(first_message)
        joined_event, pending_events, peer_websocket = signaling_registry.attach_participant(
            workspace_id=workspace_id,
            device_session_id=device_session_id,
            media_session_id=media_session_id,
            participant=participant,
            websocket=websocket,
            device_binding_registry=device_registry,
        )
        await _send_event(websocket, joined_event)
        for pending_event in pending_events:
            await _send_event(websocket, pending_event)
        if peer_websocket is not None:
            await _send_event(peer_websocket, joined_event)

        while True:
            message = await _receive_signal_message(websocket)
            if message.type in {"workspace_join", "source_join"}:
                raise WebRTCSignalingRegistryError(
                    reason="duplicate_join",
                    message="The media signaling participant already joined this session.",
                )
            peer_websocket, event = signaling_registry.forward_or_queue(
                workspace_id=workspace_id,
                device_session_id=device_session_id,
                media_session_id=media_session_id,
                sender=participant,
                message=message,
            )
            if peer_websocket is not None:
                await _send_event(peer_websocket, event)
            if message.type == "close":
                await websocket.close(code=1000)
                return
    except WebRTCSignalingRegistryError as exc:
        await _send_event(
            websocket,
            MediaSignalEvent(
                type="session_error",
                workspace_id=workspace_id,
                device_session_id=device_session_id,
                media_session_id=media_session_id,
                reason=exc.reason,
                message=exc.message,
                recoverable=False,
                created_at_epoch=0,
            ),
        )
        await websocket.close(code=exc.close_code, reason=exc.reason)
    except WebSocketDisconnect:
        pass
    finally:
        if participant is not None:
            signaling_registry.detach_participant(
                workspace_id=workspace_id,
                device_session_id=device_session_id,
                media_session_id=media_session_id,
                participant=participant,
                websocket=websocket,
            )


async def _receive_signal_message(websocket: WebSocket) -> MediaSignalMessage:
    raw = await websocket.receive_text()
    if len(raw.encode("utf-8")) > MAX_WEBRTC_SIGNAL_MESSAGE_BYTES:
        raise WebRTCSignalingRegistryError(
            reason="signal_message_too_large",
            message="Media signaling messages must not exceed 64 KiB.",
            status_code=413,
            close_code=4409,
        )
    try:
        payload: Any = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise WebRTCSignalingRegistryError(
            reason="invalid_json",
            message="Media signaling messages must be JSON.",
        ) from exc
    try:
        return MediaSignalMessage.model_validate(payload)
    except ValidationError as exc:
        first_error = exc.errors()[0]
        reason = "raw_media_payload_not_allowed" if first_error.get("type") == "value_error" else "invalid_message"
        raise WebRTCSignalingRegistryError(
            reason=reason,
            message=str(first_error.get("msg") or "Invalid media signaling message."),
        ) from exc


def _participant_from_join(message: MediaSignalMessage) -> MediaSignalParticipant:
    if message.type == "workspace_join":
        return "workspace"
    if message.type == "source_join":
        return "source"
    raise WebRTCSignalingRegistryError(
        reason="join_required",
        message="The first media signaling message must join as workspace or source.",
    )
