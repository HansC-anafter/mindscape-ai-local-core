from __future__ import annotations

from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from backend.app.models.device_binding import DeviceSessionEntry
from backend.app.models.media_transport import (
    CreateLiveMediaSessionRequest,
    StartLiveMediaReceiverRequest,
)
from backend.app.services.media_transport.live_media_config import LiveMediaConfig
from backend.app.services.media_transport.live_media_receiver_service import (
    LiveMediaReceiverControlError,
    start_live_media_receiver,
    terminate_live_media_session,
)
from backend.app.services.media_transport import live_media_receiver_service
from backend.app.services.host_services.capture_relay_proxy import CaptureRelayUnavailable
from backend.app.services.media_transport.live_media_session_registry import (
    LiveMediaSessionRegistry,
)
from backend.app.services.media_transport.live_media_session_service import (
    LiveMediaSessionService,
    LiveMediaSessionServiceError,
)
from backend.app.services.media_transport.live_media_token_service import (
    LiveMediaTokenService,
)


def _service(tmp_path: Path) -> tuple[LiveMediaSessionService, str]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    key_path = tmp_path / "media-private.pem"
    key_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    key_path.chmod(0o600)
    config = LiveMediaConfig(
        public_webrtc_origin="https://media.example.test",
        public_rtmps_origin="rtmps://media.example.test:1936",
        receiver_rtsps_origin="rtsps://media.example.test:8322",
        jwt_private_key_path=key_path,
        jwt_key_id="media-test",
        jwt_issuer="https://issuer.example.test",
        jwt_audience="media-test",
        session_ttl_seconds=3600,
    )
    service = LiveMediaSessionService(
        config,
        registry=LiveMediaSessionRegistry(config, now=lambda: 1000),
        token_service=LiveMediaTokenService(config, now=lambda: 1000),
    )
    access = service.create(
        device_session=DeviceSessionEntry(
            session_id="device-one",
            workspace_id="workspace-one",
            pairing_code="pair-one",
            device_id="phone-one",
            source_types=["phone_camera"],
            state="active",
            created_at_epoch=900,
            updated_at_epoch=900,
            expires_at_epoch=5000,
        ),
        request=CreateLiveMediaSessionRequest(source_kind="phone_camera"),
    )
    return service, access.session.media_session_id


def _request() -> StartLiveMediaReceiverRequest:
    return StartLiveMediaReceiverRequest(
        live_motion_session_id="motion-one",
        meeting_session_id="meeting-one",
        practice_session_id="practice-one",
        coach_pack="yogacoach",
        practice_mode="live_guidance",
    )


