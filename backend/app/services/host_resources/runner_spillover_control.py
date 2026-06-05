"""Runner spillover lifecycle control through Device Node."""

from __future__ import annotations

from typing import Any

from .host_bridge import (
    HostBridgeError,
    call_host_resource_runner_spillover_control,
    list_device_node_tools,
)


TOOL_NAME = "host_resource_runner_spillover_control"
ALLOWED_ACTIONS = {"status", "start", "stop"}
ALLOWED_PROFILES = {"default_local", "browser_local", "vision_local"}


def _clean_string(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _clean_action(value: Any) -> str:
    action = _clean_string(value, "status")
    if action not in ALLOWED_ACTIONS:
        raise ValueError("unsupported_spillover_action")
    return action


def _clean_profile(value: Any) -> str:
    profile = _clean_string(value, "default_local")
    if profile not in ALLOWED_PROFILES:
        raise ValueError("unsupported_spillover_profile")
    return profile


def _clean_max_inflight(value: Any) -> int:
    try:
        parsed = int(value or 1)
    except (TypeError, ValueError):
        parsed = 1
    return min(max(parsed, 1), 4)


async def runner_spillover_status() -> dict[str, Any]:
    return await runner_spillover_action({"action": "status"})


async def runner_spillover_action(payload: dict[str, Any] | None) -> dict[str, Any]:
    body = payload or {}
    action = _clean_action(body.get("action"))
    profile = _clean_profile(body.get("profile_code"))
    max_inflight = _clean_max_inflight(body.get("max_inflight"))
    try:
        tool_names = await list_device_node_tools(timeout_seconds=3.0)
    except HostBridgeError as exc:
        return {
            "accepted": False,
            "reason": "device_node_unavailable",
            "error": str(exc),
            "action": action,
            "profile_code": profile,
            "max_inflight": max_inflight,
        }
    if TOOL_NAME not in tool_names:
        return {
            "accepted": False,
            "reason": "spillover_control_tool_unavailable",
            "action": action,
            "profile_code": profile,
            "max_inflight": max_inflight,
            "required_tool": TOOL_NAME,
            "available_tools": tool_names,
        }
    try:
        result = await call_host_resource_runner_spillover_control(
            {
                "action": action,
                "profile_code": profile,
                "max_inflight": max_inflight,
            }
        )
    except HostBridgeError as exc:
        return {
            "accepted": False,
            "reason": "spillover_control_failed",
            "error": str(exc),
            "action": action,
            "profile_code": profile,
            "max_inflight": max_inflight,
        }
    return {
        "accepted": bool(result.get("accepted")),
        "action": action,
        "profile_code": profile,
        "max_inflight": max_inflight,
        "result": result,
    }
