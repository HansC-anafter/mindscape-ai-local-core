"""
Playbook Tool Dependency Checker

Checks if a playbook's required tools are available.
Used to determine if a background playbook can be enabled.
"""

from enum import Enum
from typing import Dict, List, Optional, Tuple
from backend.app.models.playbook import Playbook, PlaybookMetadata
from backend.app.models.tool_connection import ToolConnectionStatus
from backend.app.services.tool_status_checker import ToolStatusChecker


class PlaybookReadinessStatus(str, Enum):
    """
    Playbook readiness status based on tool dependencies

    - ready: All required tools are connected
    - needs_setup: One or more required tools are registered_but_not_connected
    - unsupported: One or more required tools are unavailable
    """
    READY = "ready"
    NEEDS_SETUP = "needs_setup"
    UNSUPPORTED = "unsupported"


class PlaybookToolChecker:
    """
    Check playbook tool dependencies and readiness
    """

    def __init__(self, tool_status_checker: ToolStatusChecker):
        """
        Initialize playbook tool checker

        Args:
            tool_status_checker: Tool status checker instance
        """
        self.tool_status_checker = tool_status_checker

    def check_playbook_tools(
        self,
        playbook: Playbook,
        profile_id: str
    ) -> Tuple[PlaybookReadinessStatus, Dict[str, ToolConnectionStatus], List[str]]:
        """
        Check playbook tool dependencies

        Args:
            playbook: Playbook instance
            profile_id: Profile ID

        Returns:
            Tuple of:
            - readiness_status: PlaybookReadinessStatus
            - tool_statuses: Dict mapping tool_type -> ToolConnectionStatus
            - missing_required_tools: List of missing required tool types
        """
        # Extract required tools from playbook metadata
        required_tools = self._extract_required_tools(playbook.metadata)

        if not required_tools:
            # No tool dependencies, always ready
            return (
                PlaybookReadinessStatus.READY,
                {},
                []
            )

        # Check status of all required tools
        tool_statuses = self.tool_status_checker.get_tools_status(
            tool_types=required_tools,
            profile_id=profile_id
        )

        # Determine readiness
        missing_required = []
        has_unavailable = False
        has_not_connected = False

        for tool_type, status in tool_statuses.items():
            if status == ToolConnectionStatus.UNAVAILABLE:
                has_unavailable = True
                missing_required.append(tool_type)
            elif status == ToolConnectionStatus.REGISTERED_BUT_NOT_CONNECTED:
                has_not_connected = True
                missing_required.append(tool_type)

        # Determine readiness status
        if has_unavailable:
            readiness = PlaybookReadinessStatus.UNSUPPORTED
        elif has_not_connected:
            readiness = PlaybookReadinessStatus.NEEDS_SETUP
        else:
            readiness = PlaybookReadinessStatus.READY

        return readiness, tool_statuses, missing_required

    def _extract_required_tools(self, metadata: PlaybookMetadata) -> List[str]:
        """
        Extract required tool types from playbook metadata

        Supports both legacy required_tools and new tool_dependencies format

        Args:
            metadata: Playbook metadata

        Returns:
            List of required tool types
        """
        required_tools = []

        # Legacy format: required_tools (simple list)
        if metadata.required_tools:
            required_tools.extend(metadata.required_tools)

        # New format: tool_dependencies (detailed)
        for dep in metadata.tool_dependencies:
            if dep.required:
                # Extract tool type from name
                # For builtin tools, name is the tool_type (e.g., "wordpress")
                # For langchain/mcp, we might need to map differently
                if dep.type == "builtin":
                    required_tools.append(dep.name)
                # Note: langchain/mcp tools are handled differently

        # Remove duplicates
        return list(set(required_tools))

    def can_enable_background_playbook(
        self,
        playbook: Playbook,
        profile_id: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if a background playbook can be enabled

        Args:
            playbook: Playbook instance
            profile_id: Profile ID

        Returns:
            Tuple of (can_enable, error_message)
        """
        if not playbook.metadata.background:
            return True, None  # Not a background playbook, no restriction

        readiness, tool_statuses, missing_required = self.check_playbook_tools(
            playbook=playbook,
            profile_id=profile_id
        )

        if readiness == PlaybookReadinessStatus.READY:
            return True, None
        elif readiness == PlaybookReadinessStatus.NEEDS_SETUP:
            tool_names = ", ".join(missing_required)
            return False, f"需要先配置工具：{tool_names}"
        else:  # UNSUPPORTED
            tool_names = ", ".join(missing_required)
            return False, f"工具尚未支援：{tool_names}"

