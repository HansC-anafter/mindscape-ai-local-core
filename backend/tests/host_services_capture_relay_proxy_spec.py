from __future__ import annotations

import pytest

from backend.app.services.host_services import capture_relay_proxy
from backend.app.services.host_services.capture_relay_proxy import (
    CaptureRelayRequest,
    CaptureRelayUnavailable,
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
        "rtmp_port": 1935,
        "rtsp_port": 8554,
        "open_obs": True,
        "timeout_ms": 5000,
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
