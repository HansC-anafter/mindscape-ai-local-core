"""
Tool registry for managing tool implementations.

This registry maps tool types to their implementations (local/remote).
Also supports dynamic tool registration from ToolRegistryService.

Version 2: 支援新的 MindscapeTool 架構
- 向後兼容舊的 Tool 類
- 支援新的 MindscapeTool 工具
"""
from typing import Dict, Type, Optional, List, Union
from backend.app.services.tools.base import Tool, MindscapeTool, ToolConnection

# Import tool implementations (Legacy)
from backend.app.services.tools.wordpress.wordpress_tool import WordPressTool

# Import v2 tools (New MindscapeTool)
from backend.app.services.tools.wordpress.wordpress_tools_v2 import (
    create_wordpress_tools,
    get_wordpress_tool_by_name
)
from backend.app.services.tools.canva.canva_tools import (
    create_canva_tools,
    get_canva_tool_by_name
)
from backend.app.services.tools.slack.slack_tools import (
    create_slack_tools,
    get_slack_tool_by_name
)
from backend.app.services.tools.airtable.airtable_tools import (
    create_airtable_tools,
    get_airtable_tool_by_name
)
from backend.app.services.tools.google_sheets.google_sheets_tools import (
    create_google_sheets_tools,
    get_google_sheets_tool_by_name
)

# Tool priority classification
CORE_TOOLS = ["wordpress"]  # Core tools, must be fully implemented
THIRD_PARTY_TOOLS = ["notion", "google_drive", "github"]  # Third-party tools, BYO mode

# Static tool registry: maps tool_type -> connection_type -> Tool class
STATIC_TOOL_REGISTRY: Dict[str, Dict[str, Type[Tool]]] = {
    # Core tool: WordPress (must implement)
    "wordpress": {
        "local": WordPressTool,
        # "remote": RemoteWordPressTool,  # TODO: Implement for console-kit
    },
    # Third-party tools: BYO mode (provide connector only)
    # "notion": {
    #     "local": NotionTool,
    #     "remote": RemoteNotionTool,
    # },
    # "google_drive": {
    #     "local": GoogleDriveTool,
    #     "remote": RemoteGoogleDriveTool,
    # },
    # "github": {
    #     "local": GitHubTool,
    #     "remote": RemoteGitHubTool,
    # },
}

# Dynamic tool registry (from ToolRegistryService)
# Maps registered_tool_id -> ToolConnection
_dynamic_tools: Dict[str, ToolConnection] = {}

# New: MindscapeTool instances registry
# Maps tool_id -> MindscapeTool instance
_mindscape_tools: Dict[str, MindscapeTool] = {}


def get_tool(tool_type: str, connection_type: str, connection: ToolConnection) -> Tool:
    """Factory function to get tool instance"""
    if tool_type not in STATIC_TOOL_REGISTRY:
        raise ValueError(f"Unknown tool type: {tool_type}")

    if connection_type not in STATIC_TOOL_REGISTRY[tool_type]:
        raise ValueError(f"Connection type '{connection_type}' not supported for tool '{tool_type}'")

    tool_class = STATIC_TOOL_REGISTRY[tool_type][connection_type]
    return tool_class(connection)


def get_tool_by_registered_id(registered_tool_id: str) -> Optional[Tool]:
    """
    Get tool instance by registered tool ID.

    This is used for dynamically registered tools from ToolRegistryService.
    """
    connection = _dynamic_tools.get(registered_tool_id)
    if not connection:
        return None

    # Extract tool_type from registered_tool_id (e.g., "wp.my-site.post.create_draft" -> "wordpress")
    parts = registered_tool_id.split(".")
    if len(parts) < 2:
        return None

    tool_type = parts[0]  # "wp" -> "wordpress"
    if tool_type == "wp":
        tool_type = "wordpress"

    return get_tool(tool_type, "local", connection)


