"""Workspace-scoped WebRTC media signaling routes."""

from __future__ import annotations

import json
from typing import Any, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Path, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from backend.app.models.media_transport import (
    CreateLiveMediaSessionRequest,
    LiveMediaSessionAccess,
    LiveMediaSessionDescriptor,
    MediaSignalEvent,
    MediaSignalMessage,
    MediaSignalParticipant,
)
from backend.app.models.device_binding import DeviceControlEvent, DeviceSessionEntry
from backend.app.models.workspace import Workspace
from backend.app.routes.workspace_dependencies import get_workspace
from backend.app.services.orchestration.meeting.device_binding_registry import (
    DeviceBindingRegistry,
    DeviceBindingRegistryError,
    get_device_binding_registry,
)
from backend.app.services.media_transport import (
    LiveMediaSessionService,
    LiveMediaSessionServiceError,
    get_live_media_session_service,
)
from backend.app.services.orchestration.meeting.webrtc_signaling_registry import (
    MAX_WEBRTC_SIGNAL_MESSAGE_BYTES,
    WebRTCSignalingRegistry,
    WebRTCSignalingRegistryError,
    get_webrtc_signaling_registry,
)

router = APIRouter()


def get_live_media_session_route_service() -> LiveMediaSessionService:
    try:
        return get_live_media_session_service()
    except LiveMediaSessionServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.reason) from exc


def _require_device_session(
    *,
    registry: DeviceBindingRegistry,
    workspace_id: str,
    device_session_id: str,
) -> DeviceSessionEntry:
    entry = registry.get_active_session(
        workspace_id=workspace_id,
        session_id=device_session_id,
    )
    if entry is None:
        raise HTTPException(status_code=404, detail="unknown_device_session")
    return entry


async def _broadcast_device_snapshot(
    *,
    registry: DeviceBindingRegistry,
    workspace_id: str,
) -> None:
    event = DeviceControlEvent(
        type="session_active",
        workspace_id=workspace_id,
        state="active",
        active_sessions=registry.list_active_sessions(workspace_id=workspace_id),
    )
    payload = json.dumps(event.model_dump(mode="json", exclude_none=True))
    stale: list[WebSocket] = []
    for observer in registry.workspace_session_observers(workspace_id=workspace_id):
        try:
            await observer.send_text(payload)
        except RuntimeError:
            stale.append(observer)
    for observer in stale:
        registry.detach_workspace_session_observer(
            workspace_id=workspace_id,
            websocket=observer,
        )


def _raise_live_media_error(exc: LiveMediaSessionServiceError) -> NoReturn:
    raise HTTPException(status_code=exc.status_code, detail=exc.reason) from exc


@router.post(
    "/{workspace_id}/device-bindings/{device_session_id}/media-sessions",
    response_model=LiveMediaSessionAccess,
)
async def create_live_media_session(
    payload: CreateLiveMediaSessionRequest,
    workspace_id: str = Path(..., description="Workspace ID"),
    device_session_id: str = Path(..., description="Bound source device session ID"),
    workspace: Workspace = Depends(get_workspace),
    device_registry: DeviceBindingRegistry = Depends(get_device_binding_registry),
    media_service: LiveMediaSessionService = Depends(get_live_media_session_route_service),
) -> LiveMediaSessionAccess:
    """Create or read back the one authorized media path for a bound device."""

    _ = workspace
    device_session = _require_device_session(
        registry=device_registry,
        workspace_id=workspace_id,
        device_session_id=device_session_id,
    )
    try:
        access = media_service.create(device_session=device_session, request=payload)
        device_registry.attach_live_media_session(
            workspace_id=workspace_id,
            session_id=device_session_id,
            media_session_id=access.session.media_session_id,
            media_session_state=access.session.state,
            media_session_expires_at_epoch=access.session.expires_at_epoch,
        )
    except LiveMediaSessionServiceError as exc:
        _raise_live_media_error(exc)
    except DeviceBindingRegistryError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.reason) from exc
    await _broadcast_device_snapshot(
        registry=device_registry,
        workspace_id=workspace_id,
    )
    return access


