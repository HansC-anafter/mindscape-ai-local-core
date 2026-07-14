from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

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
    spec = importlib.util.spec_from_file_location(f"{name}_route_under_test", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _build_app(device_module, media_module, *, device_registry):
    app = FastAPI()
    app.include_router(device_module.router, prefix="/api/v1/workspaces")
    app.include_router(media_module.router, prefix="/api/v1/workspaces")
    for module in (device_module, media_module):
        app.dependency_overrides[module.get_workspace] = lambda: SimpleNamespace(
            id="ws_device",
            default_locale="zh-TW",
        )
        app.dependency_overrides[module.get_device_binding_registry] = lambda: device_registry
    return app


def _receive(ws):
    return json.loads(ws.receive_text())


def _create_device_session(client: TestClient) -> tuple[str, str]:
    pairing = client.post(
        "/api/v1/workspaces/ws_device/device-bindings/pairing-codes",
        json={},
    ).json()
    control_url = (
        "/api/v1/workspaces/ws_device/device-bindings/"
        f"{pairing['pairing_code']}/control"
    )
    return pairing["pairing_code"], control_url


def test_legacy_media_signaling_ws_is_a_non_executing_compatibility_facade() -> None:
    device_module = _load_route_module("device_bindings")
    media_module = _load_route_module("media_sessions")
    client = TestClient(
        _build_app(
            device_module,
            media_module,
            device_registry=DeviceBindingRegistry(),
        )
    )
    _, control_url = _create_device_session(client)

    with client.websocket_connect(control_url) as source_control:
        source_control.send_json({"type": "source_join", "device_id": "phone_1"})
        paired = _receive(source_control)
        assert paired["type"] == "session_paired"
        media_url = (
            "/api/v1/workspaces/ws_device/device-bindings/"
            f"{paired['session_id']}/media-sessions/{paired['session_id']}/signal"
        )

        with client.websocket_connect(media_url) as source_media:
            error = _receive(source_media)

            assert error["type"] == "session_error"
            assert error["reason"] == "legacy_media_signaling_retired"
            assert error["recoverable"] is False
