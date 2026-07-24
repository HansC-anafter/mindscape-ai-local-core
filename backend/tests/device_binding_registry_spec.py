from __future__ import annotations

import pytest

from backend.app.models.device_binding import (
    DeviceCapabilityDeclaration,
    DeviceMediaAnalysisHandoff,
)
from backend.app.services.orchestration.meeting.device_binding_registry import (
    DEVICE_PAIRING_CODE_TTL_SECONDS,
    DEVICE_SESSION_TTL_SECONDS,
    MAX_ACTIVE_SOURCE_DEVICES_PER_WORKSPACE,
    MAX_DEVICE_PAIRING_CODE_TTL_SECONDS,
    DeviceBindingRegistry,
    DeviceBindingRegistryError,
)


def _declaration(index: int = 1) -> DeviceCapabilityDeclaration:
    return DeviceCapabilityDeclaration(
        device_id=f"device_{index}",
        display_name=f"Device {index}",
        source_types=["phone_camera", "microphone"],
        metadata={
            "secure_context": True,
            "source_origin_scheme": "https",
            "capture_surface": "device_link",
        },
    )


def test_registry_creates_pairing_code_with_fixed_ttl() -> None:
    registry = DeviceBindingRegistry()

    pairing = registry.create_pairing_code(workspace_id="ws_device")

    assert pairing.workspace_id == "ws_device"
    assert pairing.expires_in_seconds == DEVICE_PAIRING_CODE_TTL_SECONDS
    assert pairing.device_link_path == f"/device-link/{pairing.pairing_code}"


def test_registry_allows_bounded_pairing_ttl_override() -> None:
    registry = DeviceBindingRegistry()

    pairing = registry.create_pairing_code(workspace_id="ws_device", ttl_seconds=600)
    capped = registry.create_pairing_code(workspace_id="ws_device", ttl_seconds=3600)

    assert pairing.expires_in_seconds == 600
    assert capped.expires_in_seconds == MAX_DEVICE_PAIRING_CODE_TTL_SECONDS


def test_registry_rejects_expired_pairing_code() -> None:
    registry = DeviceBindingRegistry()
    pairing = registry.create_pairing_code(workspace_id="ws_device")
    registry.cleanup_expired(
        now_epoch=pairing.expires_at_epoch + DEVICE_PAIRING_CODE_TTL_SECONDS,
    )

    with pytest.raises(DeviceBindingRegistryError) as exc_info:
        registry.connect_source_device(
            workspace_id="ws_device",
            pairing_code=pairing.pairing_code,
            declaration=_declaration(),
            websocket=object(),
        )

    assert exc_info.value.reason == "unknown_pairing_code"


def test_registry_rejects_workspace_mismatch() -> None:
    registry = DeviceBindingRegistry()
    pairing = registry.create_pairing_code(workspace_id="ws_device")

    with pytest.raises(DeviceBindingRegistryError) as exc_info:
        registry.connect_source_device(
            workspace_id="ws_other",
            pairing_code=pairing.pairing_code,
            declaration=_declaration(),
            websocket=object(),
        )

    assert exc_info.value.reason == "workspace_mismatch"


def test_registry_rejects_duplicate_pairing_code_connect() -> None:
    registry = DeviceBindingRegistry()
    pairing = registry.create_pairing_code(workspace_id="ws_device")
    first = registry.connect_source_device(
        workspace_id="ws_device",
        pairing_code=pairing.pairing_code,
        declaration=_declaration(),
        websocket=object(),
    )

    assert first.state == "paired"
    assert first.metadata == {
        "secure_context": True,
        "source_origin_scheme": "https",
        "capture_surface": "device_link",
    }
    with pytest.raises(DeviceBindingRegistryError) as exc_info:
        registry.connect_source_device(
            workspace_id="ws_device",
            pairing_code=pairing.pairing_code,
            declaration=_declaration(2),
            websocket=object(),
        )

    assert exc_info.value.reason == "duplicate_pairing_code"


def test_registry_releases_pairing_code_after_closed_session_for_reconnect() -> None:
    registry = DeviceBindingRegistry()
    pairing = registry.create_pairing_code(workspace_id="ws_device")
    first = registry.connect_source_device(
        workspace_id="ws_device",
        pairing_code=pairing.pairing_code,
        declaration=_declaration(),
        websocket=object(),
    )

    closed = registry.close_session(session_id=first.session_id)
    second = registry.connect_source_device(
        workspace_id="ws_device",
        pairing_code=pairing.pairing_code,
        declaration=_declaration(2),
        websocket=object(),
    )

    assert closed is not None
    assert closed.state == "closed"
    assert second.state == "paired"
    assert second.session_id != first.session_id
    assert registry.active_count(workspace_id="ws_device") == 1


def test_registry_releases_pairing_code_after_revoked_session_for_reconnect() -> None:
    registry = DeviceBindingRegistry()
    pairing = registry.create_pairing_code(workspace_id="ws_device")
    first = registry.connect_source_device(
        workspace_id="ws_device",
        pairing_code=pairing.pairing_code,
        declaration=_declaration(),
        websocket=object(),
    )

    registry.revoke_session(workspace_id="ws_device", session_id=first.session_id)
    second = registry.connect_source_device(
        workspace_id="ws_device",
        pairing_code=pairing.pairing_code,
        declaration=_declaration(2),
        websocket=object(),
    )

    assert second.state == "paired"
    assert second.session_id != first.session_id


