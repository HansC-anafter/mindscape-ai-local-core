from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.app.models.device_binding import DeviceCapabilityDeclaration
from backend.app.models.media_transport import MediaSignalMessage, MediaStreamRef


def test_media_signal_message_rejects_raw_media_payload() -> None:
    with pytest.raises(ValidationError) as exc_info:
        MediaSignalMessage.model_validate(
            {
                "type": "ice_candidate",
                "candidate": {
                    "candidate": "candidate:1",
                    "video_base64": "AAAA",
                },
            }
        )

    assert "raw_media_payload_not_allowed" in str(exc_info.value)


def test_media_stream_ref_allows_fixed_camera_source_kinds() -> None:
    for source_kind in (
        "phone_camera",
        "desktop_camera",
        "usb_camera",
        "virtual_camera",
        "external_provider_camera",
    ):
        ref = MediaStreamRef(
            workspace_id="ws_device",
            device_session_id="session_1",
            media_session_id="media_1",
            source_kind=source_kind,
            stream_id="stream_1",
            track_kinds=["video"],
            started_at_epoch=1.0,
        )
        assert ref.source_kind == source_kind


def test_media_stream_ref_rejects_direct_rtsp_source_kind() -> None:
    with pytest.raises(ValidationError):
        MediaStreamRef(
            workspace_id="ws_device",
            device_session_id="session_1",
            media_session_id="media_1",
            source_kind="rtsp_camera",
            stream_id="stream_1",
            track_kinds=["video"],
            started_at_epoch=1.0,
        )


def test_device_binding_declaration_accepts_usb_camera_without_obs_control() -> None:
    declaration = DeviceCapabilityDeclaration(
        device_id="desktop_1",
        source_types=["usb_camera", "virtual_camera"],
    )

    assert declaration.source_types == ["usb_camera", "virtual_camera"]


def test_device_binding_declaration_accepts_external_provider_camera() -> None:
    declaration = DeviceCapabilityDeclaration(
        device_id="provider_bridge_1",
        display_name="Provider bridge",
        source_types=["external_provider_camera"],
        metadata={
            "capture_surface": "external_provider_bridge",
            "provider_family": "dji_ground_imaging",
            "provider_backend": "dji_mobile_companion",
        },
    )

    assert declaration.source_types == ["external_provider_camera"]
    assert declaration.metadata["capture_surface"] == "external_provider_bridge"
