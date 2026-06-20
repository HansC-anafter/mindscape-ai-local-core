"""
WordPress Tools Collection

This module is the canonical public facade for WordPress MindscapeTool classes.
"""

from typing import List

from backend.app.services.tools.base import MindscapeTool, ToolConnection
from backend.app.services.tools.wordpress.wordpress_client import (
    _init_wp_client_from_connection,
    validate_wp_connection,
)
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
from backend.app.services.tools.wordpress.wordpress_plugin_tools import (
    WordPressCallPluginEndpointTool,
)


def create_wordpress_tools(connection: ToolConnection) -> List[MindscapeTool]:
    """
    Create all WordPress tool instances.

    Args:
        connection: WordPress connection configuration

    Returns:
        List of WordPress tools
    """
    return [
        WordPressListPostsTool(connection),
        WordPressGetPostTool(connection),
        WordPressCreateDraftTool(connection),
        WordPressUpdatePostTool(connection),
        WordPressListOrdersTool(connection),
        WordPressUpdateOrderStatusTool(connection),
        WordPressCallPluginEndpointTool(connection),
    ]


def get_wordpress_tool_by_name(
    connection: ToolConnection,
    tool_name: str,
) -> MindscapeTool:
    """
    Get a specific WordPress tool by name.

    Args:
        connection: WordPress connection
        tool_name: Tool name

    Returns:
        Tool instance

    Raises:
        ValueError: Unknown tool name
    """
    tool_map = {
        "wordpress.list_posts": WordPressListPostsTool,
        "wordpress.get_post": WordPressGetPostTool,
        "wordpress.create_draft": WordPressCreateDraftTool,
        "wordpress.update_post": WordPressUpdatePostTool,
        "wordpress.list_orders": WordPressListOrdersTool,
        "wordpress.update_order_status": WordPressUpdateOrderStatusTool,
        "wordpress.call_plugin_endpoint": WordPressCallPluginEndpointTool,
    }

    tool_class = tool_map.get(tool_name)
    if not tool_class:
        available = list(tool_map.keys())
        raise ValueError(
            f"Unknown tool name: {tool_name}. "
            f"Available tools: {', '.join(available)}"
        )

    return tool_class(connection)
