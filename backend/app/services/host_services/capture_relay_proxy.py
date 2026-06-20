"""Capture relay proxy through Device Node."""

from __future__ import annotations

import json
import os
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field


class CaptureRelayUnavailable(Exception):
    """Raised when Device Node capture relay control is unavailable."""

    def __init__(self, reason: str, detail: dict[str, Any] | None = None) -> None:
        self.reason = reason
        self.detail = detail or {"reason": reason}
        super().__init__(reason)

    def to_detail(self) -> dict[str, Any]:
        return self.detail


class CaptureRelayRequest(BaseModel):
    """Request model for the host capture relay helper."""

    action: Literal["status", "start", "stop", "open_obs"] = "status"
    stream_name: str = Field(default="external-camera", max_length=128)
    rtmp_port: int = Field(default=1935, ge=1, le=65535)
    rtsp_port: int = Field(default=8554, ge=1, le=65535)
    open_obs: bool = False
    timeout_ms: int = Field(default=5000, ge=1000, le=15000)


def _device_node_url() -> str:
    return os.getenv("DEVICE_NODE_URL", "http://host.docker.internal:3100").rstrip("/")


async def _post_device_node_mcp(
    *,
    arguments: dict[str, Any],
    timeout_seconds: float,
) -> dict[str, Any]:
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "capture_relay_control",
            "arguments": arguments,
        },
    }
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(
                f"{_device_node_url()}/mcp",
                json=request,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "Mindscape-LocalCore/1.0",
                    "X-Request-Source": "capture-relay-control",
                },
            )
    except httpx.TimeoutException as exc:
        raise CaptureRelayUnavailable(
            "device_node_capture_relay_timeout",
            {"reason": "device_node_capture_relay_timeout"},
        ) from exc
    except httpx.HTTPError as exc:
        raise CaptureRelayUnavailable(
            "device_node_unreachable",
            {"reason": "device_node_unreachable", "message": str(exc)},
        ) from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise CaptureRelayUnavailable(
            "device_node_invalid_response",
            {"reason": "device_node_invalid_response"},
        ) from exc

    if response.status_code >= 400:
        raise CaptureRelayUnavailable(
            "device_node_http_error",
            {"reason": "device_node_http_error", "status_code": response.status_code},
        )
    if isinstance(payload, dict) and payload.get("error"):
        error = payload.get("error")
        message = error.get("message") if isinstance(error, dict) else str(error)
        raise CaptureRelayUnavailable(
            "device_node_mcp_error",
            {"reason": "device_node_mcp_error", "message": message},
        )
    if not isinstance(payload, dict):
        raise CaptureRelayUnavailable(
            "device_node_invalid_response",
            {"reason": "device_node_invalid_response"},
        )
    result = payload.get("result")
    if not isinstance(result, dict):
        raise CaptureRelayUnavailable(
            "device_node_invalid_result",
            {"reason": "device_node_invalid_result"},
        )
    return result


def _parse_mcp_text_result(result: dict[str, Any]) -> dict[str, Any]:
    content = result.get("content")
    if not isinstance(content, list) or not content:
        raise CaptureRelayUnavailable(
            "capture_relay_empty_result",
            {"reason": "capture_relay_empty_result"},
        )
    first = content[0]
    text = first.get("text") if isinstance(first, dict) else None
    if not isinstance(text, str):
        raise CaptureRelayUnavailable(
            "capture_relay_non_text_result",
            {"reason": "capture_relay_non_text_result"},
        )
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CaptureRelayUnavailable(
            "capture_relay_invalid_json",
            {"reason": "capture_relay_invalid_json"},
        ) from exc
    if not isinstance(parsed, dict):
        raise CaptureRelayUnavailable(
            "capture_relay_invalid_payload",
            {"reason": "capture_relay_invalid_payload"},
        )
    return parsed


async def call_capture_relay_control(
    request: CaptureRelayRequest,
) -> dict[str, Any]:
    result = await _post_device_node_mcp(
        arguments=request.model_dump(mode="json"),
        timeout_seconds=(request.timeout_ms / 1000) + 5,
    )
    return _parse_mcp_text_result(result)


__all__ = [
    "CaptureRelayRequest",
    "CaptureRelayUnavailable",
    "call_capture_relay_control",
]
