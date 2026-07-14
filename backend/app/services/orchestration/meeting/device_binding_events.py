"""Event construction and fan-out for workspace device bindings."""

from __future__ import annotations

import json

from fastapi import WebSocket

from backend.app.models.device_binding import DeviceControlEvent, DeviceSessionEntry
from backend.app.services.orchestration.meeting.device_binding_registry import (
    DeviceBindingRegistry,
)


async def send_device_control_event(
    websocket: WebSocket,
    event: DeviceControlEvent,
) -> None:
    await websocket.send_text(json.dumps(event.model_dump(mode="json", exclude_none=True)))


def build_entry_event(
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


def build_error_event(
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


async def broadcast_to_workspace_observers(
    *,
    registry: DeviceBindingRegistry,
    pairing_code: str,
    event: DeviceControlEvent,
) -> None:
    stale: list[WebSocket] = []
    for observer in registry.workspace_observers(pairing_code=pairing_code):
        try:
            await send_device_control_event(observer, event)
        except RuntimeError:
            stale.append(observer)
    for observer in stale:
        registry.detach_workspace_observer(
            pairing_code=pairing_code,
            websocket=observer,
        )

    stale_workspace_observers: list[WebSocket] = []
    for observer in registry.workspace_session_observers(
        workspace_id=event.workspace_id,
    ):
        try:
            await send_device_control_event(observer, event)
        except RuntimeError:
            stale_workspace_observers.append(observer)
    for observer in stale_workspace_observers:
        registry.detach_workspace_session_observer(
            workspace_id=event.workspace_id,
            websocket=observer,
        )


async def broadcast_to_source_devices(
    *,
    registry: DeviceBindingRegistry,
    workspace_id: str,
    pairing_code: str,
    event: DeviceControlEvent,
) -> None:
    for entry in registry.list_active_sessions(workspace_id=workspace_id):
        if (pairing_code and entry.pairing_code != pairing_code) or entry.websocket is None:
            continue
        try:
            await send_device_control_event(entry.websocket, event)
        except RuntimeError:
            continue


async def broadcast_workspace_session_observers(
    *,
    registry: DeviceBindingRegistry,
    workspace_id: str,
    event: DeviceControlEvent,
) -> None:
    stale: list[WebSocket] = []
    for observer in registry.workspace_session_observers(workspace_id=workspace_id):
        try:
            await send_device_control_event(observer, event)
        except RuntimeError:
            stale.append(observer)
    for observer in stale:
        registry.detach_workspace_session_observer(
            workspace_id=workspace_id,
            websocket=observer,
        )


__all__ = [
    "broadcast_to_source_devices",
    "broadcast_to_workspace_observers",
    "broadcast_workspace_session_observers",
    "build_entry_event",
    "build_error_event",
    "send_device_control_event",
]
