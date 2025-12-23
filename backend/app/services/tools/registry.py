"""
Tool registry for managing tool implementations.

This registry maps tool types to their implementations (local/remote).
Also supports dynamic tool registration from ToolRegistryService.

Version 2: Supports new MindscapeTool architecture
- Backward compatible with legacy Tool class
- Supports new MindscapeTool implementations
"""
from typing import Dict, Type, Optional, List, Union
from backend.app.services.tools.base import Tool, MindscapeTool, ToolConnection

# Import tool implementations (Legacy)
from backend.app.services.tools.wordpress.wordpress_tool_v1 import WordPressTool

# Import WordPress tools (New MindscapeTool)
from backend.app.services.tools.wordpress.wordpress_tools import (
    create_wordpress_tools,
    get_wordpress_tool_by_name,
    validate_wp_connection
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
from backend.app.services.tools.github.github_tools import (
    create_github_tools,
    get_github_tool_by_name
)
from backend.app.services.tools.providers.sandbox_provider import create_sandbox_tools

# Remote tools are now provided by system capability packs in cloud repo
# This registry only handles local tools and generic mechanisms
REMOTE_TOOLS_AVAILABLE = False

# Tool priority classification
CORE_TOOLS = ["wordpress"]  # Core tools, must be fully implemented
THIRD_PARTY_TOOLS = ["notion", "google_drive", "github"]  # Third-party tools, BYO mode

# Static tool registry: maps tool_type -> connection_type -> Tool class
STATIC_TOOL_REGISTRY: Dict[str, Dict[str, Type[Tool]]] = {
    # Core tool: WordPress (must implement)
    "wordpress": {
        "local": WordPressTool,
        # Remote tools are provided by system capability packs in cloud repo
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
    Register a dynamically discovered tool (backward compatible)

    Args:
        registered_tool_id: Tool ID (e.g., "wp.site1.post.create_draft")
        connection: Tool connection configuration
    """
    _dynamic_tools[registered_tool_id] = connection


def unregister_dynamic_tool(registered_tool_id: str):
    """
    Unregister a dynamically discovered tool

    Args:
        registered_tool_id: Tool ID
    """
    if registered_tool_id in _dynamic_tools:
        del _dynamic_tools[registered_tool_id]
    if registered_tool_id in _mindscape_tools:
        del _mindscape_tools[registered_tool_id]


def register_mindscape_tool(tool_id: str, tool: MindscapeTool):
    """
    Register a new MindscapeTool instance

    Args:
        tool_id: Tool ID
        tool: MindscapeTool instance

    Example:
        >>> from backend.app.services.tools.wordpress.wordpress_tools import WordPressListPostsTool
        >>> tool = WordPressListPostsTool(connection)
        >>> register_mindscape_tool("wordpress.list_posts", tool)
    """
    _mindscape_tools[tool_id] = tool


def get_mindscape_tool(tool_id: str) -> Optional[MindscapeTool]:
    """
    Get MindscapeTool instance

    Args:
        tool_id: Tool ID

    Returns:
        MindscapeTool instance or None
    """
    return _mindscape_tools.get(tool_id)


def register_wordpress_v2_tools(connection: ToolConnection) -> List[MindscapeTool]:
    """
    Register all WordPress tools

    Args:
        connection: WordPress connection configuration

    Returns:
        List of registered tools

    Example:
        >>> wp_conn = ToolConnection(
        ...     id="my-wp",
        ...     tool_type="wordpress",
        ...     base_url="https://mysite.com",
        ...     api_key="admin",
        ...     api_secret="password"
        ... )
        >>> tools = register_wordpress_v2_tools(wp_conn)
        >>> print(f"Registered {len(tools)} tools")
    """
    tools = create_wordpress_tools(connection)

    for tool in tools:
        tool_id = f"{connection.id}.{tool.metadata.name}"
        register_mindscape_tool(tool_id, tool)

    return tools


def register_canva_tools(connection: ToolConnection) -> List[MindscapeTool]:
    """
    Register all Canva tools

    Args:
        connection: Canva connection configuration

    Returns:
        List of registered tools

    Example:
        >>> canva_conn = ToolConnection(
        ...     id="my-canva",
        ...     tool_type="canva",
        ...     api_key="api_key_here",
        ...     oauth_token="oauth_token_here",
        ...     base_url="https://api.canva.com/rest/v1"
        ... )
        >>> tools = register_canva_tools(canva_conn)
        >>> print(f"Registered {len(tools)} tools")
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


def register_sandbox_tools(store) -> List[MindscapeTool]:
    """
    Register all Sandbox tools

    Args:
        store: MindscapeStore instance

    Returns:
        List of registered tools

    Example:
        >>> from backend.app.services.mindscape_store import MindscapeStore
        >>> store = MindscapeStore()
        >>> tools = register_sandbox_tools(store)
        >>> print(f"Registered {len(tools)} sandbox tools")
    """
    tools = create_sandbox_tools(store)

    for tool in tools:
        tool_id = f"sandbox.{tool.metadata.name}"
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


def register_github_tools(connection: ToolConnection) -> List[MindscapeTool]:
    """
    Register all GitHub tools

    Args:
        connection: GitHub connection configuration

    Returns:
        List of registered tools

    Example:
        >>> github_conn = ToolConnection(
        ...     id="my-github",
        ...     tool_type="github",
        ...     api_key="ghp_...",
        ...     oauth_token="gho_..."
        ... )
        >>> tools = register_github_tools(github_conn)
        >>> print(f"Registered {len(tools)} tools")
    """
    access_token = connection.oauth_token or connection.api_key
    if not access_token:
        raise ValueError("GitHub access token is required (oauth_token or api_key)")

    tools = create_github_tools(access_token)

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
    Get all registered MindscapeTool instances

    Returns:
        Dictionary mapping tool_id to MindscapeTool
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


def register_filesystem_tools():
    """
    Register all local filesystem tools (builtin, no connection required)

    Returns:
        List of registered tools
    """
    import os
    from pathlib import Path
    from backend.app.services.tools.local_filesystem.filesystem_tools import (
        FilesystemListFilesTool,
        FilesystemReadFileTool,
        FilesystemWriteFileTool,
        FilesystemSearchTool
    )

    data_dir = os.getenv("DATA_DIR", "./data")
    default_base_dir = Path(data_dir) / "workspaces"

    tools = [
        FilesystemListFilesTool(base_directory=str(default_base_dir)),
        FilesystemReadFileTool(base_directory=str(default_base_dir)),
        FilesystemWriteFileTool(base_directory=str(default_base_dir)),
        FilesystemSearchTool(base_directory=str(default_base_dir))
    ]

    for tool in tools:
        tool_id = tool.metadata.name
        register_mindscape_tool(tool_id, tool)

    return tools


def register_ig_post_tools():
    """
    Register all IG Post tools (builtin, no connection required)

    Returns:
        List of registered tools
    """
    from backend.app.services.tools.ig_post.ig_post_tools import create_ig_post_tools

    tools = create_ig_post_tools()

    for tool in tools:
        tool_id = tool.metadata.name
        register_mindscape_tool(tool_id, tool)

    return tools


def register_unsplash_tools():
    """
    Register all Unsplash tools (builtin, proxy to Cloud API)

    Returns:
        List of registered tools
    """
    from backend.app.services.tools.unsplash import register_unsplash_tools as _register
    return _register()






def get_tool_metadata(tool_id: str) -> Optional[Dict]:
    """
    Get tool metadata

    Args:
        tool_id: Tool ID

    Returns:
        Tool metadata dictionary or None

    Example:
        >>> metadata = get_tool_metadata("wordpress.list_posts")
        >>> print(metadata["description"])
    """
    tool = get_mindscape_tool(tool_id)
    if tool:
        return tool.to_dict()
    return None

