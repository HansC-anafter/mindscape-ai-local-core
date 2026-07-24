from __future__ import annotations

import pytest

from backend.app.services.host_services import capture_relay_proxy
from backend.app.services.host_services.capture_relay_proxy import (
    CaptureRelayRequest,
    CaptureRelayUnavailable,
    call_capture_relay_arguments,
    call_capture_relay_control,
)


@pytest.mark.asyncio
async def test_call_capture_relay_control_parses_device_node_text_payload(monkeypatch):
    captured: dict[str, object] = {}

    async def fake_post_device_node_mcp(*, arguments, timeout_seconds):
        captured["arguments"] = arguments
        captured["timeout_seconds"] = timeout_seconds
        return {
            "content": [
                {
                    "type": "text",
                    "text": (
                        '{"schema_version":"capture_relay_control.v1",'
                        '"status":"blocked","reason":"relay_binary_missing"}'
                    ),
                }
            ]
        }

    monkeypatch.setattr(
        capture_relay_proxy,
        "_post_device_node_mcp",
        fake_post_device_node_mcp,
    )

    result = await call_capture_relay_control(
        CaptureRelayRequest(action="start", stream_name="external camera", open_obs=True)
    )

    assert result == {
        "schema_version": "capture_relay_control.v1",
        "status": "blocked",
        "reason": "relay_binary_missing",
    }
    assert captured["arguments"] == {
        "action": "start",
        "stream_name": "external camera",
        "scene_name": "Mindscape External Camera",
        "source_name": "Mindscape RTSP Source",
        "rtmp_port": 1935,
        "rtsp_port": 8554,
        "open_obs": True,
        "start_virtual_camera": True,
        "install_method": "homebrew",
        "timeout_ms": 5000,
    }


@pytest.mark.asyncio
async def test_call_capture_relay_control_accepts_mediamtx_install_action(monkeypatch):
    captured: dict[str, object] = {}

    async def fake_post_device_node_mcp(*, arguments, timeout_seconds):
        captured["arguments"] = arguments
        captured["timeout_seconds"] = timeout_seconds
        return {
            "content": [
                {
                    "type": "text",
                    "text": (
                        '{"schema_version":"capture_relay_control.v1",'
                        '"action":"install_mediamtx","install_result":"installed"}'
                    ),
                }
            ]
        }

    monkeypatch.setattr(
        capture_relay_proxy,
        "_post_device_node_mcp",
        fake_post_device_node_mcp,
    )

    result = await call_capture_relay_control(
        CaptureRelayRequest(
            action="install_mediamtx",
            stream_name="external camera",
            install_method="homebrew",
            timeout_ms=120000,
        )
    )

    assert result == {
        "schema_version": "capture_relay_control.v1",
        "action": "install_mediamtx",
        "install_result": "installed",
    }
    assert captured["arguments"] == {
        "action": "install_mediamtx",
        "stream_name": "external camera",
        "scene_name": "Mindscape External Camera",
        "source_name": "Mindscape RTSP Source",
        "rtmp_port": 1935,
        "rtsp_port": 8554,
        "open_obs": False,
        "start_virtual_camera": True,
        "install_method": "homebrew",
        "timeout_ms": 120000,
    }


@pytest.mark.asyncio
async def test_call_capture_relay_control_accepts_obs_configure_action(monkeypatch):
    captured: dict[str, object] = {}

    async def fake_post_device_node_mcp(*, arguments, timeout_seconds):
        captured["arguments"] = arguments
        captured["timeout_seconds"] = timeout_seconds
        return {
            "content": [
                {
                    "type": "text",
                    "text": (
                        '{"schema_version":"capture_relay_control.v1",'
                        '"action":"configure_obs","configure_result":"configured"}'
                    ),
                }
            ]
        }

    monkeypatch.setattr(
        capture_relay_proxy,
        "_post_device_node_mcp",
        fake_post_device_node_mcp,
    )

    result = await call_capture_relay_control(
        CaptureRelayRequest(
            action="configure_obs",
            stream_name="external camera",
            scene_name="Mindscape External Camera",
            source_name="Mindscape RTSP Source",
            timeout_ms=12000,
        )
    )

    assert result == {
        "schema_version": "capture_relay_control.v1",
        "action": "configure_obs",
        "configure_result": "configured",
    }
    assert captured["arguments"] == {
        "action": "configure_obs",
        "stream_name": "external camera",
        "scene_name": "Mindscape External Camera",
        "source_name": "Mindscape RTSP Source",
        "rtmp_port": 1935,
        "rtsp_port": 8554,
        "open_obs": False,
        "start_virtual_camera": True,
        "install_method": "homebrew",
        "timeout_ms": 12000,
    }


@pytest.mark.asyncio
async def test_call_capture_relay_control_rejects_non_json_text(monkeypatch):
    async def fake_post_device_node_mcp(*, arguments, timeout_seconds):
        return {"content": [{"type": "text", "text": "not-json"}]}

    monkeypatch.setattr(
        capture_relay_proxy,
        "_post_device_node_mcp",
        fake_post_device_node_mcp,
    )

    with pytest.raises(CaptureRelayUnavailable) as exc_info:
        await call_capture_relay_control(CaptureRelayRequest(action="status"))

    assert exc_info.value.reason == "capture_relay_invalid_json"


@pytest.mark.asyncio
async def test_receiver_start_timeout_includes_runtime_preflight_budget(monkeypatch):
    captured: dict[str, object] = {}

    async def fake_post_device_node_mcp(*, arguments, timeout_seconds):
        captured["arguments"] = arguments
        captured["timeout_seconds"] = timeout_seconds
        return {
            "content": [
                {
                    "type": "text",
                    "text": (
                        '{"schema_version":"live_media_receiver_control.v1",'
                        '"status":"active","state":"analyzing"}'
                    ),
                }
            ]
        }

    monkeypatch.setattr(
        capture_relay_proxy,
        "_post_device_node_mcp",
        fake_post_device_node_mcp,
    )

    result = await call_capture_relay_arguments(
        {"action": "receiver_start", "timeout_ms": 10000},
        timeout_ms=10000,
    )

    assert result["status"] == "active"
    assert captured["timeout_seconds"] == 105.0
