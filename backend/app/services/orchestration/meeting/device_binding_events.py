"""Event construction and fan-out for workspace device bindings."""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import WebSocket

from backend.app.models.device_binding import DeviceControlEvent, DeviceSessionEntry
from backend.app.services.orchestration.meeting.device_binding_registry import (
    DeviceBindingRegistry,
)


logger = logging.getLogger(__name__)
OBSERVER_SEND_TIMEOUT_SECONDS = 1.0


async def _send_observer_event(
    websocket: WebSocket,
    event: DeviceControlEvent,
) -> bool:
    try:
        await asyncio.wait_for(
            send_device_control_event(websocket, event),
            timeout=OBSERVER_SEND_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        logger.info(
            "detaching closed device-binding observer: %s",
            type(exc).__name__,
        )
        return False
    return True


async def _stale_observers(
    observers: list[WebSocket],
    event: DeviceControlEvent,
) -> list[WebSocket]:
    if not observers:
        return []
    delivered = await asyncio.gather(
        *(_send_observer_event(observer, event) for observer in observers)
    )
    return [
        observer
        for observer, was_delivered in zip(observers, delivered, strict=True)
        if not was_delivered
    ]


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
    heartbeat_sequence: int | None = None,
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
        heartbeat_sequence=heartbeat_sequence,
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
    pairing_observers = registry.workspace_observers(pairing_code=pairing_code)
    workspace_observers = registry.workspace_session_observers(
        workspace_id=event.workspace_id,
    )
    observers_by_identity = {
        id(observer): observer
        for observer in [*pairing_observers, *workspace_observers]
    }
    stale = await _stale_observers(list(observers_by_identity.values()), event)
    pairing_observer_ids = {id(observer) for observer in pairing_observers}
    workspace_observer_ids = {id(observer) for observer in workspace_observers}
    for observer in stale:
        if id(observer) in pairing_observer_ids:
            registry.detach_workspace_observer(
                pairing_code=pairing_code,
                websocket=observer,
            )
        if id(observer) in workspace_observer_ids:
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
    observers = [
        entry.websocket
        for entry in registry.list_active_sessions(workspace_id=workspace_id)
        if (
            (not pairing_code or entry.pairing_code == pairing_code)
            and entry.websocket is not None
        )
    ]
    await _stale_observers(observers, event)


async def broadcast_workspace_session_observers(
    *,
    registry: DeviceBindingRegistry,
    workspace_id: str,
    event: DeviceControlEvent,
) -> None:
    observers = registry.workspace_session_observers(workspace_id=workspace_id)
    stale = await _stale_observers(observers, event)
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
