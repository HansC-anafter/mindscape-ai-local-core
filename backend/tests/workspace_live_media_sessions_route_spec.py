from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.services.media_transport.live_media_config import LiveMediaConfig
from backend.app.services.media_transport.live_media_session_service import (
    LiveMediaSessionService,
    LiveMediaSessionServiceError,
)
from backend.app.services.orchestration.meeting.device_binding_registry import (
    DeviceBindingRegistry,
)


def _load_route_module(name: str):
    module_path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "routes"
        / "core"
        / "workspace"
        / f"{name}.py"
    )
    spec = importlib.util.spec_from_file_location(f"{name}_live_media_route", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _service(tmp_path: Path) -> LiveMediaSessionService:
    key_path = tmp_path / "media-private.pem"
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    key_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    os.chmod(key_path, 0o600)
    return LiveMediaSessionService(
        LiveMediaConfig(
            public_webrtc_origin="https://media.mindscapeai.app",
            public_rtmps_origin="rtmps://media.mindscapeai.app:1936",
            receiver_rtsps_origin="rtsps://media.mindscapeai.app:8322",
            jwt_private_key_path=key_path,
            jwt_key_id="media-test",
            jwt_issuer="https://remote-workbench.mindscapeai.app/media-auth",
            jwt_audience="mindscape-media-relay",
            session_ttl_seconds=3600,
        )
    )


def _client(tmp_path: Path):
    device_module = _load_route_module("device_bindings")
    media_module = _load_route_module("media_sessions")
    registry = DeviceBindingRegistry()
    service = _service(tmp_path)
    app = FastAPI()
    app.include_router(device_module.router, prefix="/api/v1/workspaces")
    app.include_router(media_module.router, prefix="/api/v1/workspaces")
    for module in (device_module, media_module):
        app.dependency_overrides[module.get_workspace] = lambda: SimpleNamespace(
            id="ws_device",
            default_locale="zh-TW",
        )
        app.dependency_overrides[module.get_device_binding_registry] = lambda: registry
    app.dependency_overrides[media_module.get_live_media_session_route_service] = (
        lambda: service
    )
    app.dependency_overrides[device_module.get_device_binding_live_media_service] = (
        lambda: service
    )
    return TestClient(app), registry, service


def _connect_device(client: TestClient) -> tuple[str, object]:
    pairing = client.post(
        "/api/v1/workspaces/ws_device/device-bindings/pairing-codes",
        json={},
    ).json()
    socket = client.websocket_connect(
        "/api/v1/workspaces/ws_device/device-bindings/"
        f"{pairing['pairing_code']}/control"
    )
    source = socket.__enter__()
    source.send_json(
        {
            "type": "source_join",
            "device_id": "phone_1",
            "source_types": ["phone_camera", "microphone"],
        }
    )
    paired = source.receive_json()
    return paired["session_id"], socket


def test_live_media_routes_create_read_refresh_and_stop_without_get_token_leak(
    tmp_path: Path,
) -> None:
    client, registry, _ = _client(tmp_path)
    device_session_id, source_socket = _connect_device(client)
    collection_url = (
        "/api/v1/workspaces/ws_device/device-bindings/"
        f"{device_session_id}/media-sessions"
    )

    created = client.post(
        collection_url,
        json={
            "source_kind": "phone_camera",
            "capabilities": ["video", "audio"],
            "analysis_reserved": True,
        },
    )

    assert created.status_code == 200
    access = created.json()
    assert set(access["tokens"]) == {"publish", "preview", "receiver"}
    media_session_id = access["session"]["media_session_id"]
    device_entry = registry.get_active_session(
        workspace_id="ws_device",
        session_id=device_session_id,
    )
    assert device_entry is not None
    assert device_entry.media_session_id == media_session_id

    readback = client.get(collection_url)
    assert readback.status_code == 200
    assert "token" not in readback.text.lower()
    assert readback.json()["media_session_id"] == media_session_id

    refreshed = client.post(f"{collection_url}/{media_session_id}/refresh")
    assert refreshed.status_code == 200
    assert refreshed.json()["session"]["expires_at_epoch"] == access["session"]["expires_at_epoch"]

    stopped = client.post(f"{collection_url}/{media_session_id}/stop")
    assert stopped.status_code == 200
    assert stopped.json()["state"] == "stopped"
    assert client.get(collection_url).status_code == 404
    source_socket.__exit__(None, None, None)


def test_live_media_route_rejects_unknown_device_session(tmp_path: Path) -> None:
    client, _, _ = _client(tmp_path)

    response = client.post(
        "/api/v1/workspaces/ws_device/device-bindings/missing/media-sessions",
        json={"source_kind": "phone_camera"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "unknown_device_session"


def test_source_disconnect_releases_attached_media_reservation(tmp_path: Path) -> None:
    client, _, service = _client(tmp_path)
    device_session_id, source_socket = _connect_device(client)
    collection_url = (
        "/api/v1/workspaces/ws_device/device-bindings/"
        f"{device_session_id}/media-sessions"
    )
    created = client.post(
        collection_url,
        json={"source_kind": "phone_camera", "analysis_reserved": True},
    ).json()
    media_session_id = created["session"]["media_session_id"]

    source_socket.__exit__(None, None, None)

    with pytest.raises(LiveMediaSessionServiceError) as exc_info:
        service.get_active(
            workspace_id="ws_device",
            device_session_id=device_session_id,
        )
    assert exc_info.value.reason == "live_media_session_not_found"
    assert media_session_id.startswith("lms_")
