"""Builtin registration helpers for the tools registry."""

from typing import List, Optional

from backend.app.services.tools.base import MindscapeTool
from backend.app.services.tools.registry_core.dynamic import register_mindscape_tool


def register_workspace_tools():
    """Register all workspace tools."""
    from backend.app.services.tools.workspace_tools import create_workspace_tools

    tools = create_workspace_tools()

    for tool in tools:
        tool_id = tool.metadata.name
        register_mindscape_tool(tool_id, tool)
        dot_notation_id = tool_id.replace("workspace_", "workspace.")
        register_mindscape_tool(dot_notation_id, tool)

    return tools


def register_filesystem_tools():
    """Register all local filesystem tools."""
    import os
    from pathlib import Path

    from backend.app.services.tools.local_filesystem.filesystem_tools import (
        FilesystemListFilesTool,
        FilesystemReadFileTool,
        FilesystemSearchTool,
        FilesystemWriteFileTool,
    )

    data_dir = os.getenv("DATA_DIR", "./data")
    default_base_dir = Path(data_dir) / "workspaces"

    tools = [
        FilesystemListFilesTool(base_directory=str(default_base_dir)),
        FilesystemReadFileTool(base_directory=str(default_base_dir)),
        FilesystemWriteFileTool(base_directory=str(default_base_dir)),
        FilesystemSearchTool(base_directory=str(default_base_dir)),
    ]

    for tool in tools:
        tool_id = tool.metadata.name
        register_mindscape_tool(tool_id, tool)

    return tools


def register_ig_post_tools():
    """Register all IG Post tools."""
    from backend.app.services.tools.ig_post.ig_post_tools import create_ig_post_tools

    tools = create_ig_post_tools()

    for tool in tools:
        tool_id = tool.metadata.name
        register_mindscape_tool(tool_id, tool)

    return tools


def register_unsplash_tools():
    """Register all Unsplash tools."""
    from backend.app.services.tools.unsplash import register_unsplash_tools as _register

    return _register()


def register_content_vault_tools(vault_path: Optional[str] = None):
    """Register all Content Vault tools."""
    import os
    from pathlib import Path

    from backend.app.services.tools.content_vault.vault_tools import (
        ContentVaultBuildPromptTool,
        ContentVaultLoadContextTool,
        ContentVaultMergeContextTool,
        ContentVaultWritePostsTool,
    )

    if vault_path is None:
        vault_path = os.getenv("CONTENT_VAULT_PATH") or str(
            Path.home() / "content-vault"
        )

    tools = [
        ContentVaultLoadContextTool(vault_path),
        ContentVaultBuildPromptTool(),
        ContentVaultWritePostsTool(vault_path),
        ContentVaultMergeContextTool(vault_path),
    ]

    for tool in tools:
        tool_id = tool.metadata.name
        register_mindscape_tool(tool_id, tool)

    return tools


def register_mindscape_graph_tools() -> List[MindscapeTool]:
    """Register all Mindscape Graph tools."""
    from backend.app.services.tools.mindscape_graph import get_all_tools

    tools = get_all_tools()

    for tool in tools:
        tool_id = tool.metadata.name
        register_mindscape_tool(tool_id, tool)

    return tools


def register_reporting_tools() -> List[MindscapeTool]:
    """Register workspace reporting tools."""
    from backend.app.services.tools.reporting import create_reporting_tools

    tools = create_reporting_tools()

    for tool in tools:
        tool_id = tool.metadata.name
        register_mindscape_tool(tool_id, tool)
        register_mindscape_tool(f"core.{tool_id}", tool)

    return tools


def register_knowledge_query_tool() -> MindscapeTool:
    """Register exactly one public authorization-aware knowledge tool."""

    from backend.app.services.tools.knowledge_query import (
        create_knowledge_query_tool,
    )

    tool = create_knowledge_query_tool()
    register_mindscape_tool("knowledge_query", tool)
    return tool


def register_internal_knowledge_projection_tool() -> MindscapeTool:
    """Register the runner-only tool; public registry lists filter it out."""

    from backend.app.services.tools.knowledge_project_source import (
        create_knowledge_project_source_tool,
    )

    tool = create_knowledge_project_source_tool()
    register_mindscape_tool(tool.metadata.name, tool)
    return tool


def register_meeting_planner_tools() -> List[MindscapeTool]:
    """Register MeetingEngine planner tools."""
    from backend.app.services.tools.meeting_planner import create_meeting_planner_tools

    tools = create_meeting_planner_tools()

    for tool in tools:
        tool_id = tool.metadata.name
        register_mindscape_tool(tool_id, tool)

    return tools


def register_external_agent_tools() -> List[MindscapeTool]:
    """Register all external agent tools."""
    from backend.app.services.tools.external_agent_wrapper import (
        ExternalAgentCheckTool,
        ExternalAgentExecuteTool,
        ExternalAgentListTool,
    )

    tools = [
        ExternalAgentExecuteTool(),
        ExternalAgentListTool(),
        ExternalAgentCheckTool(),
    ]

    for tool in tools:
        tool_id = tool.metadata.name
        register_mindscape_tool(tool_id, tool)
        core_id = f"core.{tool_id}"
        register_mindscape_tool(core_id, tool)

    return tools