def register_dynamic_tool(registered_tool_id: str, connection: ToolConnection):
    """
    Register a dynamically discovered tool (向後兼容)

    Args:
        registered_tool_id: 工具 ID（如 "wp.site1.post.create_draft"）
        connection: 工具連接配置
    """
    _dynamic_tools[registered_tool_id] = connection


def unregister_dynamic_tool(registered_tool_id: str):
    """
    Unregister a dynamically discovered tool

    Args:
        registered_tool_id: 工具 ID
    """
    if registered_tool_id in _dynamic_tools:
        del _dynamic_tools[registered_tool_id]
    if registered_tool_id in _mindscape_tools:
        del _mindscape_tools[registered_tool_id]


def register_mindscape_tool(tool_id: str, tool: MindscapeTool):
    """
    註冊新版 MindscapeTool 實例

    Args:
        tool_id: 工具 ID
        tool: MindscapeTool 實例

    Example:
        >>> from backend.app.services.tools.wordpress.wordpress_tools_v2 import WordPressListPostsTool
        >>> tool = WordPressListPostsTool(connection)
        >>> register_mindscape_tool("wordpress.list_posts", tool)
    """
    _mindscape_tools[tool_id] = tool


def get_mindscape_tool(tool_id: str) -> Optional[MindscapeTool]:
    """
    獲取 MindscapeTool 實例

    Args:
        tool_id: 工具 ID

    Returns:
        MindscapeTool 實例或 None
    """
    return _mindscape_tools.get(tool_id)


def register_wordpress_v2_tools(connection: ToolConnection) -> List[MindscapeTool]:
    """
    註冊所有 WordPress v2 工具

    Args:
        connection: WordPress 連接配置

    Returns:
        已註冊的工具列表

    Example:
        >>> wp_conn = ToolConnection(
        ...     id="my-wp",
        ...     tool_type="wordpress",
        ...     base_url="https://mysite.com",
        ...     api_key="admin",
        ...     api_secret="password"
        ... )
        >>> tools = register_wordpress_v2_tools(wp_conn)
        >>> print(f"註冊了 {len(tools)} 個工具")
    """
    tools = create_wordpress_tools(connection)

    for tool in tools:
        tool_id = f"{connection.id}.{tool.metadata.name}"
        register_mindscape_tool(tool_id, tool)

    return tools


def register_canva_tools(connection: ToolConnection) -> List[MindscapeTool]:
    """
    註冊所有 Canva 工具

    Args:
        connection: Canva 連接配置

    Returns:
        已註冊的工具列表

    Example:
        >>> canva_conn = ToolConnection(
        ...     id="my-canva",
        ...     tool_type="canva",
        ...     api_key="api_key_here",
        ...     oauth_token="oauth_token_here",
        ...     base_url="https://api.canva.com/rest/v1"
        ... )
        >>> tools = register_canva_tools(canva_conn)
        >>> print(f"註冊了 {len(tools)} 個工具")
    """
    tools = create_canva_tools(connection)

    for tool in tools:
        tool_id = f"{connection.id}.{tool.metadata.name}"
        # Set allowed agent roles for Canva tools
        # Canva tools are useful for writers (content creators) and planners (presentations)
        # Note: ToolMetadata doesn't have allowed_agent_roles field by default,
        # but we can add it to the metadata if needed for tool filtering
        register_mindscape_tool(tool_id, tool)

    return tools


def register_slack_tools(connection: ToolConnection) -> List[MindscapeTool]:
    """
    Register all Slack tools

    Args:
        connection: Slack connection configuration

    Returns:
        List of registered tools

    Example:
        >>> slack_conn = ToolConnection(
        ...     id="my-slack",
        ...     tool_type="slack",
        ...     api_key="xoxb-...",
        ...     oauth_token="xoxb-..."
        ... )
        >>> tools = register_slack_tools(slack_conn)
        >>> print(f"Registered {len(tools)} tools")
    """
    access_token = connection.oauth_token or connection.api_key
    if not access_token:
        raise ValueError("Slack access token is required (oauth_token or api_key)")

    tools = create_slack_tools(access_token)

    for tool in tools:
        tool_id = f"{connection.id}.{tool.metadata.name}"
        register_mindscape_tool(tool_id, tool)

    return tools


