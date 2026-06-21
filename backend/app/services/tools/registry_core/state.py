"""Shared state for the public tools registry facade."""

from typing import Dict, Type

from backend.app.services.tools.base import MindscapeTool, Tool, ToolConnection
from backend.app.services.tools.wordpress.wordpress_tool_v1 import WordPressTool

REMOTE_TOOLS_AVAILABLE = False

CORE_TOOLS = ["wordpress"]
THIRD_PARTY_TOOLS = ["notion", "google_drive", "github"]

STATIC_TOOL_REGISTRY: Dict[str, Dict[str, Type[Tool]]] = {
    "wordpress": {
        "local": WordPressTool,
    },
}

_dynamic_tools: Dict[str, ToolConnection] = {}
_mindscape_tools: Dict[str, MindscapeTool] = {}
