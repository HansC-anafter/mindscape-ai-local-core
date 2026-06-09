"""Workspace-scoped device binding and control WebSocket routes."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, ValidationError

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

router = APIRouter()


class CreateDevicePairingCodeRequest(BaseModel):
    """Request body for issuing a workspace device pairing code."""

    model_config = ConfigDict(extra="forbid")

    label: str | None = None


async def _send_event(websocket: WebSocket, event: DeviceControlEvent) -> None:
    await websocket.send_text(json.dumps(event.model_dump(mode="json", exclude_none=True)))


def _entry_event(
    *,
    event_type: str,
    entry: DeviceSessionEntry,
    active_sessions: list[DeviceSessionEntry] | None = None,
    reason: str | None = None,
    message: str | None = None,
    recoverable: bool | None = None,
) -> DeviceControlEvent:
    return DeviceControlEvent(
        type=event_type,
        workspace_id=entry.workspace_id,
        pairing_code=entry.pairing_code,
        session_id=entry.session_id,
        device_id=entry.device_id,
        display_name=entry.display_name,
        source_types=entry.source_types,
        state=entry.state,
        expires_at_epoch=entry.expires_at_epoch,
        active_sessions=active_sessions or [],
        reason=reason,
        message=message,
        recoverable=recoverable,
    )


def _error_event(
    *,
    workspace_id: str,
    pairing_code: str,
    reason: str,
    message: str,
    recoverable: bool,
    active_sessions: list[DeviceSessionEntry] | None = None,
) -> DeviceControlEvent:
    return DeviceControlEvent(
        type="session_error",
        workspace_id=workspace_id,
        pairing_code=pairing_code,
        state="rejected",
        active_sessions=active_sessions or [],
        reason=reason,
        message=message,
        recoverable=recoverable,
    )


async def _broadcast_to_workspace_observers(
    *,
    registry: DeviceBindingRegistry,
    pairing_code: str,
    event: DeviceControlEvent,
) -> None:
    stale: list[WebSocket] = []
    for observer in registry.workspace_observers(pairing_code=pairing_code):
        try:
            await _send_event(observer, event)
        except RuntimeError:
            stale.append(observer)
    for observer in stale:
        registry.detach_workspace_observer(
            pairing_code=pairing_code,
            websocket=observer,
        )


async def _broadcast_to_source_devices(
    *,
    registry: DeviceBindingRegistry,
    workspace_id: str,
    pairing_code: str,
    event: DeviceControlEvent,
) -> None:
    for entry in registry.list_active_sessions(workspace_id=workspace_id):
        if entry.pairing_code != pairing_code or entry.websocket is None:
            continue
        try:
            await _send_event(entry.websocket, event)
        except RuntimeError:
            continue


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

    _ = payload
    _ = workspace
    return registry.create_pairing_code(workspace_id=workspace_id)


@router.post(
    "/{workspace_id}/device-bindings/{session_id}/revoke",
    response_model=DeviceControlEvent,
)
async def revoke_device_binding_session(
    workspace_id: str = Path(..., description="Workspace ID"),
    session_id: str = Path(..., description="Device session ID"),
    workspace: Workspace = Depends(get_workspace),
    registry: DeviceBindingRegistry = Depends(get_device_binding_registry),
) -> DeviceControlEvent:
    """Revoke one active device binding session."""

    _ = workspace
    try:
        entry = registry.revoke_session(
            workspace_id=workspace_id,
            session_id=session_id,
        )
    except DeviceBindingRegistryError as exc:
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


@router.websocket("/{workspace_id}/device-bindings/{pairing_code}/control")
async def control_device_binding_session(
    websocket: WebSocket,
    workspace_id: str,
    pairing_code: str,
    workspace: Workspace = Depends(get_workspace),
    registry: DeviceBindingRegistry = Depends(get_device_binding_registry),
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
                closed = registry.close_session(session_id=entry.session_id)
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