def register_airtable_tools(connection: ToolConnection) -> List[MindscapeTool]:
    """
    Register all Airtable tools

    Args:
        connection: Airtable connection configuration

    Returns:
        List of registered tools

    Example:
        >>> airtable_conn = ToolConnection(
        ...     id="my-airtable",
        ...     tool_type="airtable",
        ...     api_key="pat..."
        ... )
        >>> tools = register_airtable_tools(airtable_conn)
        >>> print(f"Registered {len(tools)} tools")
    """
    api_key = connection.api_key
    if not api_key:
        raise ValueError("Airtable API key is required")

    tools = create_airtable_tools(api_key)

    for tool in tools:
        tool_id = f"{connection.id}.{tool.metadata.name}"
        register_mindscape_tool(tool_id, tool)

    return tools


def register_google_sheets_tools(connection: ToolConnection) -> List[MindscapeTool]:
    """
    Register all Google Sheets tools

    Args:
        connection: Google Sheets connection configuration

    Returns:
        List of registered tools

    Example:
        >>> sheets_conn = ToolConnection(
        ...     id="my-sheets",
        ...     tool_type="google_sheets",
        ...     api_key="ya29...",
        ...     oauth_token="ya29..."
        ... )
        >>> tools = register_google_sheets_tools(sheets_conn)
        >>> print(f"Registered {len(tools)} tools")
    """
    access_token = connection.oauth_token or connection.api_key
    if not access_token:
        raise ValueError("Google Sheets access token is required (oauth_token or api_key)")

    tools = create_google_sheets_tools(access_token)

    for tool in tools:
        tool_id = f"{connection.id}.{tool.metadata.name}"
        register_mindscape_tool(tool_id, tool)

    return tools


def get_dynamic_tools_for_site(site_id: str) -> List[str]:
    """Get all registered tool IDs for a site"""
    return [
        tool_id for tool_id in _dynamic_tools.keys()
        if tool_id.startswith(f"wp.{site_id}.")
    ]


def is_core_tool(tool_type: str) -> bool:
    """Check if tool is a core tool (WordPress)"""
    return tool_type in CORE_TOOLS


def get_available_tools() -> Dict[str, Dict[str, bool]]:
    """Get list of available tools and their connection types"""
    return {
        tool_type: {
            connection_type: True
            for connection_type in implementations.keys()
        }
        for tool_type, implementations in STATIC_TOOL_REGISTRY.items()
    }


def get_all_mindscape_tools() -> Dict[str, MindscapeTool]:
    """
    獲取所有已註冊的 MindscapeTool

    Returns:
        {tool_id: MindscapeTool} 字典
    """
    return _mindscape_tools.copy()


def register_workspace_tools():
    """
    Register all workspace tools (builtin, no connection required)

    Returns:
        List of registered tools
    """
    from backend.app.services.tools.workspace_tools import create_workspace_tools

    tools = create_workspace_tools()

    for tool in tools:
        tool_id = tool.metadata.name
        register_mindscape_tool(tool_id, tool)
        # Also register with dot notation for backward compatibility (workspace_get_execution -> workspace.get_execution)
        dot_notation_id = tool_id.replace("workspace_", "workspace.")
        register_mindscape_tool(dot_notation_id, tool)

    return tools


def get_tool_metadata(tool_id: str) -> Optional[Dict]:
    """
    獲取工具的 metadata

    Args:
        tool_id: 工具 ID

    Returns:
        工具 metadata dict 或 None

    Example:
        >>> metadata = get_tool_metadata("wordpress.list_posts")
        >>> print(metadata["description"])
    """
    tool = get_mindscape_tool(tool_id)
    if tool:
        return tool.to_dict()
    return None