@pytest.mark.asyncio
async def test_receiver_handoff_keeps_credentials_server_only(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service, media_session_id = _service(tmp_path)
    calls: list[dict] = []

    async def fake_call(arguments: dict, *, timeout_ms: int) -> dict:
        calls.append({"arguments": arguments, "timeout_ms": timeout_ms})
        descriptor = arguments["receiver_descriptor"]
        return {
            "schema_version": "live_media_receiver_control.v1",
            "status": "active",
            "state": "starting",
            "media_session_id": descriptor["media_session_id"],
            "receiver_identity": descriptor["receiver_identity"],
        }

    monkeypatch.setattr(
        "backend.app.services.media_transport.live_media_receiver_service."
        "call_capture_relay_arguments",
        fake_call,
    )

    first = await start_live_media_receiver(
        media_service=service,
        workspace_id="workspace-one",
        device_session_id="device-one",
        media_session_id=media_session_id,
        request=_request(),
    )
    second = await start_live_media_receiver(
        media_service=service,
        workspace_id="workspace-one",
        device_session_id="device-one",
        media_session_id=media_session_id,
        request=_request(),
    )

    first_descriptor = calls[0]["arguments"]["receiver_descriptor"]
    second_descriptor = calls[1]["arguments"]["receiver_descriptor"]
    assert first["status"] == "active"
    assert "access_token" not in first
    assert "receiver_identity" not in first
    assert first_descriptor["access_token"]
    assert first_descriptor["append_owner_id"].startswith("append_")
    assert second_descriptor["append_owner_id"] == first_descriptor["append_owner_id"]
    assert second_descriptor["receiver_identity"] == first_descriptor["receiver_identity"]
    assert service.receiver_started(media_session_id) is True
    assert service.get_active(
        workspace_id="workspace-one",
        device_session_id="device-one",
    ).state == "waiting_for_publisher"


def test_receiver_state_projects_without_releasing_reservation(tmp_path: Path) -> None:
    service, media_session_id = _service(tmp_path)

    analyzing = service.update_receiver_state(media_session_id, "analyzing")
    completed = service.update_receiver_state(media_session_id, "completed")

    assert analyzing.state == "ready"
    assert completed.state == "ready"
    assert service.get_active(
        workspace_id="workspace-one",
        device_session_id="device-one",
    ).media_session_id == media_session_id


@pytest.mark.asyncio
async def test_receiver_handoff_rejects_secret_echo(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service, media_session_id = _service(tmp_path)

    async def fake_call(_arguments: dict, *, timeout_ms: int) -> dict:
        _ = timeout_ms
        return {
            "status": "active",
            "media_session_id": media_session_id,
            "access_token": "must-not-return",
        }

    monkeypatch.setattr(
        "backend.app.services.media_transport.live_media_receiver_service."
        "call_capture_relay_arguments",
        fake_call,
    )

    with pytest.raises(LiveMediaReceiverControlError) as exc_info:
        await start_live_media_receiver(
            media_service=service,
            workspace_id="workspace-one",
            device_session_id="device-one",
            media_session_id=media_session_id,
            request=_request(),
        )
    assert exc_info.value.reason == "receiver_control_returned_secret"


@pytest.mark.asyncio
async def test_termination_stops_receiver_before_releasing_reservation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service, media_session_id = _service(tmp_path)
    service.mark_receiver_started(media_session_id)
    calls: list[str] = []

    async def fake_call(_arguments: dict, *, timeout_ms: int) -> dict:
        _ = timeout_ms
        assert service.get_active(
            workspace_id="workspace-one",
            device_session_id="device-one",
        ).media_session_id == media_session_id
        calls.append("receiver_stopped")
        return {"status": "completed", "media_session_id": media_session_id}

    monkeypatch.setattr(
        "backend.app.services.media_transport.live_media_receiver_service."
        "call_capture_relay_arguments",
        fake_call,
    )

    descriptor = await terminate_live_media_session(
        media_service=service,
        workspace_id="workspace-one",
        device_session_id="device-one",
        media_session_id=media_session_id,
        reason="device_session_closed",
    )

    assert calls == ["receiver_stopped"]
    assert descriptor.state == "stopped"
    assert descriptor.terminal_reason == "device_session_closed"
    with pytest.raises(LiveMediaSessionServiceError) as exc_info:
        service.get_active(
            workspace_id="workspace-one",
            device_session_id="device-one",
        )
    assert exc_info.value.reason == "live_media_session_not_found"


@pytest.mark.asyncio
async def test_termination_preserves_reservation_when_receiver_stop_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service, media_session_id = _service(tmp_path)
    service.mark_receiver_started(media_session_id)

    async def fake_call(_arguments: dict, *, timeout_ms: int) -> dict:
        _ = timeout_ms
        raise CaptureRelayUnavailable("device_node_unreachable")

    monkeypatch.setattr(
        "backend.app.services.media_transport.live_media_receiver_service."
        "call_capture_relay_arguments",
        fake_call,
    )

    with pytest.raises(LiveMediaReceiverControlError) as exc_info:
        await terminate_live_media_session(
            media_service=service,
            workspace_id="workspace-one",
            device_session_id="device-one",
            media_session_id=media_session_id,
            reason="device_session_closed",
        )

    assert exc_info.value.reason == "device_node_unreachable"
    assert service.get_active(
        workspace_id="workspace-one",
        device_session_id="device-one",
    ).media_session_id == media_session_id


@pytest.mark.asyncio
async def test_termination_preserves_reservation_until_stop_is_confirmed(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service, media_session_id = _service(tmp_path)
    service.mark_receiver_started(media_session_id)
    monkeypatch.setattr(
        live_media_receiver_service,
        "RECEIVER_CLOSEOUT_WAIT_SECONDS",
        0.0,
    )

    async def fake_call(_arguments: dict, *, timeout_ms: int) -> dict:
        _ = timeout_ms
        return {"status": "stopping", "media_session_id": media_session_id}

    monkeypatch.setattr(
        "backend.app.services.media_transport.live_media_receiver_service."
        "call_capture_relay_arguments",
        fake_call,
    )

    with pytest.raises(LiveMediaReceiverControlError) as exc_info:
        await terminate_live_media_session(
            media_service=service,
            workspace_id="workspace-one",
            device_session_id="device-one",
            media_session_id=media_session_id,
            reason="device_session_closed",
        )

    assert exc_info.value.reason == "live_media_receiver_stop_not_confirmed"
    assert service.get_active(
        workspace_id="workspace-one",
        device_session_id="device-one",
    ).media_session_id == media_session_id


@pytest.mark.asyncio
async def test_termination_polls_stopping_receiver_until_closeout_completes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service, media_session_id = _service(tmp_path)
    service.mark_receiver_started(media_session_id)
    actions: list[str] = []

    async def fake_call(arguments: dict, *, timeout_ms: int) -> dict:
        _ = timeout_ms
        action = str(arguments["action"])
        actions.append(action)
        if action == "receiver_stop":
            return {"status": "stopping", "media_session_id": media_session_id}
        return {"status": "completed", "media_session_id": media_session_id}

    monkeypatch.setattr(
        live_media_receiver_service,
        "call_capture_relay_arguments",
        fake_call,
    )
    monkeypatch.setattr(
        live_media_receiver_service,
        "RECEIVER_STATUS_POLL_INTERVAL_SECONDS",
        0.0,
    )

    descriptor = await terminate_live_media_session(
        media_service=service,
        workspace_id="workspace-one",
        device_session_id="device-one",
        media_session_id=media_session_id,
        reason="device_session_closed",
    )

    assert actions == ["receiver_stop", "receiver_status"]
    assert descriptor.state == "stopped"
