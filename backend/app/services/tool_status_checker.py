"""
Tool Status Checker Service

Checks tool connection status for a workspace/profile.
Determines: unavailable / registered_but_not_connected / connected
"""

from typing import Dict, List
from backend.app.models.tool_connection import ToolConnectionStatus
from backend.app.services.tool_info import get_tool_info, TOOL_INFO
from backend.app.services.tool_connection_store import ToolConnectionStore


class ToolStatusChecker:
    """
    Check tool connection status

    Determines the connection status for tools:
    - unavailable: Tool not registered in tool_info.py
    - registered_but_not_connected: Tool registered but no active connection
    - connected: Tool has active and validated connection
    """

    def __init__(self, tool_connection_store: ToolConnectionStore):
        """
        Initialize tool status checker

        Args:
            tool_connection_store: Tool connection store instance
        """
        self.tool_connection_store = tool_connection_store

    def get_tool_status(
        self,
        tool_type: str,
        profile_id: str
    ) -> ToolConnectionStatus:
        """
        Get status for a specific tool

        Args:
            tool_type: Tool type (e.g., 'wordpress', 'canva')
            profile_id: Profile ID

        Returns:
            ToolConnectionStatus
        """
        # Check if tool is registered in tool_info.py
        tool_info = get_tool_info(tool_type)
        if not tool_info:
            return ToolConnectionStatus.UNAVAILABLE

        # Check if user has active connection
        connections = self.tool_connection_store.get_connections_by_tool_type(
            profile_id=profile_id,
            tool_type=tool_type
        )

        # Filter active and validated connections
        active_connections = [
            conn for conn in connections
            if conn.is_active and conn.is_validated
        ]

        if active_connections:
            return ToolConnectionStatus.CONNECTED
        else:
            return ToolConnectionStatus.REGISTERED_BUT_NOT_CONNECTED

    def get_tools_status(
        self,
        tool_types: List[str],
        profile_id: str
    ) -> Dict[str, ToolConnectionStatus]:
        """
        Get status for multiple tools

        Args:
            tool_types: List of tool types
            profile_id: Profile ID

        Returns:
            Dict mapping tool_type -> ToolConnectionStatus
        """
        return {
            tool_type: self.get_tool_status(tool_type, profile_id)
            for tool_type in tool_types
        }

    def list_all_tools_status(
        self,
        profile_id: str
    ) -> Dict[str, ToolConnectionStatus]:
        """
        Get status for all registered tools

        Args:
            profile_id: Profile ID

        Returns:
            Dict mapping tool_type -> ToolConnectionStatus
        """
        all_tool_types = list(TOOL_INFO.keys())
        return self.get_tools_status(all_tool_types, profile_id)

