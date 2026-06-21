"""
WordPress tools v2 compatibility facade.

The canonical WordPress implementation lives in the split wordpress_tools
modules. This module keeps the legacy v2 import surface and six-tool factory.
"""

from __future__ import annotations

from typing import Dict, List, Type

from backend.app.services.tools.base import MindscapeTool, ToolConnection
from backend.app.services.tools.wordpress.wordpress_commerce_tools import (
    WordPressListOrdersTool,
    WordPressUpdateOrderStatusTool,
)
from backend.app.services.tools.wordpress.wordpress_content_tools import (
    WordPressCreateDraftTool,
    WordPressGetPostTool,
    WordPressListPostsTool,
    WordPressUpdatePostTool,
)


V2_TOOL_CLASSES: List[Type[MindscapeTool]] = [
    WordPressListPostsTool,
    WordPressGetPostTool,
    WordPressCreateDraftTool,
    WordPressUpdatePostTool,
    WordPressListOrdersTool,
    WordPressUpdateOrderStatusTool,
]

V2_TOOL_MAP: Dict[str, Type[MindscapeTool]] = {
    "wordpress.list_posts": WordPressListPostsTool,
    "wordpress.get_post": WordPressGetPostTool,
    "wordpress.create_draft": WordPressCreateDraftTool,
    "wordpress.update_post": WordPressUpdatePostTool,
    "wordpress.list_orders": WordPressListOrdersTool,
    "wordpress.update_order_status": WordPressUpdateOrderStatusTool,
}


def create_wordpress_tools(connection: ToolConnection) -> List[MindscapeTool]:
    """
    Create the legacy v2 WordPress tool set.

    Args:
        connection: WordPress connection configuration

    Returns:
        List of v2-compatible WordPress tools
    """
    return [tool_class(connection) for tool_class in V2_TOOL_CLASSES]


def get_wordpress_tool_by_name(
    connection: ToolConnection,
    tool_name: str,
) -> MindscapeTool:
    """
    Get a legacy v2 WordPress tool by name.

    Args:
        connection: WordPress connection configuration
        tool_name: Tool name

    Returns:
        Tool instance

    Raises:
        ValueError: Unknown tool name
    """
    tool_class = V2_TOOL_MAP.get(tool_name)
    if not tool_class:
        available = list(V2_TOOL_MAP.keys())
        raise ValueError(
            f"Unknown tool name: {tool_name}. "
            f"Available tools: {', '.join(available)}"
        )

    return tool_class(connection)


__all__ = [
    "WordPressCreateDraftTool",
    "WordPressGetPostTool",
    "WordPressListOrdersTool",
    "WordPressListPostsTool",
    "WordPressUpdateOrderStatusTool",
    "WordPressUpdatePostTool",
    "create_wordpress_tools",
    "get_wordpress_tool_by_name",
]
