"""
Tool Overlay Service

Handles tool overlay logic for workspace-specific tool customization:
1. Tool whitelist (filter tools available in workspace)
2. Danger level override (can only be more restrictive, not less)
3. Tool enabled/disabled status

Security rule: Overrides can only be more restrictive, never more permissive.
"""

import logging
from typing import List, Optional, Dict, Any
from enum import Enum

from backend.app.models.tool_registry import RegisteredTool
from backend.app.models.workspace_resource_binding import ResourceType
from backend.app.services.stores.workspace_resource_binding_store import WorkspaceResourceBindingStore

logger = logging.getLogger(__name__)


class DangerLevel(str, Enum):
    """Tool danger level hierarchy"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ToolOverlayService:
    """
    Service for applying workspace overlay to tools
    """

    def __init__(self):
        """Initialize the service"""
        self.binding_store = WorkspaceResourceBindingStore()

    def _get_danger_level_hierarchy(self) -> Dict[str, int]:
        """
        Get danger level hierarchy (for comparison)

        Returns:
            Dict mapping danger level to numeric value (higher = more dangerous)
        """
        return {
            DangerLevel.LOW: 1,
            DangerLevel.MEDIUM: 2,
            DangerLevel.HIGH: 3,
        }

    def _is_more_restrictive(self, original: str, override: str) -> bool:
        """
        Check if override danger level is more restrictive than original

        More restrictive means higher danger level (more restrictions).

        Args:
            original: Original danger level
            override: Override danger level

        Returns:
            True if override is more restrictive, False otherwise
        """
        hierarchy = self._get_danger_level_hierarchy()
        original_level = hierarchy.get(original.lower(), 1)
        override_level = hierarchy.get(override.lower(), 1)

        # More restrictive = higher level
        return override_level > original_level

    def _is_more_permissive(self, original: str, override: str) -> bool:
        """
        Check if override danger level is more permissive than original

        More permissive means lower danger level (fewer restrictions).

        Args:
            original: Original danger level
            override: Override danger level

        Returns:
            True if override is more permissive, False otherwise
        """
        hierarchy = self._get_danger_level_hierarchy()
        original_level = hierarchy.get(original.lower(), 1)
        override_level = hierarchy.get(override.lower(), 1)

        # More permissive = lower level
        return override_level < original_level

    def validate_danger_level_override(
        self,
        tool: RegisteredTool,
        override_danger_level: str
    ) -> bool:
        """
        Validate that danger level override is more restrictive (not more permissive)

        Security rule: Overrides can only be more restrictive, never more permissive.

        Args:
            tool: Original tool
            override_danger_level: Proposed override danger level

        Returns:
            True if override is valid (more restrictive or same), False if invalid (more permissive)
        """
        original_level = tool.danger_level.lower()
        override_level = override_danger_level.lower()

        # Same level is allowed (no change)
        if original_level == override_level:
            return True

        # More restrictive is allowed
        if self._is_more_restrictive(original_level, override_level):
            return True

        # More permissive is NOT allowed
        if self._is_more_permissive(original_level, override_level):
            logger.warning(
                f"Invalid danger level override for tool {tool.tool_id}: "
                f"cannot make {original_level} more permissive to {override_level}"
            )
            return False

        return True

    def apply_tool_overlay(
        self,
        tool: RegisteredTool,
        workspace_id: str
    ) -> Optional[RegisteredTool]:
        """
        Apply workspace overlay to a tool

        This method:
        1. Checks if tool is in workspace whitelist (if whitelist exists)
        2. Applies danger level override (if exists and valid)
        3. Applies enabled/disabled status (if exists)

        Args:
            tool: Original tool
            workspace_id: Workspace ID

        Returns:
            Modified tool with overlay applied, or None if tool is filtered out
        """
        # Get workspace binding for this tool
        binding = self.binding_store.get_binding_by_resource(
            workspace_id=workspace_id,
            resource_type=ResourceType.TOOL,
            resource_id=tool.tool_id
        )

        # If no binding, return tool as-is
        if not binding:
            return tool

        overrides = binding.overrides or {}

        # Step 1: Check tool whitelist
        tool_whitelist = overrides.get("local_tool_whitelist")
        if tool_whitelist is not None:
            # If whitelist exists and tool is not in it, filter out
            if tool.tool_id not in tool_whitelist:
                logger.debug(f"Tool {tool.tool_id} filtered out by workspace {workspace_id} whitelist")
                return None

        # Step 2: Apply danger level override (if exists and valid)
        danger_overrides = overrides.get("local_danger_overrides", {})
        if tool.tool_id in danger_overrides:
            override_danger_level = danger_overrides[tool.tool_id]

            # Validate override (must be more restrictive)
            if not self.validate_danger_level_override(tool, override_danger_level):
                # Invalid override: log warning and use original
                logger.warning(
                    f"Invalid danger level override for tool {tool.tool_id} in workspace {workspace_id}, "
                    f"using original level {tool.danger_level}"
                )
            else:
                # Valid override: create modified tool
                # Use model_copy for Pydantic v2, or copy for v1
                try:
                    tool = tool.model_copy(update={"danger_level": override_danger_level})
                except AttributeError:
                    # Fallback for Pydantic v1
                    tool = tool.copy(update={"danger_level": override_danger_level})
                logger.debug(
                    f"Applied danger level override for tool {tool.tool_id} in workspace {workspace_id}: "
                    f"{tool.danger_level} -> {override_danger_level}"
                )

        # Step 3: Apply enabled/disabled status (if exists)
        local_enabled = overrides.get("local_enabled")
        if local_enabled is not None:
            # Use model_copy for Pydantic v2, or copy for v1
            try:
                tool = tool.model_copy(update={"enabled": local_enabled})
            except AttributeError:
                # Fallback for Pydantic v1
                tool = tool.copy(update={"enabled": local_enabled})
            logger.debug(
                f"Applied enabled override for tool {tool.tool_id} in workspace {workspace_id}: {local_enabled}"
            )

        return tool

    def apply_tools_overlay(
        self,
        tools: List[RegisteredTool],
        workspace_id: str
    ) -> List[RegisteredTool]:
        """
        Apply workspace overlay to a list of tools

        Args:
            tools: List of original tools
            workspace_id: Workspace ID

        Returns:
            List of tools with overlay applied (filtered and modified)
        """
        result = []
        for tool in tools:
            overlay_tool = self.apply_tool_overlay(tool, workspace_id)
            if overlay_tool:
                result.append(overlay_tool)

        return result

    def get_workspace_tool_bindings(
        self,
        workspace_id: str
    ) -> Dict[str, Any]:
        """
        Get all tool bindings for a workspace

        Args:
            workspace_id: Workspace ID

        Returns:
            Dict mapping tool_id to binding overrides
        """
        bindings = self.binding_store.list_bindings_by_workspace(
            workspace_id=workspace_id,
            resource_type=ResourceType.TOOL
        )

        result = {}
        for binding in bindings:
            result[binding.resource_id] = {
                "access_mode": binding.access_mode.value,
                "overrides": binding.overrides,
            }

        return result

