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


def _load_device_bindings_module():
    module_path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "routes"
        / "core"
        / "workspace"
        / "device_bindings.py"
    )
    spec = importlib.util.spec_from_file_location(
        "device_bindings_route_under_test",
        module_path,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _build_app(module, *, registry):
    app = FastAPI()
    app.include_router(module.router, prefix="/api/v1/workspaces")
    app.dependency_overrides[module.get_workspace] = lambda: SimpleNamespace(
        id="ws_device",
        default_locale="zh-TW",
    )
    app.dependency_overrides[module.get_device_binding_registry] = lambda: registry
    return app


def _receive(ws):
    return json.loads(ws.receive_text())


def test_device_binding_pairing_code_route_issues_code() -> None:
    module = _load_device_bindings_module()
    registry = DeviceBindingRegistry()
    client = TestClient(_build_app(module, registry=registry))

    response = client.post("/api/v1/workspaces/ws_device/device-bindings/pairing-codes", json={})

    assert response.status_code == 200
    payload = response.json()
    assert payload["workspace_id"] == "ws_device"
    assert payload["device_link_path"] == f"/device-link/{payload['pairing_code']}"


def test_device_binding_pairing_code_route_accepts_smoke_ttl() -> None:
    module = _load_device_bindings_module()
    registry = DeviceBindingRegistry()
    client = TestClient(_build_app(module, registry=registry))

    response = client.post(
        "/api/v1/workspaces/ws_device/device-bindings/pairing-codes",
        json={"expires_in_seconds": 600},
    )

    assert response.status_code == 200
    assert response.json()["expires_in_seconds"] == 600


def test_device_binding_pairing_code_route_rejects_unbounded_ttl() -> None:
    module = _load_device_bindings_module()
    registry = DeviceBindingRegistry()
    client = TestClient(_build_app(module, registry=registry))

    response = client.post(
        "/api/v1/workspaces/ws_device/device-bindings/pairing-codes",
        json={"expires_in_seconds": 601},
    )

    assert response.status_code == 422


def test_device_binding_control_ws_pairs_source_and_notifies_workspace() -> None:
    module = _load_device_bindings_module()
    registry = DeviceBindingRegistry()
    client = TestClient(_build_app(module, registry=registry))
    pairing = client.post(
        "/api/v1/workspaces/ws_device/device-bindings/pairing-codes",
        json={},
    ).json()
    control_url = (
        "/api/v1/workspaces/ws_device/device-bindings/"
        f"{pairing['pairing_code']}/control"
    )

    with client.websocket_connect(control_url) as workspace_ws:
        workspace_ws.send_json({"type": "workspace_subscribe"})
        assert _receive(workspace_ws)["type"] == "pairing_ready"

        with client.websocket_connect(control_url) as source_ws:
            source_ws.send_json(
                {
                    "type": "source_join",
                    "device_id": "phone_1",
                    "display_name": "Phone",
                    "source_types": ["phone_camera", "microphone"],
                }
            )
            source_event = _receive(source_ws)
            workspace_event = _receive(workspace_ws)

            assert source_event["type"] == "session_paired"
            assert source_event["device_id"] == "phone_1"
            assert workspace_event["type"] == "session_paired"
            assert workspace_event["active_sessions"][0]["device_id"] == "phone_1"


def test_device_binding_control_ws_pairs_external_provider_bridge_source() -> None:
    module = _load_device_bindings_module()
    registry = DeviceBindingRegistry()
    client = TestClient(_build_app(module, registry=registry))
    pairing = client.post(
        "/api/v1/workspaces/ws_device/device-bindings/pairing-codes",
        json={},
    ).json()
    control_url = (
        "/api/v1/workspaces/ws_device/device-bindings/"
        f"{pairing['pairing_code']}/control"
    )

    with client.websocket_connect(control_url) as workspace_ws:
        workspace_ws.send_json({"type": "workspace_subscribe"})
        assert _receive(workspace_ws)["type"] == "pairing_ready"

        with client.websocket_connect(control_url) as source_ws:
            source_ws.send_json(
                {
                    "type": "source_join",
                    "device_id": "provider_bridge_1",
                    "display_name": "External provider bridge",
                    "source_types": ["external_provider_camera"],
                    "metadata": {
                        "capture_surface": "external_provider_bridge",
                        "provider_family": "dji_ground_imaging",
                        "provider_backend": "dji_mobile_companion",
                    },
                }
            )
            source_event = _receive(source_ws)
            workspace_event = _receive(workspace_ws)

            assert source_event["type"] == "session_paired"
            assert source_event["source_types"] == ["external_provider_camera"]
            assert workspace_event["active_sessions"][0]["metadata"] == {
                "capture_surface": "external_provider_bridge",
                "provider_family": "dji_ground_imaging",
                "provider_backend": "dji_mobile_companion",
            }


def test_device_binding_control_ws_rejects_duplicate_pairing_code() -> None:
    module = _load_device_bindings_module()
    registry = DeviceBindingRegistry()
    client = TestClient(_build_app(module, registry=registry))
    pairing = client.post(
        "/api/v1/workspaces/ws_device/device-bindings/pairing-codes",
        json={},
    ).json()
    control_url = (
        "/api/v1/workspaces/ws_device/device-bindings/"
        f"{pairing['pairing_code']}/control"
    )

    with client.websocket_connect(control_url) as first:
        first.send_json({"type": "source_join", "device_id": "phone_1"})
        assert _receive(first)["type"] == "session_paired"

        with client.websocket_connect(control_url) as duplicate:
            duplicate.send_json({"type": "source_join", "device_id": "phone_2"})
            error = _receive(duplicate)
            assert error["type"] == "session_error"
            assert error["reason"] == "duplicate_pairing_code"


def test_device_binding_control_ws_allows_reconnect_after_session_close() -> None:
    module = _load_device_bindings_module()
    registry = DeviceBindingRegistry()
    client = TestClient(_build_app(module, registry=registry))
    pairing = client.post(
        "/api/v1/workspaces/ws_device/device-bindings/pairing-codes",
        json={},
    ).json()
    control_url = (
        "/api/v1/workspaces/ws_device/device-bindings/"
        f"{pairing['pairing_code']}/control"
    )

    with client.websocket_connect(control_url) as first:
        first.send_json({"type": "source_join", "device_id": "phone_1"})
        first_session = _receive(first)
        assert first_session["type"] == "session_paired"
        first.send_json({"type": "session_close"})
        closed = _receive(first)
        assert closed["type"] == "session_closed"

    with client.websocket_connect(control_url) as second:
        second.send_json({"type": "source_join", "device_id": "phone_1"})
        second_session = _receive(second)

        assert second_session["type"] == "session_paired"
        assert second_session["session_id"] != first_session["session_id"]


def test_workspace_device_control_restores_existing_sessions_and_observes_new_pairings() -> None:
    module = _load_device_bindings_module()
    registry = DeviceBindingRegistry()
    client = TestClient(_build_app(module, registry=registry))
    first_pairing = client.post(
        "/api/v1/workspaces/ws_device/device-bindings/pairing-codes",
        json={},
    ).json()
    first_control_url = (
        "/api/v1/workspaces/ws_device/device-bindings/"
        f"{first_pairing['pairing_code']}/control"
    )
    workspace_control_url = "/api/v1/workspaces/ws_device/device-bindings/control"

    with client.websocket_connect(first_control_url) as first_source:
        first_source.send_json({"type": "source_join", "device_id": "phone_1"})
        first_session = _receive(first_source)

        with client.websocket_connect(workspace_control_url) as workspace_ws:
            workspace_ws.send_json({"type": "workspace_subscribe"})
            initial = _receive(workspace_ws)

            assert initial["type"] == "session_active"
            assert initial["active_sessions"][0]["session_id"] == first_session["session_id"]

            second_pairing = client.post(
                "/api/v1/workspaces/ws_device/device-bindings/pairing-codes",
                json={},
            ).json()
            second_control_url = (
                "/api/v1/workspaces/ws_device/device-bindings/"
                f"{second_pairing['pairing_code']}/control"
            )
            with client.websocket_connect(second_control_url) as second_source:
                second_source.send_json({"type": "source_join", "device_id": "phone_2"})
                assert _receive(second_source)["type"] == "session_paired"
                update = _receive(workspace_ws)

                assert update["type"] == "session_paired"
                assert [entry["device_id"] for entry in update["active_sessions"]] == [
                    "phone_1",
                    "phone_2",
                ]


def test_device_binding_revoke_route_broadcasts_terminal_event() -> None:
    module = _load_device_bindings_module()
    registry = DeviceBindingRegistry()
    client = TestClient(_build_app(module, registry=registry))
    pairing = client.post(
        "/api/v1/workspaces/ws_device/device-bindings/pairing-codes",
        json={},
    ).json()
    control_url = (
        "/api/v1/workspaces/ws_device/device-bindings/"
        f"{pairing['pairing_code']}/control"
    )

    with client.websocket_connect(control_url) as workspace_ws:
        workspace_ws.send_json({"type": "workspace_subscribe"})
        assert _receive(workspace_ws)["type"] == "pairing_ready"

        with client.websocket_connect(control_url) as source_ws:
            source_ws.send_json({"type": "source_join", "device_id": "phone_1"})
            paired = _receive(source_ws)
            assert _receive(workspace_ws)["type"] == "session_paired"

            response = client.post(
                "/api/v1/workspaces/ws_device/device-bindings/"
                f"{paired['session_id']}/revoke",
            )

            assert response.status_code == 200
            assert response.json()["type"] == "session_revoked"
            assert _receive(source_ws)["type"] == "session_revoked"
            assert _receive(workspace_ws)["type"] == "session_revoked"


def test_device_binding_control_ws_broadcasts_reference_lesson_state() -> None:
    module = _load_device_bindings_module()
    registry = DeviceBindingRegistry()
    client = TestClient(_build_app(module, registry=registry))
    pairing = client.post(
        "/api/v1/workspaces/ws_device/device-bindings/pairing-codes",
        json={},
    ).json()
    control_url = (
        "/api/v1/workspaces/ws_device/device-bindings/"
        f"{pairing['pairing_code']}/control"
    )

    with client.websocket_connect(control_url) as workspace_ws:
        workspace_ws.send_json({"type": "workspace_subscribe"})
        assert _receive(workspace_ws)["type"] == "pairing_ready"

        with client.websocket_connect(control_url) as source_ws:
            source_ws.send_json({"type": "source_join", "device_id": "pad_1"})
            assert _receive(source_ws)["type"] == "session_paired"
            assert _receive(workspace_ws)["type"] == "session_paired"

            workspace_ws.send_json(
                {
                    "type": "reference_lesson_state",
                    "reference_lesson_state": {
                        "chapter_ref": "chapter_01",
                        "title": "Mountain pose alignment",
                        "timestamp_ms": 65000,
                        "poster_ref": "artifact://poster",
                        "focus_cue": "Ground both feet before raising arms.",
                    },
                }
            )

            source_event = _receive(source_ws)
            workspace_event = _receive(workspace_ws)
            assert source_event["type"] == "reference_lesson_state"
            assert source_event["reference_lesson_state"]["title"] == "Mountain pose alignment"
            assert source_event["reference_lesson_state"]["timestamp_ms"] == 65000
            assert workspace_event["type"] == "reference_lesson_state"
            assert workspace_event["reference_lesson_state"]["focus_cue"] == (
                "Ground both feet before raising arms."
            )
