"""Workspace-scoped device binding and control WebSocket routes."""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from backend.app.models.device_binding import (
    DeviceCapabilityDeclaration,
    DeviceControlEvent,
    DeviceControlMessage,
    DevicePairingCode,
    DeviceSessionEntry,
)
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
    terminate_live_media_session,
)
from backend.app.services.orchestration.meeting.device_binding_events import (
    broadcast_to_source_devices as _broadcast_to_source_devices,
    broadcast_to_workspace_observers as _broadcast_to_workspace_observers,
    broadcast_workspace_session_observers as _broadcast_workspace_session_observers,
    build_entry_event as _entry_event,
    build_error_event as _error_event,
    send_device_control_event as _send_event,
)

router = APIRouter()
logger = logging.getLogger(__name__)


def get_device_binding_live_media_service() -> LiveMediaSessionService | None:
    """Resolve media lifecycle support only when the formal lane is configured."""

    try:
        return get_live_media_session_service()
    except LiveMediaSessionServiceError:
        return None


async def _stop_attached_live_media_session(
    entry: DeviceSessionEntry,
    media_service: LiveMediaSessionService | None,
) -> None:
    if media_service is None or not entry.media_session_id:
        return
    try:
        await terminate_live_media_session(
            media_service=media_service,
            workspace_id=entry.workspace_id,
            device_session_id=entry.session_id,
            media_session_id=entry.media_session_id,
            reason=entry.terminal_reason or "device_session_closed",
        )
    except LiveMediaSessionServiceError as exc:
        if exc.reason != "live_media_session_not_found":
            raise


class CreateDevicePairingCodeRequest(BaseModel):
    """Request body for issuing a workspace device pairing code."""

    model_config = ConfigDict(extra="forbid")

    label: str | None = None
    expires_in_seconds: int | None = Field(default=None, ge=1, le=600)


@router.post(
    "/{workspace_id}/device-bindings/pairing-codes",
    response_model=DevicePairingCode,
)
async def create_device_pairing_code(
    payload: CreateDevicePairingCodeRequest | None = None,
    workspace_id: str = Path(..., description="Workspace ID"),
    workspace: Workspace = Depends(get_workspace),
    registry: DeviceBindingRegistry = Depends(get_device_binding_registry),
) -> DevicePairingCode:
    """Issue one short-lived device pairing code for this workspace."""

    _ = workspace
    return registry.create_pairing_code(
        workspace_id=workspace_id,
        ttl_seconds=payload.expires_in_seconds if payload is not None else None,
    )


@router.get(
    "/{workspace_id}/device-bindings/sessions",
    response_model=list[DeviceSessionEntry],
)
async def list_device_binding_sessions(
    workspace_id: str = Path(..., description="Workspace ID"),
    workspace: Workspace = Depends(get_workspace),
    registry: DeviceBindingRegistry = Depends(get_device_binding_registry),
) -> list[DeviceSessionEntry]:
    """Return active source device sessions for workspace hydration."""

    _ = workspace
    return registry.list_active_sessions(workspace_id=workspace_id)


@router.post(
    "/{workspace_id}/device-bindings/{session_id}/revoke",
    response_model=DeviceControlEvent,
)
async def revoke_device_binding_session(
    workspace_id: str = Path(..., description="Workspace ID"),
    session_id: str = Path(..., description="Device session ID"),
    workspace: Workspace = Depends(get_workspace),
    registry: DeviceBindingRegistry = Depends(get_device_binding_registry),
    media_service: LiveMediaSessionService | None = Depends(
        get_device_binding_live_media_service
    ),
) -> DeviceControlEvent:
    """Revoke one active device binding session."""

    _ = workspace
    try:
        entry = registry.get_active_session(
            workspace_id=workspace_id,
            session_id=session_id,
        )
        if entry is None:
            registry.revoke_session(
                workspace_id=workspace_id,
                session_id=session_id,
            )
            raise AssertionError("unreachable")
        entry.terminal_reason = "revoked_by_workspace"
        await _stop_attached_live_media_session(entry, media_service)
        entry = registry.revoke_session(
            workspace_id=workspace_id,
            session_id=session_id,
        )
    except DeviceBindingRegistryError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.reason) from exc
    except LiveMediaReceiverControlError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.reason) from exc

    event = _entry_event(
        event_type="session_revoked",
        entry=entry,
        active_sessions=registry.list_active_sessions(workspace_id=workspace_id),
        reason=entry.terminal_reason,
        recoverable=False,
    )
    if entry.websocket is not None:
        try:
            await _send_event(entry.websocket, event)
        except RuntimeError:
            pass
    await _broadcast_to_workspace_observers(
        registry=registry,
        pairing_code=entry.pairing_code,
        event=event,
    )
    return event


