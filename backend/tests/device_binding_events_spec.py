from __future__ import annotations

import asyncio

import pytest

from backend.app.models.device_binding import DeviceControlEvent
from backend.app.services.orchestration.meeting import device_binding_events
from backend.app.services.orchestration.meeting.device_binding_events import (
    broadcast_to_workspace_observers,
    broadcast_workspace_session_observers,
)
from backend.app.services.orchestration.meeting.device_binding_registry import (
    DeviceBindingRegistry,
)


class _ClosedObserverError(Exception):
    pass


class _ClosedObserver:
    async def send_text(self, _payload: str) -> None:
        raise _ClosedObserverError("observer already closed")


class _StalledObserver:
    async def send_text(self, _payload: str) -> None:
        await asyncio.Event().wait()


class _RecordingObserver:
    def __init__(self) -> None:
        self.payloads: list[str] = []

    async def send_text(self, payload: str) -> None:
        self.payloads.append(payload)


def _event() -> DeviceControlEvent:
    return DeviceControlEvent(
        type="session_active",
        workspace_id="ws-device",
        pairing_code="PAIRING",
        state="active",
    )


@pytest.mark.asyncio
async def test_closed_pairing_observer_cannot_abort_source_heartbeat() -> None:
    registry = DeviceBindingRegistry()
    pairing = registry.create_pairing_code(workspace_id="ws-device")
    observer = _ClosedObserver()
    registry.attach_workspace_observer(
        workspace_id="ws-device",
        pairing_code=pairing.pairing_code,
        websocket=observer,
    )

    await broadcast_to_workspace_observers(
        registry=registry,
        pairing_code=pairing.pairing_code,
        event=_event(),
    )

    assert registry.workspace_observers(pairing_code=pairing.pairing_code) == []


@pytest.mark.asyncio
async def test_closed_workspace_observer_is_detached_without_propagation() -> None:
    registry = DeviceBindingRegistry()
    observer = _ClosedObserver()
    registry.attach_workspace_session_observer(
        workspace_id="ws-device",
        websocket=observer,
    )

    await broadcast_workspace_session_observers(
        registry=registry,
        workspace_id="ws-device",
        event=_event(),
    )

    assert registry.workspace_session_observers(workspace_id="ws-device") == []


@pytest.mark.asyncio
async def test_stalled_observer_is_bounded_without_delaying_healthy_observer(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        device_binding_events,
        "OBSERVER_SEND_TIMEOUT_SECONDS",
        0.01,
    )
    registry = DeviceBindingRegistry()
    pairing = registry.create_pairing_code(workspace_id="ws-device")
    stalled = _StalledObserver()
    healthy = _RecordingObserver()
    registry.attach_workspace_observer(
        workspace_id="ws-device",
        pairing_code=pairing.pairing_code,
        websocket=stalled,
    )
    registry.attach_workspace_session_observer(
        workspace_id="ws-device",
        websocket=healthy,
    )

    await asyncio.wait_for(
        broadcast_to_workspace_observers(
            registry=registry,
            pairing_code=pairing.pairing_code,
            event=_event(),
        ),
        timeout=0.1,
    )

    assert registry.workspace_observers(pairing_code=pairing.pairing_code) == []
    assert registry.workspace_session_observers(workspace_id="ws-device") == [
        healthy
    ]
    assert len(healthy.payloads) == 1
