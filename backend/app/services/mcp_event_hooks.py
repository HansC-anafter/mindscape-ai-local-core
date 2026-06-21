"""
MCP event hook service public facade.

The implementation lives in mcp_event_hooks_core so this public import path
stays stable for chat_sync and any direct service imports.
"""

from .mcp_event_hooks_core.contracts import HookResults, ReceiptDecision
from .mcp_event_hooks_core.service import MCPEventHookService

__all__ = [
    "HookResults",
    "MCPEventHookService",
    "ReceiptDecision",
]