@router.websocket("/{workspace_id}/device-bindings/control")
async def control_workspace_device_sessions(
    websocket: WebSocket,
    workspace_id: str,
    workspace: Workspace = Depends(get_workspace),
    registry: DeviceBindingRegistry = Depends(get_device_binding_registry),
) -> None:
    """Observe all active device sessions for one workspace without polling."""

    _ = workspace
    await websocket.accept()
    attached = False
    try:
        message = await _receive_control_message(websocket)
        if message.type != "workspace_subscribe":
            await _send_event(
                websocket,
                _error_event(
                    workspace_id=workspace_id,
                    pairing_code="",
                    reason="workspace_subscribe_required",
                    message="The first workspace control message must subscribe to the workspace.",
                    recoverable=False,
                ),
            )
            await websocket.close(code=4400, reason="workspace_subscribe_required")
            return
        registry.attach_workspace_session_observer(
            workspace_id=workspace_id,
            websocket=websocket,
        )
        attached = True
        await _send_event(
            websocket,
            DeviceControlEvent(
                type="session_active",
                workspace_id=workspace_id,
                state="active",
                active_sessions=registry.list_active_sessions(workspace_id=workspace_id),
            ),
        )
        while True:
            message = await _receive_control_message(websocket)
            if message.type == "reference_lesson_state":
                event = DeviceControlEvent(
                    type="reference_lesson_state",
                    workspace_id=workspace_id,
                    reference_lesson_state=message.reference_lesson_state or {},
                    active_sessions=registry.list_active_sessions(workspace_id=workspace_id),
                )
                await _broadcast_to_source_devices(
                    registry=registry,
                    workspace_id=workspace_id,
                    pairing_code="",
                    event=event,
                )
                await _broadcast_workspace_session_observers(
                    registry=registry,
                    workspace_id=workspace_id,
                    event=event,
                )
    except WebSocketDisconnect:
        pass
    finally:
        if attached:
            registry.detach_workspace_session_observer(
                workspace_id=workspace_id,
                websocket=websocket,
            )


