"""Lookup and shared-state helpers for the tools registry."""

from typing import Dict, List, Optional

from backend.app.services.tools.base import MindscapeTool, Tool, ToolConnection
from backend.app.services.tools.registry_core.state import (
    CORE_TOOLS,
    STATIC_TOOL_REGISTRY,
    _dynamic_tools,
    _mindscape_tools,
)


def get_tool(tool_type: str, connection_type: str, connection: ToolConnection) -> Tool:
    """Create a legacy tool instance."""
    if tool_type not in STATIC_TOOL_REGISTRY:
        raise ValueError(f"Unknown tool type: {tool_type}")

    if connection_type not in STATIC_TOOL_REGISTRY[tool_type]:
        raise ValueError(
            f"Connection type '{connection_type}' not supported for tool '{tool_type}'"
        )

    tool_class = STATIC_TOOL_REGISTRY[tool_type][connection_type]
    return tool_class(connection)


def get_tool_by_registered_id(registered_tool_id: str) -> Optional[Tool]:
    """Get a legacy tool instance by registered tool ID."""
    connection = _dynamic_tools.get(registered_tool_id)
    if not connection:
        return None

    parts = registered_tool_id.split(".")
    if len(parts) < 2:
        return None

    tool_type = parts[0]
    if tool_type == "wp":
        tool_type = "wordpress"

    return get_tool(tool_type, "local", connection)


def register_dynamic_tool(registered_tool_id: str, connection: ToolConnection):
    """Register a dynamically discovered legacy tool connection."""
    _dynamic_tools[registered_tool_id] = connection


def unregister_dynamic_tool(registered_tool_id: str):
    """Remove a dynamically discovered tool from all in-process registries."""
    if registered_tool_id in _dynamic_tools:
        del _dynamic_tools[registered_tool_id]
    if registered_tool_id in _mindscape_tools:
        del _mindscape_tools[registered_tool_id]


def register_mindscape_tool(tool_id: str, tool: MindscapeTool):
    """Register a MindscapeTool instance."""
    _mindscape_tools[tool_id] = tool


def get_mindscape_tool(tool_id: str) -> Optional[MindscapeTool]:
    """Get a MindscapeTool instance."""
    return _mindscape_tools.get(tool_id)


def get_dynamic_tools_for_site(site_id: str) -> List[str]:
    """Get all registered tool IDs for a WordPress site."""
    return [
        tool_id
        for tool_id in _dynamic_tools.keys()
        if tool_id.startswith(f"wp.{site_id}.")
    ]


def is_core_tool(tool_type: str) -> bool:
    """Check whether a tool type is a core tool."""
    return tool_type in CORE_TOOLS


def get_available_tools() -> Dict[str, Dict[str, bool]]:
    """Get available legacy tools and their connection types."""
    return {
        tool_type: {connection_type: True for connection_type in implementations.keys()}
        for tool_type, implementations in STATIC_TOOL_REGISTRY.items()
    }


def get_all_mindscape_tools(
    *,
    include_internal: bool = False,
) -> Dict[str, MindscapeTool]:
    """Get registered tools, excluding runner-internal tools by default."""

    if include_internal:
        return _mindscape_tools.copy()
    return {
        tool_id: tool
        for tool_id, tool in _mindscape_tools.items()
        if not bool(getattr(tool.metadata, "internal", False))
    }


def get_tool_metadata(tool_id: str) -> Optional[Dict]:
    """Get registered tool metadata."""
    tool = get_mindscape_tool(tool_id)
    if tool:
        return tool.to_dict()
    return None
