from __future__ import annotations

import os
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import jwt

from backend.app.models.device_binding import DeviceSessionEntry
from backend.app.models.media_transport import CreateLiveMediaSessionRequest
from backend.app.services.media_transport.live_media_config import LiveMediaConfig
from backend.app.services.media_transport.live_media_session_registry import (
    LiveMediaSessionRegistry,
)
from backend.app.services.media_transport.live_media_session_service import (
    LiveMediaSessionService,
    LiveMediaSessionServiceError,
)
from backend.app.services.media_transport.live_media_token_service import (
    LiveMediaTokenError,
    LiveMediaTokenService,
)


def _write_private_key(path: Path, *, mode: int = 0o600) -> None:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    os.chmod(path, mode)


def _config(private_key_path: Path) -> LiveMediaConfig:
    return LiveMediaConfig(
        public_webrtc_origin="https://media.mindscapeai.app",
        public_rtmps_origin="rtmps://media.mindscapeai.app:1936",
        receiver_rtsps_origin="rtsps://media.mindscapeai.app:8322",
        jwt_private_key_path=private_key_path,
        jwt_key_id="media-2026-07",
        jwt_issuer="https://remote-workbench.mindscapeai.app/media-auth",
        jwt_audience="mindscape-media-relay",
        session_ttl_seconds=3600,
    )


def _device_session(workspace_id: str, session_id: str) -> DeviceSessionEntry:
    return DeviceSessionEntry(
        session_id=session_id,
        workspace_id=workspace_id,
        pairing_code="PAIR1234",
        device_id="phone_1",
        source_types=["phone_camera", "microphone"],
        state="active",
        created_at_epoch=1000,
        updated_at_epoch=1000,
        expires_at_epoch=2000,
    )


def _request(*, analysis_reserved: bool = True) -> CreateLiveMediaSessionRequest:
    return CreateLiveMediaSessionRequest(
        source_kind="phone_camera",
        capabilities=["video", "audio"],
        analysis_reserved=analysis_reserved,
    )


def test_service_issues_exact_path_tokens_and_public_jwks(tmp_path: Path) -> None:
    key_path = tmp_path / "media-private.pem"
    _write_private_key(key_path)
    config = _config(key_path)
    token_service = LiveMediaTokenService(config, now=lambda: 1000)
    service = LiveMediaSessionService(
        config,
        registry=LiveMediaSessionRegistry(config, now=lambda: 1000),
        token_service=token_service,
    )

    access = service.create(
        device_session=_device_session("ws_one", "device_one"),
        request=_request(),
    )

    assert access.session.endpoints.whip_publish_url.endswith(
        f"/{access.session.stream_path}/whip"
    )
    assert access.session.endpoints.whep_preview_url.endswith(
        f"/{access.session.stream_path}/whep"
    )
    assert access.session.expires_at_epoch == 4600
    publish_claims = jwt.get_unverified_claims(access.tokens.publish)
    preview_claims = jwt.get_unverified_claims(access.tokens.preview)
    receiver_claims = jwt.get_unverified_claims(access.tokens.receiver)
    assert publish_claims["mediamtx_permissions"] == [
        {"action": "publish", "path": access.session.stream_path}
    ]
    assert preview_claims["mediamtx_permissions"] == [
        {"action": "read", "path": access.session.stream_path}
    ]
    assert receiver_claims["media_access_role"] == "receiver"
    assert publish_claims["aud"] == "mindscape-media-relay"
    assert jwt.get_unverified_header(access.tokens.publish)["kid"] == "media-2026-07"
    assert token_service.public_jwks()["keys"][0]["kid"] == "media-2026-07"
    assert len(access.tokens.publish) < 1024


def test_service_reuses_same_device_contract_without_creating_second_path(
    tmp_path: Path,
) -> None:
    key_path = tmp_path / "media-private.pem"
    _write_private_key(key_path)
    config = _config(key_path)
    service = LiveMediaSessionService(config)
    device = _device_session("ws_one", "device_one")

    first = service.create(device_session=device, request=_request())
    second = service.create(device_session=device, request=_request())

    assert second.session.media_session_id == first.session.media_session_id
    assert second.session.stream_path == first.session.stream_path


def test_service_allows_only_one_analysis_reserved_session_per_workspace(
    tmp_path: Path,
) -> None:
    key_path = tmp_path / "media-private.pem"
    _write_private_key(key_path)
    config = _config(key_path)
    service = LiveMediaSessionService(config)
    service.create(
        device_session=_device_session("ws_one", "device_one"),
        request=_request(),
    )

    with pytest.raises(LiveMediaSessionServiceError) as exc_info:
        service.create(
            device_session=_device_session("ws_one", "device_two"),
            request=_request(),
        )

    assert exc_info.value.reason == "workspace_analysis_session_already_reserved"
    assert exc_info.value.status_code == 409


def test_service_rejects_source_kind_not_declared_by_device(tmp_path: Path) -> None:
    key_path = tmp_path / "media-private.pem"
    _write_private_key(key_path)
    config = _config(key_path)
    service = LiveMediaSessionService(config)

    with pytest.raises(LiveMediaSessionServiceError) as exc_info:
        service.create(
            device_session=_device_session("ws_one", "device_one"),
            request=CreateLiveMediaSessionRequest(source_kind="usb_camera"),
        )

    assert exc_info.value.reason == "live_media_source_kind_not_declared"


def test_token_service_rejects_group_readable_private_key(tmp_path: Path) -> None:
    key_path = tmp_path / "media-private.pem"
    _write_private_key(key_path, mode=0o640)

    with pytest.raises(LiveMediaTokenError) as exc_info:
        LiveMediaTokenService(_config(key_path))

    assert str(exc_info.value) == "live_media_private_key_permissions_invalid"