@router.websocket("/{workspace_id}/device-bindings/{pairing_code}/control")
async def control_device_binding_session(
    websocket: WebSocket,
    workspace_id: str,
    pairing_code: str,
    workspace: Workspace = Depends(get_workspace),
    registry: DeviceBindingRegistry = Depends(get_device_binding_registry),
    media_service: LiveMediaSessionService | None = Depends(
        get_device_binding_live_media_service
    ),
) -> None:
    """Run the workspace/source device binding control channel."""

    _ = workspace
    await websocket.accept()
    entry: DeviceSessionEntry | None = None
    observer_attached = False

    try:
        message = await _receive_control_message(websocket)
        if message.type == "workspace_subscribe":
            await _run_workspace_observer(
                websocket=websocket,
                workspace_id=workspace_id,
                pairing_code=pairing_code,
                registry=registry,
            )
            return

        if message.type != "source_join":
            await _send_event(
                websocket,
                _error_event(
                    workspace_id=workspace_id,
                    pairing_code=pairing_code,
                    reason="source_join_required",
                    message="The first device control message must join as workspace or source.",
                    recoverable=False,
                ),
            )
            await websocket.close(code=4400, reason="source_join_required")
            return

        declaration = DeviceCapabilityDeclaration(
            device_id=message.device_id,
            display_name=message.display_name,
            source_types=message.source_types,
            metadata=message.metadata,
        )
        entry = registry.connect_source_device(
            workspace_id=workspace_id,
            pairing_code=pairing_code,
            declaration=declaration,
            websocket=websocket,
        )
        event = _entry_event(
            event_type="session_paired",
            entry=entry,
            active_sessions=registry.list_active_sessions(workspace_id=workspace_id),
        )
        await _send_event(websocket, event)
        await _broadcast_to_workspace_observers(
            registry=registry,
            pairing_code=pairing_code,
            event=event,
        )

        while True:
            message = await _receive_control_message(websocket)
            if message.type == "heartbeat":
                entry = registry.refresh_session(session_id=entry.session_id)
                event = _entry_event(
                    event_type="heartbeat_ack",
                    entry=entry,
                    active_sessions=registry.list_active_sessions(workspace_id=workspace_id),
                )
                await _send_event(websocket, event)
                await _broadcast_to_workspace_observers(
                    registry=registry,
                    pairing_code=pairing_code,
                    event=_entry_event(
                        event_type="session_active",
                        entry=entry,
                        active_sessions=registry.list_active_sessions(
                            workspace_id=workspace_id,
                        ),
                    ),
                )
                continue
            if message.type == "session_close":
                entry.terminal_reason = "closed_by_source"
                try:
                    await _stop_attached_live_media_session(entry, media_service)
                except LiveMediaReceiverControlError as exc:
                    await _send_event(
                        websocket,
                        _error_event(
                            workspace_id=workspace_id,
                            pairing_code=pairing_code,
                            reason=exc.reason,
                            message="The live media receiver could not be stopped.",
                            recoverable=True,
                            active_sessions=registry.list_active_sessions(
                                workspace_id=workspace_id,
                            ),
                        ),
                    )
                    continue
                closed = registry.close_session(
                    session_id=entry.session_id,
                    reason="closed_by_source",
                )
                if closed is not None:
                    event = _entry_event(
                        event_type="session_closed",
                        entry=closed,
                        active_sessions=registry.list_active_sessions(
                            workspace_id=workspace_id,
                        ),
                        reason=closed.terminal_reason,
                        recoverable=False,
                    )
                    await _send_event(websocket, event)
                    await _broadcast_to_workspace_observers(
                        registry=registry,
                        pairing_code=pairing_code,
                        event=event,
                    )
                await websocket.close(code=1000)
                return
    except DeviceBindingRegistryError as exc:
        await _send_event(
            websocket,
            _error_event(
                workspace_id=workspace_id,
                pairing_code=pairing_code,
                reason=exc.reason,
                message=exc.message,
                recoverable=False,
                active_sessions=registry.list_active_sessions(workspace_id=workspace_id),
            ),
        )
        await websocket.close(code=exc.close_code, reason=exc.reason)
    except WebSocketDisconnect:
        pass
    finally:
        if observer_attached:
            registry.detach_workspace_observer(
                pairing_code=pairing_code,
                websocket=websocket,
            )
        if entry is not None:
            try:
                entry.terminal_reason = "socket_closed"
                await _stop_attached_live_media_session(entry, media_service)
            except LiveMediaReceiverControlError as exc:
                logger.error(
                    "live media receiver cleanup failed after source disconnect",
                    extra={
                        "workspace_id": entry.workspace_id,
                        "device_session_id": entry.session_id,
                        "media_session_id": entry.media_session_id,
                        "reason": exc.reason,
                    },
                )
            closed = registry.close_session(session_id=entry.session_id)
            if closed is not None:
                await _broadcast_to_workspace_observers(
                    registry=registry,
                    pairing_code=pairing_code,
                    event=_entry_event(
                        event_type="session_closed",
                        entry=closed,
                        active_sessions=registry.list_active_sessions(
                            workspace_id=workspace_id,
                        ),
                        reason=closed.terminal_reason,
                        recoverable=False,
                    ),
                )


async def _receive_control_message(websocket: WebSocket) -> DeviceControlMessage:
    raw = await websocket.receive_text()
    try:
        payload: Any = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DeviceBindingRegistryError(
            reason="invalid_json",
            message="Device control messages must be JSON.",
        ) from exc
    try:
        return DeviceControlMessage.model_validate(payload)
    except ValidationError as exc:
        raise DeviceBindingRegistryError(
            reason="invalid_message",
            message=str(exc.errors()[0].get("msg") or "Invalid message."),
        ) from exc


async def _run_workspace_observer(
    *,
    websocket: WebSocket,
    workspace_id: str,
    pairing_code: str,
    registry: DeviceBindingRegistry,
) -> None:
    pairing = registry.attach_workspace_observer(
        workspace_id=workspace_id,
        pairing_code=pairing_code,
        websocket=websocket,
    )
    await _send_event(
        websocket,
        DeviceControlEvent(
            type="pairing_ready",
            workspace_id=workspace_id,
            pairing_code=pairing.pairing_code,
            state="pairing",
            expires_at_epoch=pairing.expires_at_epoch,
            active_sessions=registry.list_active_sessions(workspace_id=workspace_id),
        ),
    )
    try:
        while True:
            message = await _receive_control_message(websocket)
            if message.type == "reference_lesson_state":
                event = DeviceControlEvent(
                    type="reference_lesson_state",
                    workspace_id=workspace_id,
                    pairing_code=pairing_code,
                    reference_lesson_state=message.reference_lesson_state or {},
                    active_sessions=registry.list_active_sessions(workspace_id=workspace_id),
                )
                await _broadcast_to_source_devices(
                    registry=registry,
                    workspace_id=workspace_id,
                    pairing_code=pairing_code,
                    event=event,
                )
                await _broadcast_to_workspace_observers(
                    registry=registry,
                    pairing_code=pairing_code,
                    event=event,
                )
    finally:
        registry.detach_workspace_observer(
            pairing_code=pairing_code,
            websocket=websocket,
        )
