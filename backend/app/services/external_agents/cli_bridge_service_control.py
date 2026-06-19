"""Host-side CLI bridge service control through Device Node."""

from __future__ import annotations

import json
import os
from typing import Any, Literal

import httpx

BridgeAction = Literal["status", "start", "restart"]
TOOL_NAME = "cli_bridge_service_control"


def _device_node_url() -> str:
    return os.getenv("DEVICE_NODE_URL", "http://host.docker.internal:3100").rstrip("/")


def _fallback_status(
    *,
    action: BridgeAction,
    state: str,
    message: str,
    reason: str | None = None,
) -> dict[str, Any]:
    return {
        "service": "cli_bridge",
        "label": "ai.mindscape.cli-bridge",
        "action": action,
        "supported": False,
        "installed": False,
        "loaded": False,
        "running": False,
        "state": state,
        "auto_recovery": False,
        "reason": reason,
        "message": message,
    }


async def _post_mcp(
    method: str,
    params: dict[str, Any] | None = None,
    *,
    timeout_seconds: float = 4.0,
) -> dict[str, Any]:
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params or {},
    }
    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        response = await client.post(
            f"{_device_node_url()}/mcp",
            json=request,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "Mindscape-LocalCore/1.0",
                "X-Request-Source": "cli-bridge-service-control",
            },
        )
    payload = response.json()
    if isinstance(payload, dict) and payload.get("error"):
        error = payload.get("error") or {}
        message = error.get("message") if isinstance(error, dict) else str(error)
        raise RuntimeError(message or "Device Node MCP error")
    result = payload.get("result") if isinstance(payload, dict) else None
    if not isinstance(result, dict):
        raise RuntimeError("Device Node MCP result was not an object")
    return result


def _decode_tool_payload(result: dict[str, Any]) -> dict[str, Any]:
    content = result.get("content")
    if not isinstance(content, list) or not content:
        raise RuntimeError("Device Node tool returned no content")
    text = content[0].get("text") if isinstance(content[0], dict) else None
    if not isinstance(text, str):
        raise RuntimeError("Device Node tool content was not text")
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise RuntimeError("Device Node tool JSON was not an object")
    return payload


async def get_cli_bridge_service_status(action: BridgeAction = "status") -> dict[str, Any]:
    try:
        result = await _post_mcp(
            "tools/call",
            {
                "name": TOOL_NAME,
                "arguments": {
                    "action": action,
                },
            },
            timeout_seconds=12.0 if action in {"start", "restart"} else 4.0,
        )
        payload = _decode_tool_payload(result)
        payload.setdefault("action", action)
        payload.setdefault("service", "cli_bridge")
        return payload
    except (httpx.HTTPError, TimeoutError) as exc:
        return _fallback_status(
            action=action,
            state="device_node_unavailable",
            reason="device_node_unavailable",
            message=f"Device Node is unreachable: {exc}",
        )
    except Exception as exc:
        message = str(exc) or exc.__class__.__name__
        if "Unknown tool" in message:
            return _fallback_status(
                action=action,
                state="unsupported_tool",
                reason="device_node_tool_missing",
                message="Device Node is running but does not expose cli_bridge_service_control.",
            )
        return _fallback_status(
            action=action,
            state="control_failed",
            reason="device_node_control_failed",
            message=message,
        )
