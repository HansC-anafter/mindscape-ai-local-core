"""Tool query helpers for ToolRegistryService."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from backend.app.models.tool_registry import RegisteredTool
from backend.app.services.tools.discovery_provider import ToolDiscoveryProvider


def get_available_provider_metadata(
    discovery_providers: Dict[str, ToolDiscoveryProvider],
) -> List[Dict[str, Any]]:
    """Return provider metadata for UI display."""
    return [
        provider.get_discovery_metadata()
        for provider in discovery_providers.values()
    ]


def get_tools(
    tools_by_id: Dict[str, RegisteredTool],
    *,
    site_id: Optional[str] = None,
    category: Optional[str] = None,
    enabled_only: bool = True,
    scope: Optional[str] = None,
    tenant_id: Optional[str] = None,
    profile_id: Optional[str] = None,
    workspace_id: Optional[str] = None,
) -> List[RegisteredTool]:
    """Return registered tools with scope and overlay filtering."""
    tools = list(tools_by_id.values())

    if site_id:
        tools = [tool for tool in tools if tool.site_id == site_id]
    if category:
        tools = [tool for tool in tools if tool.category == category]
    if enabled_only:
        tools = [tool for tool in tools if tool.enabled]
    if scope:
        tools = [tool for tool in tools if tool.scope == scope]
    if tenant_id:
        tools = [tool for tool in tools if tool.tenant_id == tenant_id]

    if profile_id:
        tools = [
            tool
            for tool in tools
            if (
                tool.scope == "system"
                or (tool.scope == "tenant" and tool.tenant_id == tenant_id)
                or (tool.scope == "profile" and tool.owner_profile_id == profile_id)
            )
        ]

    if workspace_id:
        from backend.app.services.tool_overlay_service import ToolOverlayService

        overlay_service = ToolOverlayService()
        tools = overlay_service.apply_tools_overlay(tools, workspace_id)

    return tools


def get_tool(
    tools_by_id: Dict[str, RegisteredTool],
    tool_id: str,
) -> Optional[RegisteredTool]:
    """Return a single tool from the registry cache."""
    return tools_by_id.get(tool_id)


def update_tool(
    tools_by_id: Dict[str, RegisteredTool],
    *,
    save_registry: Callable[[], None],
    tool_id: str,
    enabled: Optional[bool] = None,
    read_only: Optional[bool] = None,
    allowed_agent_roles: Optional[List[str]] = None,
) -> Optional[RegisteredTool]:
    """Update mutable tool flags and persist the registry."""
    tool = tools_by_id.get(tool_id)
    if not tool:
        return None

    if enabled is not None:
        tool.enabled = enabled
    if read_only is not None:
        tool.read_only = read_only
    if allowed_agent_roles is not None:
        tool.allowed_agent_roles = allowed_agent_roles

    tool.updated_at = datetime.now()
    save_registry()
    return tool


def get_tools_for_agent_role(
    *,
    get_tools_fn: Callable[..., List[RegisteredTool]],
    agent_role: str,
    profile_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    workspace_id: Optional[str] = None,
) -> List[RegisteredTool]:
    """Return enabled tools available to the requested agent role."""
    tools = get_tools_fn(
        enabled_only=True,
        profile_id=profile_id,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
    )

    filtered_tools = []
    for tool in tools:
        if tool.allowed_agent_roles and agent_role not in tool.allowed_agent_roles:
            continue
        filtered_tools.append(tool)

    return filtered_tools


def infer_side_effect_level(
    provider_name: str,
    danger_level: str,
    tool_id: str,
    methods: List[str],
) -> str:
    """Infer the tool side-effect level from provider and method metadata."""
    if methods and all(method.upper() in ["GET"] for method in methods):
        return "readonly"

    provider_lower = provider_name.lower()
    if provider_lower in ["wordpress", "notion", "google_drive"]:
        if any(
            keyword in tool_id.lower() for keyword in ["read", "list", "search", "get"]
        ):
            return "readonly"
        return "external_write"

    if provider_lower == "local_filesystem":
        if any(keyword in tool_id.lower() for keyword in ["read", "list", "search"]):
            return "readonly"
        return "external_write"

    if danger_level == "high":
        return "external_write"

    return "soft_write"
