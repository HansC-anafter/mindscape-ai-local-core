"""Provider-backed registration helpers for the tools registry."""

from typing import List

from backend.app.services.tools.airtable.airtable_tools import (
    create_airtable_tools,
    get_airtable_tool_by_name,
)
from backend.app.services.tools.base import MindscapeTool, ToolConnection
from backend.app.services.tools.github.github_tools import (
    create_github_tools,
    get_github_tool_by_name,
)
from backend.app.services.tools.google_sheets.google_sheets_tools import (
    create_google_sheets_tools,
    get_google_sheets_tool_by_name,
)
from backend.app.services.tools.providers.sandbox_provider import create_sandbox_tools
from backend.app.services.tools.registry_core.dynamic import register_mindscape_tool
from backend.app.services.tools.slack.slack_tools import (
    create_slack_tools,
    get_slack_tool_by_name,
)
from backend.app.services.tools.wordpress.wordpress_tools import (
    create_wordpress_tools,
    get_wordpress_tool_by_name,
    validate_wp_connection,
)


def register_wordpress_v2_tools(connection: ToolConnection) -> List[MindscapeTool]:
    """Register all WordPress MindscapeTool instances."""
    tools = create_wordpress_tools(connection)

    for tool in tools:
        tool_id = f"{connection.id}.{tool.metadata.name}"
        register_mindscape_tool(tool_id, tool)

    return tools


def register_sandbox_tools(store) -> List[MindscapeTool]:
    """Register all Sandbox MindscapeTool instances."""
    tools = create_sandbox_tools(store)

    for tool in tools:
        tool_id = f"sandbox.{tool.metadata.name}"
        register_mindscape_tool(tool_id, tool)

    return tools


def register_slack_tools(connection: ToolConnection) -> List[MindscapeTool]:
    """Register all Slack MindscapeTool instances."""
    access_token = connection.oauth_token or connection.api_key
    if not access_token:
        raise ValueError("Slack access token is required (oauth_token or api_key)")

    tools = create_slack_tools(access_token)

    for tool in tools:
        tool_id = f"{connection.id}.{tool.metadata.name}"
        register_mindscape_tool(tool_id, tool)

    return tools


def register_airtable_tools(connection: ToolConnection) -> List[MindscapeTool]:
    """Register all Airtable MindscapeTool instances."""
    api_key = connection.api_key
    if not api_key:
        raise ValueError("Airtable API key is required")

    tools = create_airtable_tools(api_key)

    for tool in tools:
        tool_id = f"{connection.id}.{tool.metadata.name}"
        register_mindscape_tool(tool_id, tool)

    return tools


def register_google_sheets_tools(connection: ToolConnection) -> List[MindscapeTool]:
    """Register all Google Sheets MindscapeTool instances."""
    access_token = connection.oauth_token or connection.api_key
    if not access_token:
        raise ValueError(
            "Google Sheets access token is required (oauth_token or api_key)"
        )

    tools = create_google_sheets_tools(access_token)

    for tool in tools:
        tool_id = f"{connection.id}.{tool.metadata.name}"
        register_mindscape_tool(tool_id, tool)

    return tools


def register_github_tools(connection: ToolConnection) -> List[MindscapeTool]:
    """Register all GitHub MindscapeTool instances."""
    access_token = connection.oauth_token or connection.api_key
    if not access_token:
        raise ValueError("GitHub access token is required (oauth_token or api_key)")

    tools = create_github_tools(access_token)

    for tool in tools:
        tool_id = f"{connection.id}.{tool.metadata.name}"
        register_mindscape_tool(tool_id, tool)

    return tools