def test_registry_caps_active_source_devices_per_workspace() -> None:
    registry = DeviceBindingRegistry()
    for index in range(MAX_ACTIVE_SOURCE_DEVICES_PER_WORKSPACE):
        pairing = registry.create_pairing_code(workspace_id="ws_device")
        registry.connect_source_device(
            workspace_id="ws_device",
            pairing_code=pairing.pairing_code,
            declaration=_declaration(index),
            websocket=object(),
        )

    overflow = registry.create_pairing_code(workspace_id="ws_device")
    with pytest.raises(DeviceBindingRegistryError) as exc_info:
        registry.connect_source_device(
            workspace_id="ws_device",
            pairing_code=overflow.pairing_code,
            declaration=_declaration(9),
            websocket=object(),
        )

    assert exc_info.value.reason == "active_source_limit_reached"


def test_registry_revoke_removes_active_session() -> None:
    registry = DeviceBindingRegistry()
    pairing = registry.create_pairing_code(workspace_id="ws_device")
    entry = registry.connect_source_device(
        workspace_id="ws_device",
        pairing_code=pairing.pairing_code,
        declaration=_declaration(),
        websocket=object(),
    )

    revoked = registry.revoke_session(
        workspace_id="ws_device",
        session_id=entry.session_id,
    )

    assert revoked.state == "revoked"
    assert revoked.terminal_reason == "revoked_by_workspace"
    assert registry.active_count(workspace_id="ws_device") == 0


def test_registry_refresh_extends_session_ttl() -> None:
    registry = DeviceBindingRegistry()
    pairing = registry.create_pairing_code(workspace_id="ws_device")
    entry = registry.connect_source_device(
        workspace_id="ws_device",
        pairing_code=pairing.pairing_code,
        declaration=_declaration(),
        websocket=object(),
    )

    refreshed = registry.refresh_session(session_id=entry.session_id)

    assert refreshed.state == "active"
    assert refreshed.expires_at_epoch >= refreshed.updated_at_epoch + DEVICE_SESSION_TTL_SECONDS - 1


def test_registry_projects_and_clears_media_analysis_handoff() -> None:
    registry = DeviceBindingRegistry()
    pairing = registry.create_pairing_code(workspace_id="ws_device")
    entry = registry.connect_source_device(
        workspace_id="ws_device",
        pairing_code=pairing.pairing_code,
        declaration=_declaration(),
        websocket=object(),
    )
    registry.attach_live_media_session(
        workspace_id="ws_device",
        session_id=entry.session_id,
        media_session_id="media-one",
        media_session_state="waiting_for_publisher",
        media_session_expires_at_epoch=entry.expires_at_epoch,
    )

    updated = registry.update_live_media_receiver_state(
        workspace_id="ws_device",
        session_id=entry.session_id,
        media_session_id="media-one",
        receiver_state="analyzing",
        analysis_handoff=DeviceMediaAnalysisHandoff(
            live_motion_session_id="motion-one",
            meeting_session_id="meeting-one",
            practice_session_id="practice-one",
            coach_pack="yogacoach",
            practice_mode="live_guidance",
        ),
    )

    assert updated.media_analysis_handoff is not None
    assert updated.media_analysis_handoff.live_motion_session_id == "motion-one"
    assert updated.media_analysis_handoff.meeting_session_id == "meeting-one"
    detached = registry.detach_live_media_session(
        workspace_id="ws_device",
        session_id=entry.session_id,
        media_session_id="media-one",
    )
    assert detached.media_analysis_handoff is None


def test_registry_session_lease_survives_four_phone_heartbeat_intervals() -> None:
    registry = DeviceBindingRegistry()
    pairing = registry.create_pairing_code(workspace_id="ws_device")
    entry = registry.connect_source_device(
        workspace_id="ws_device",
        pairing_code=pairing.pairing_code,
        declaration=_declaration(),
        websocket=object(),
    )

    removed = registry.cleanup_expired(now_epoch=entry.updated_at_epoch + 120)

    assert removed == 0
    assert registry.get_active_session(
        workspace_id="ws_device",
        session_id=entry.session_id,
    ) is entry


def test_registry_tracks_workspace_session_observers_independent_of_pairing_code() -> None:
    registry = DeviceBindingRegistry()
    first = object()
    second = object()

    registry.attach_workspace_session_observer(
        workspace_id="ws_device",
        websocket=first,
    )
    registry.attach_workspace_session_observer(
        workspace_id="ws_device",
        websocket=second,
    )

    assert registry.workspace_session_observers(workspace_id="ws_device") == [
        first,
        second,
    ]

    registry.detach_workspace_session_observer(
        workspace_id="ws_device",
        websocket=first,
    )

    assert registry.workspace_session_observers(workspace_id="ws_device") == [second]
