"""
Sandbox Tools Provider

Registers sandbox tools with the tool registry.
"""

from typing import List
import logging

from backend.app.services.tools.base import MindscapeTool
from backend.app.services.tools.sandbox.sandbox_tools import (
    SandboxWriteFileTool,
    SandboxReadFileTool,
    SandboxListFilesTool,
    SandboxCreateVersionTool,
)
from backend.app.services.mindscape_store import MindscapeStore

logger = logging.getLogger(__name__)


def create_sandbox_tools(store: MindscapeStore) -> List[MindscapeTool]:
    """
    Create sandbox tools instances

    Args:
        store: MindscapeStore instance

    Returns:
        List of sandbox tool instances
    """
    return [
        SandboxWriteFileTool(store),
        SandboxReadFileTool(store),
        SandboxListFilesTool(store),
        SandboxCreateVersionTool(store),
    ]

