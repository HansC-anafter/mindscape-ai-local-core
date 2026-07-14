"""Workspace-scoped WebRTC media signaling routes."""

from __future__ import annotations

import json
from typing import Any, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Path, WebSocket

from backend.app.models.media_transport import (
    CreateLiveMediaSessionRequest,
    LiveMediaSessionAccess,
    LiveMediaSessionDescriptor,
    MediaSignalEvent,
    StartLiveMediaReceiverRequest,
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
from backend.app.services.media_transport.live_media_receiver_service import (
    LiveMediaReceiverControlError,
    start_live_media_receiver,
    terminate_live_media_session,
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
    "{media_session_id}/receiver/start",
)
async def start_live_media_session_receiver(
    payload: StartLiveMediaReceiverRequest,
    workspace_id: str = Path(..., description="Workspace ID"),
    device_session_id: str = Path(..., description="Bound source device session ID"),
    media_session_id: str = Path(..., description="Live media session ID"),
    workspace: Workspace = Depends(get_workspace),
    device_registry: DeviceBindingRegistry = Depends(get_device_binding_registry),
    media_service: LiveMediaSessionService = Depends(get_live_media_session_route_service),
) -> dict[str, Any]:
    """Start the one host receiver without returning its credentials."""

    _ = workspace
    _require_device_session(
        registry=device_registry,
        workspace_id=workspace_id,
        device_session_id=device_session_id,
    )
    try:
        return await start_live_media_receiver(
            media_service=media_service,
            workspace_id=workspace_id,
            device_session_id=device_session_id,
            media_session_id=media_session_id,
            request=payload,
        )
    except LiveMediaReceiverControlError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.reason) from exc


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
        descriptor = await terminate_live_media_session(
            media_service=media_service,
            workspace_id=workspace_id,
            device_session_id=device_session_id,
            media_session_id=media_session_id,
            reason="stopped_by_client",
        )
        device_registry.detach_live_media_session(
            workspace_id=workspace_id,
            session_id=device_session_id,
            media_session_id=media_session_id,
        )
    except LiveMediaSessionServiceError as exc:
        _raise_live_media_error(exc)
    except LiveMediaReceiverControlError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.reason) from exc
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
) -> None:
    """Retain the legacy signaling URL without a second media execution path."""

    _ = workspace
    await websocket.accept()
    await _send_event(
        websocket,
        MediaSignalEvent(
            type="session_error",
            workspace_id=workspace_id,
            device_session_id=device_session_id,
            media_session_id=media_session_id,
            reason="legacy_media_signaling_retired",
            message="Create a live media session and use its WHIP/WHEP endpoints.",
            recoverable=False,
            created_at_epoch=0,
        ),
    )
    await websocket.close(code=4401, reason="legacy_media_signaling_retired")
