from __future__ import annotations

import pytest

from backend.app.models.device_binding import DeviceCapabilityDeclaration
from backend.app.models.media_transport import MediaSignalMessage
from backend.app.services.orchestration.meeting.device_binding_registry import (
    DeviceBindingRegistry,
)
from backend.app.services.orchestration.meeting.webrtc_signaling_registry import (
    MAX_PENDING_WEBRTC_SIGNAL_EVENTS_PER_PEER,
    WebRTCSignalingRegistry,
    WebRTCSignalingRegistryError,
)


def _device_registry_with_session() -> tuple[DeviceBindingRegistry, str]:
    registry = DeviceBindingRegistry()
    pairing = registry.create_pairing_code(workspace_id="ws_device")
    session = registry.connect_source_device(
        workspace_id="ws_device",
        pairing_code=pairing.pairing_code,
        declaration=DeviceCapabilityDeclaration(
            device_id="phone_1",
            source_types=["phone_camera", "microphone"],
        ),
        websocket=object(),
    )
    return registry, session.session_id


def test_signaling_registry_requires_active_device_session() -> None:
    registry = WebRTCSignalingRegistry()
    device_registry = DeviceBindingRegistry()

    with pytest.raises(WebRTCSignalingRegistryError) as exc_info:
        registry.attach_participant(
            workspace_id="ws_device",
            device_session_id="missing",
            media_session_id="media_1",
            participant="source",
            websocket=object(),
            device_binding_registry=device_registry,
        )

    assert exc_info.value.reason == "unknown_device_session"


def test_signaling_registry_queues_offer_until_peer_joins() -> None:
    registry = WebRTCSignalingRegistry()
    device_registry, device_session_id = _device_registry_with_session()
    source_ws = object()
    workspace_ws = object()

    joined, pending, first_peer, first_replaced = registry.attach_participant(
        workspace_id="ws_device",
        device_session_id=device_session_id,
        media_session_id=device_session_id,
        participant="source",
        websocket=source_ws,
        device_binding_registry=device_registry,
    )
    peer, offer = registry.forward_or_queue(
        workspace_id="ws_device",
        device_session_id=device_session_id,
        media_session_id=device_session_id,
        sender="source",
        message=MediaSignalMessage(type="offer", sdp="v=0"),
    )
    workspace_joined, workspace_pending, workspace_peer, workspace_replaced = registry.attach_participant(
        workspace_id="ws_device",
        device_session_id=device_session_id,
        media_session_id=device_session_id,
        participant="workspace",
        websocket=workspace_ws,
        device_binding_registry=device_registry,
    )

    assert joined.type == "participant_joined"
    assert pending == []
    assert first_peer is None
    assert first_replaced is None
    assert peer is None
    assert offer.type == "offer"
    assert workspace_joined.sender == "workspace"
    assert workspace_peer is source_ws
    assert workspace_replaced is None
    assert [event.type for event in workspace_pending] == ["offer"]


def test_signaling_registry_allows_only_one_active_media_session_per_device() -> None:
    registry = WebRTCSignalingRegistry()
    device_registry, device_session_id = _device_registry_with_session()
    registry.attach_participant(
        workspace_id="ws_device",
        device_session_id=device_session_id,
        media_session_id="media_1",
        participant="source",
        websocket=object(),
        device_binding_registry=device_registry,
    )

    with pytest.raises(WebRTCSignalingRegistryError) as exc_info:
        registry.attach_participant(
            workspace_id="ws_device",
            device_session_id=device_session_id,
            media_session_id="media_2",
            participant="source",
            websocket=object(),
            device_binding_registry=device_registry,
        )

    assert exc_info.value.reason == "active_media_session_exists"


def test_signaling_registry_replaces_stale_participant_for_same_media_session() -> None:
    registry = WebRTCSignalingRegistry()
    device_registry, device_session_id = _device_registry_with_session()
    first_workspace_ws = object()
    next_workspace_ws = object()

    registry.attach_participant(
        workspace_id="ws_device",
        device_session_id=device_session_id,
        media_session_id=device_session_id,
        participant="workspace",
        websocket=first_workspace_ws,
        device_binding_registry=device_registry,
    )
    joined, pending, peer, replaced = registry.attach_participant(
        workspace_id="ws_device",
        device_session_id=device_session_id,
        media_session_id=device_session_id,
        participant="workspace",
        websocket=next_workspace_ws,
        device_binding_registry=device_registry,
    )

    assert joined.type == "participant_joined"
    assert pending == []
    assert peer is None
    assert replaced is first_workspace_ws
    assert not registry.is_active_participant(
        workspace_id="ws_device",
        device_session_id=device_session_id,
        media_session_id=device_session_id,
        participant="workspace",
        websocket=first_workspace_ws,
    )
    assert registry.is_active_participant(
        workspace_id="ws_device",
        device_session_id=device_session_id,
        media_session_id=device_session_id,
        participant="workspace",
        websocket=next_workspace_ws,
    )

    registry.detach_participant(
        workspace_id="ws_device",
        device_session_id=device_session_id,
        media_session_id=device_session_id,
        participant="workspace",
        websocket=first_workspace_ws,
    )

    assert registry.is_active_participant(
        workspace_id="ws_device",
        device_session_id=device_session_id,
        media_session_id=device_session_id,
        participant="workspace",
        websocket=next_workspace_ws,
    )


def test_signaling_registry_bounds_pending_signal_events() -> None:
    registry = WebRTCSignalingRegistry()
    device_registry, device_session_id = _device_registry_with_session()
    registry.attach_participant(
        workspace_id="ws_device",
        device_session_id=device_session_id,
        media_session_id=device_session_id,
        participant="source",
        websocket=object(),
        device_binding_registry=device_registry,
    )

    for index in range(MAX_PENDING_WEBRTC_SIGNAL_EVENTS_PER_PEER + 3):
        registry.forward_or_queue(
            workspace_id="ws_device",
            device_session_id=device_session_id,
            media_session_id=device_session_id,
            sender="source",
            message=MediaSignalMessage(
                type="ice_candidate",
                candidate={"candidate": f"candidate:{index}"},
            ),
        )

    _, pending, peer, replaced = registry.attach_participant(
        workspace_id="ws_device",
        device_session_id=device_session_id,
        media_session_id=device_session_id,
        participant="workspace",
        websocket=object(),
        device_binding_registry=device_registry,
    )

    assert len(pending) == MAX_PENDING_WEBRTC_SIGNAL_EVENTS_PER_PEER
    assert pending[0].candidate == {"candidate": "candidate:3"}
    assert peer is not None
    assert replaced is None
