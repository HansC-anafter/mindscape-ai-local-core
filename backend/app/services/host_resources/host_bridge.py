"""Device Node host resource bridge."""

from __future__ import annotations

import json
import os
from typing import Any

import httpx


class HostBridgeError(Exception):
    """Raised when the host resource probe cannot be read."""


def device_node_url() -> str:
    return os.getenv("DEVICE_NODE_URL", "http://host.docker.internal:3100").rstrip("/")


async def _post_mcp(
    method: str,
    params: dict[str, Any] | None = None,
    *,
    timeout_seconds: float = 3.0,
) -> dict[str, Any]:
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params or {},
    }
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(
                f"{device_node_url()}/mcp",
                json=request,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "Mindscape-LocalCore/1.0",
                    "X-Request-Source": "host-resource-manager",
                },
            )
        payload = response.json()
    except Exception as exc:
        message = str(exc) or exc.__class__.__name__
        raise HostBridgeError(f"Device Node request failed: {message}") from exc

    if isinstance(payload, dict) and payload.get("error"):
        error = payload.get("error") or {}
        message = error.get("message") if isinstance(error, dict) else str(error)
        raise HostBridgeError(f"Device Node MCP error: {message}")
    result = payload.get("result") if isinstance(payload, dict) else None
    if not isinstance(result, dict):
        raise HostBridgeError("Device Node MCP result was not an object")
    return result


async def list_device_node_tools(*, timeout_seconds: float = 3.0) -> list[str]:
    result = await _post_mcp("tools/list", timeout_seconds=timeout_seconds)
    tools = result.get("tools")
    if not isinstance(tools, list):
        return []
    names: list[str] = []
    for tool in tools:
        if isinstance(tool, dict) and isinstance(tool.get("name"), str):
            names.append(tool["name"])
    return names


async def call_host_resource_probe(
    *,
    probe_timeout_ms: int = 1000,
    timeout_seconds: float = 4.0,
) -> dict[str, Any]:
    result = await _post_mcp(
        "tools/call",
        {
            "name": "host_resource_probe",
            "arguments": {
                "timeout_ms": probe_timeout_ms,
            },
        },
        timeout_seconds=timeout_seconds,
    )
    content = result.get("content")
    if not isinstance(content, list) or not content:
        raise HostBridgeError("host_resource_probe returned no content")
    text = content[0].get("text") if isinstance(content[0], dict) else None
    if not isinstance(text, str):
        raise HostBridgeError("host_resource_probe content was not text")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise HostBridgeError(f"host_resource_probe returned invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise HostBridgeError("host_resource_probe JSON was not an object")
    return payload