@router.get(
    "/{workspace_id}/device-bindings/{device_session_id}/media-sessions",
    response_model=LiveMediaSessionDescriptor,
)
async def get_live_media_session(
    workspace_id: str = Path(..., description="Workspace ID"),
    device_session_id: str = Path(..., description="Bound source device session ID"),
    workspace: Workspace = Depends(get_workspace),
    device_registry: DeviceBindingRegistry = Depends(get_device_binding_registry),
    media_service: LiveMediaSessionService = Depends(get_live_media_session_route_service),
) -> LiveMediaSessionDescriptor:
    """Read credential-free state for the active device media path."""

    _ = workspace
    _require_device_session(
        registry=device_registry,
        workspace_id=workspace_id,
        device_session_id=device_session_id,
    )
    try:
        return media_service.get_active(
            workspace_id=workspace_id,
            device_session_id=device_session_id,
        )
    except LiveMediaSessionServiceError as exc:
        _raise_live_media_error(exc)


@router.post(
    "/{workspace_id}/device-bindings/{device_session_id}/media-sessions/"
    "{media_session_id}/refresh",
    response_model=LiveMediaSessionAccess,
)
async def refresh_live_media_session_access(
    workspace_id: str = Path(..., description="Workspace ID"),
    device_session_id: str = Path(..., description="Bound source device session ID"),
    media_session_id: str = Path(..., description="Live media session ID"),
    workspace: Workspace = Depends(get_workspace),
    device_registry: DeviceBindingRegistry = Depends(get_device_binding_registry),
    media_service: LiveMediaSessionService = Depends(get_live_media_session_route_service),
) -> LiveMediaSessionAccess:
    """Explicitly refresh exact-path credentials without extending session expiry."""

    _ = workspace
    _require_device_session(
        registry=device_registry,
        workspace_id=workspace_id,
        device_session_id=device_session_id,
    )
    try:
        return media_service.refresh_access(
            workspace_id=workspace_id,
            device_session_id=device_session_id,
            media_session_id=media_session_id,
        )
    except LiveMediaSessionServiceError as exc:
        _raise_live_media_error(exc)


@router.post(
    "/{workspace_id}/device-bindings/{device_session_id}/media-sessions/"
    "{media_session_id}/stop",
    response_model=LiveMediaSessionDescriptor,
)
async def stop_live_media_session(
    workspace_id: str = Path(..., description="Workspace ID"),
    device_session_id: str = Path(..., description="Bound source device session ID"),
    media_session_id: str = Path(..., description="Live media session ID"),
    workspace: Workspace = Depends(get_workspace),
    device_registry: DeviceBindingRegistry = Depends(get_device_binding_registry),
    media_service: LiveMediaSessionService = Depends(get_live_media_session_route_service),
) -> LiveMediaSessionDescriptor:
    """Stop one live media session without affecting the device control socket."""

    _ = workspace
    _require_device_session(
        registry=device_registry,
        workspace_id=workspace_id,
        device_session_id=device_session_id,
    )
    try:
        descriptor = media_service.stop(
            workspace_id=workspace_id,
            device_session_id=device_session_id,
            media_session_id=media_session_id,
        )
        device_registry.detach_live_media_session(
            workspace_id=workspace_id,
            session_id=device_session_id,
            media_session_id=media_session_id,
        )
    except LiveMediaSessionServiceError as exc:
        _raise_live_media_error(exc)
    except DeviceBindingRegistryError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.reason) from exc
    await _broadcast_device_snapshot(
        registry=device_registry,
        workspace_id=workspace_id,
    )
    return descriptor


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
        joined_event, pending_events, peer_websocket, replaced_websocket = signaling_registry.attach_participant(
            workspace_id=workspace_id,
            device_session_id=device_session_id,
            media_session_id=media_session_id,
            participant=participant,
            websocket=websocket,
            device_binding_registry=device_registry,
        )
        if replaced_websocket is not None:
            try:
                await _send_event(
                    replaced_websocket,
                    MediaSignalEvent(
                        type="session_error",
                        workspace_id=workspace_id,
                        device_session_id=device_session_id,
                        media_session_id=media_session_id,
                        reason="participant_replaced",
                        message="A newer media signaling participant replaced this connection.",
                        recoverable=True,
                        created_at_epoch=0,
                    ),
                )
                await replaced_websocket.close(code=1000, reason="participant_replaced")
            except RuntimeError:
                pass
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
            if not signaling_registry.is_active_participant(
                workspace_id=workspace_id,
                device_session_id=device_session_id,
                media_session_id=media_session_id,
                participant=participant,
                websocket=websocket,
            ):
                await websocket.close(code=1000, reason="participant_replaced")
                return
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
