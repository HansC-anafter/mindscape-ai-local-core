from typing import Optional
import logging

from backend.app.services.tools.adapters import is_langchain_available, is_mcp_available
from backend.app.services.tools.base import MindscapeTool
from backend.app.services.tools.registry import (
    get_mindscape_tool,
    register_mindscape_tool,
)
from backend.app.services.unified_tool_executor_core.capability import (
    resolve_capability_tool,
)

logger = logging.getLogger("backend.app.services.unified_tool_executor")


def parse_tool_name(tool_name: str) -> tuple[str, str]:
    """Parse tool name to determine tool type."""
    if "." in tool_name:
        parts = tool_name.split(".", 1)
        if parts[0] in ["builtin", "langchain", "mcp"]:
            return parts[0], parts[1]
        if parts[0] == "default":
            return "builtin", parts[1]

    return "builtin", tool_name


async def get_tool(executor, tool_type: str, tool_name: str) -> Optional[MindscapeTool]:
    """Get tool instance for the executor."""
    if tool_type == "builtin":
        return _get_builtin_tool(executor, tool_name)

    if tool_type == "langchain":
        if not is_langchain_available():
            logger.warning("LangChain not installed")
            return None

        full_name = f"langchain.{tool_name}"
        tool = get_mindscape_tool(full_name)
        if not tool:
            logger.warning("LangChain tool %s not registered", tool_name)
        return tool

    if tool_type == "mcp":
        if not is_mcp_available():
            logger.warning("MCP dependencies not installed")
            return None

        if executor.mcp_manager is None:
            logger.warning("MCP Manager not initialized")
            return None

        tool = executor.mcp_manager.get_tool_by_name(tool_name)
        if not tool:
            logger.warning("MCP tool %s not found", tool_name)
        return tool

    logger.error("Unsupported tool type: %s", tool_type)
    return None


def _get_builtin_tool(executor, tool_name: str) -> Optional[MindscapeTool]:
    tool = get_mindscape_tool(tool_name)
    if tool:
        return tool

    if not executor._workspace_tools_loaded:
        executor._workspace_tools_loaded = True
        _register_workspace_tool_set()
        tool = get_mindscape_tool(tool_name)
        if tool:
            return tool

    cap_tool = resolve_capability_tool(tool_name)
    if cap_tool:
        try:
            register_mindscape_tool(tool_name, cap_tool)
        except Exception:
            pass
        return cap_tool

    return None


def _register_workspace_tool_set() -> None:
    try:
        from backend.app.services.tools.registry import (
            register_filesystem_tools,
            register_internal_knowledge_projection_tool,
            register_meeting_planner_tools,
            register_mindscape_graph_tools,
            register_reporting_tools,
            register_workspace_tools,
        )

        register_workspace_tools()
        register_internal_knowledge_projection_tool()
        register_filesystem_tools()
        register_mindscape_graph_tools()
        register_reporting_tools()
        register_meeting_planner_tools()
    except Exception:
        pass
