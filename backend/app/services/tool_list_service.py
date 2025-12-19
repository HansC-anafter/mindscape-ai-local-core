"""
Tool List Service
Unified service for managing and retrieving all available tools from all sources

This service provides a single interface to get all tools from:
1. ToolRegistryService (dynamically discovered tools)
2. registry.py (built-in tools)
3. capabilities/registry (capability pack tools)
"""

import logging
import os
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ToolInfo:
    """Unified tool information"""
    tool_id: str
    name: str
    description: str
    category: str
    source: str  # 'builtin', 'capability', 'discovered'
    enabled: bool = True
    metadata: Optional[Dict[str, Any]] = None


class ToolListService:
    """
    Unified tool list service

    Provides a single interface to get all available tools from all sources
    """

    def __init__(self, data_dir: Optional[str] = None):
        """
        Initialize ToolListService

        Args:
            data_dir: Data directory for ToolRegistryService (optional)
        """
        self.data_dir = data_dir or os.getenv("DATA_DIR", "./data")

    def get_all_tools(
        self,
        workspace_id: Optional[str] = None,
        profile_id: Optional[str] = None,
        enabled_only: bool = True
    ) -> List[ToolInfo]:
        """
        Get all available tools from all sources

        Args:
            workspace_id: Workspace ID (for filtering)
            profile_id: Profile ID (for filtering)
            enabled_only: Only return enabled tools

        Returns:
            List of ToolInfo objects (deduplicated)
        """
        all_tools: Dict[str, ToolInfo] = {}

        # 1. Get tools from ToolRegistryService (dynamically discovered)
        discovered_tools = self._get_discovered_tools(
            workspace_id=workspace_id,
            profile_id=profile_id,
            enabled_only=enabled_only
        )
        for tool in discovered_tools:
            all_tools[tool.tool_id] = tool

        # 2. Get built-in tools from registry.py
        builtin_tools = self._get_builtin_tools()
        for tool in builtin_tools:
            # Only add if not already present (discovered tools take precedence)
            if tool.tool_id not in all_tools:
                all_tools[tool.tool_id] = tool

        # 3. Get capability pack tools from capabilities/registry
        capability_tools = self._get_capability_tools()
        for tool in capability_tools:
            # Only add if not already present
            if tool.tool_id not in all_tools:
                all_tools[tool.tool_id] = tool

        logger.info(
            f"ToolListService: Retrieved {len(all_tools)} unique tools "
            f"({len(discovered_tools)} discovered, {len(builtin_tools)} built-in, {len(capability_tools)} capability)"
        )

        return list(all_tools.values())

    def get_tools_string(
        self,
        workspace_id: Optional[str] = None,
        profile_id: Optional[str] = None,
        enabled_only: bool = True,
        max_description_length: int = 100
    ) -> Optional[str]:
        """
        Get formatted tools string for LLM prompts

        Args:
            workspace_id: Workspace ID
            profile_id: Profile ID
            enabled_only: Only return enabled tools
            max_description_length: Maximum description length

        Returns:
            Formatted tools string or None if no tools found
        """
        tools = self.get_all_tools(
            workspace_id=workspace_id,
            profile_id=profile_id,
            enabled_only=enabled_only
        )

        if not tools:
            return None

        tools_list = []
        for tool in tools:
            desc = tool.description[:max_description_length] if tool.description else ''
            tools_list.append(f"- {tool.tool_id}: {tool.name} ({tool.category}) - {desc}")

        return "\n".join(tools_list)

    def _get_discovered_tools(
        self,
        workspace_id: Optional[str] = None,
        profile_id: Optional[str] = None,
        enabled_only: bool = True
    ) -> List[ToolInfo]:
        """Get tools from ToolRegistryService"""
        try:
            from backend.app.services.tool_registry import ToolRegistryService

            tool_registry = ToolRegistryService(data_dir=self.data_dir)

            # Register external extensions
            try:
                from backend.app.extensions.console_kit import register_console_kit_tools
                register_console_kit_tools(tool_registry)
            except ImportError:
                pass

            try:
                from backend.app.extensions.community import register_community_extensions
                register_community_extensions(tool_registry)
            except ImportError:
                pass

            tools = tool_registry.get_tools(
                workspace_id=workspace_id,
                profile_id=profile_id,
                enabled_only=enabled_only
            )

            result = []
            for tool in tools:
                tool_id = getattr(tool, 'tool_id', None) or getattr(tool, 'id', 'unknown')
                name = getattr(tool, 'display_name', None) or getattr(tool, 'name', None) or tool_id
                desc = getattr(tool, 'description', None) or ''
                category = getattr(tool, 'category', None) or 'general'
                enabled = getattr(tool, 'enabled', True)

                result.append(ToolInfo(
                    tool_id=tool_id,
                    name=name,
                    description=desc,
                    category=category,
                    source='discovered',
                    enabled=enabled,
                    metadata={'tool': tool}
                ))

            return result

        except Exception as e:
            logger.warning(f"ToolListService: Failed to get discovered tools: {e}", exc_info=True)
            return []

    def _get_builtin_tools(self) -> List[ToolInfo]:
        """Get built-in tools from registry.py"""
        try:
            from backend.app.services.tools.registry import get_all_mindscape_tools, register_workspace_tools, register_filesystem_tools

            # Ensure tools are registered (in case module was reloaded)
            builtin_tools = get_all_mindscape_tools()
            if len(builtin_tools) == 0:
                logger.debug("ToolListService: No built-in tools found, registering...")
                register_workspace_tools()
                register_filesystem_tools()
                builtin_tools = get_all_mindscape_tools()

            result = []
            for tool_id, tool in builtin_tools.items():
                name = tool.metadata.name if hasattr(tool, 'metadata') else tool_id
                desc = tool.metadata.description if hasattr(tool, 'metadata') else ''
                category = (
                    tool.metadata.category.value
                    if hasattr(tool, 'metadata') and hasattr(tool.metadata.category, 'value')
                    else 'general'
                )

                result.append(ToolInfo(
                    tool_id=tool_id,
                    name=name,
                    description=desc,
                    category=category,
                    source='builtin',
                    enabled=True,
                    metadata={'tool': tool}
                ))

            return result

        except Exception as e:
            logger.warning(f"ToolListService: Failed to get built-in tools: {e}", exc_info=True)
            return []

    def _get_capability_tools(self) -> List[ToolInfo]:
        """Get capability pack tools from capabilities/registry"""
        try:
            from backend.app.capabilities.registry import get_registry, load_capabilities
            from pathlib import Path

            capability_registry = get_registry()
            capability_tool_names = capability_registry.list_tools()

            # If no tools found, try reloading capabilities
            if len(capability_tool_names) == 0:
                logger.debug("ToolListService: No capability tools found, reloading...")
                app_dir = Path(__file__).parent.parent.parent
                capabilities_dir = app_dir / "capabilities"
                if capabilities_dir.exists():
                    load_capabilities(capabilities_dir)

            # Always try loading from remote capabilities directory (if available)
            # Use a simple approach: track if we've already attempted to load remote capabilities
            # This avoids hardcoding any capability names
            remote_capabilities_dir = os.getenv("MINDSCAPE_REMOTE_CAPABILITIES_DIR")
            if remote_capabilities_dir:
                remote_capabilities_path = Path(remote_capabilities_dir)
                if remote_capabilities_path.exists():
                    # Check if we've already loaded from this directory by comparing tool count before/after
                    # This is a simple heuristic that doesn't hardcode capability names
                    tools_before = len(capability_tool_names)
                    load_capabilities(remote_capabilities_path)
                    capability_tool_names = capability_registry.list_tools()
                    tools_after = len(capability_tool_names)

                    if tools_after > tools_before:
                        logger.info(f"ToolListService: Loaded remote capabilities from {remote_capabilities_dir} (added {tools_after - tools_before} tools)")
                    else:
                        logger.debug(f"ToolListService: Remote capabilities already loaded or no new tools found")
                else:
                    logger.warning(f"ToolListService: Remote capabilities directory does not exist: {remote_capabilities_path}")
            else:
                logger.debug("ToolListService: MINDSCAPE_REMOTE_CAPABILITIES_DIR environment variable not set")

            result = []
            for tool_name in capability_tool_names:
                tool_info = capability_registry.get_tool(tool_name)
                if not tool_info:
                    continue

                tool_meta = tool_info.get('tool_info', {})
                name = tool_meta.get('name', tool_name.split('.')[-1] if '.' in tool_name else tool_name)
                desc = tool_meta.get('description', '')
                category = tool_meta.get('category', 'capability')

                result.append(ToolInfo(
                    tool_id=tool_name,
                    name=name,
                    description=desc,
                    category=category,
                    source='capability',
                    enabled=True,
                    metadata={'tool_info': tool_info}
                ))

            return result

        except Exception as e:
            logger.warning(f"ToolListService: Failed to get capability tools: {e}", exc_info=True)
            return []

    def get_tool_by_id(self, tool_id: str) -> Optional[ToolInfo]:
        """
        Get a specific tool by ID

        Args:
            tool_id: Tool ID

        Returns:
            ToolInfo or None if not found
        """
        all_tools = self.get_all_tools(enabled_only=False)
        for tool in all_tools:
            if tool.tool_id == tool_id:
                return tool
        return None

    def get_tools_by_source(self, source: str) -> List[ToolInfo]:
        """
        Get tools from a specific source

        Args:
            source: 'builtin', 'capability', or 'discovered'

        Returns:
            List of ToolInfo objects
        """
        all_tools = self.get_all_tools(enabled_only=False)
        return [tool for tool in all_tools if tool.source == source]

    def get_tools_by_category(self, category: str) -> List[ToolInfo]:
        """
        Get tools by category

        Args:
            category: Tool category

        Returns:
            List of ToolInfo objects
        """
        all_tools = self.get_all_tools(enabled_only=False)
        return [tool for tool in all_tools if tool.category == category]


# Global instance
_tool_list_service: Optional[ToolListService] = None


def get_tool_list_service(data_dir: Optional[str] = None) -> ToolListService:
    """
    Get global ToolListService instance

    Args:
        data_dir: Data directory (optional)

    Returns:
        ToolListService instance
    """
    global _tool_list_service
    if _tool_list_service is None:
        _tool_list_service = ToolListService(data_dir=data_dir)
    return _tool_list_service

