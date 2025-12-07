"""
Tool List Loader
Handles loading and caching tool lists for playbook execution
"""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


class ToolListLoader:
    """Loads and caches tool lists for workspace"""

    @staticmethod
    def load_tools_for_workspace(
        workspace_id: str,
        profile_id: Optional[str] = None
    ) -> Optional[str]:
        """
        Load and cache tools list for a workspace.

        Args:
            workspace_id: Workspace ID
            profile_id: Profile ID (optional)

        Returns:
            Cached tools string or None if loading fails
        """
        try:
            from backend.app.services.tool_registry import ToolRegistryService

            # Get tool registry service
            data_dir = os.getenv("DATA_DIR", "./data")
            tool_registry = ToolRegistryService(data_dir=data_dir)

            # Register external extensions (same as get_tool_registry does)
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

            # Get cached tools list (uses Redis cache if available)
            if hasattr(tool_registry, 'get_tools_str_cached'):
                cached_tools_str = tool_registry.get_tools_str_cached(
                    workspace_id=workspace_id,
                    profile_id=profile_id,
                    enabled_only=True
                )
                logger.info(f"ToolListLoader: Preloaded and cached tool list for workspace {workspace_id}")
                return cached_tools_str
            else:
                # Fallback: query tools directly
                tools = tool_registry.get_tools(
                    workspace_id=workspace_id,
                    profile_id=profile_id,
                    enabled_only=True
                )
                if tools:
                    # Format tools manually as fallback
                    tools_list = []
                    for tool in tools:
                        tool_id = getattr(tool, 'tool_id', None) or getattr(tool, 'id', 'unknown')
                        name = getattr(tool, 'display_name', None) or getattr(tool, 'name', None) or tool_id
                        desc = getattr(tool, 'description', None) or ''
                        category = getattr(tool, 'category', None) or 'general'
                        tools_list.append(f"- {tool_id}: {name} ({category}) - {desc[:100]}")
                    tools_str = "\n".join(tools_list) if tools_list else None
                    logger.info(f"ToolListLoader: Loaded {len(tools_list)} tools for workspace {workspace_id}")
                    return tools_str
        except Exception as e:
            logger.warning(f"ToolListLoader: Failed to preload tools list: {e}", exc_info=True)
            return None

