"""
Tool List Loader
Handles loading and caching tool lists for playbook execution

Now uses ToolListService for unified tool management
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
            from backend.app.services.tool_list_service import get_tool_list_service

            # Use unified ToolListService
            tool_list_service = get_tool_list_service()

            # Try to get cached tools string from ToolRegistryService first
            try:
                from backend.app.services.tool_registry import ToolRegistryService
                data_dir = os.getenv("DATA_DIR", "./data")
                tool_registry = ToolRegistryService(data_dir=data_dir)

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

                if hasattr(tool_registry, 'get_tools_str_cached'):
                    cached_tools_str = tool_registry.get_tools_str_cached(
                        workspace_id=workspace_id,
                        profile_id=profile_id,
                        enabled_only=True
                    )
                    if cached_tools_str:
                        logger.info(f"ToolListLoader: Using cached tool list for workspace {workspace_id} (length={len(cached_tools_str)})")
                        return cached_tools_str
            except Exception as e:
                logger.debug(f"ToolListLoader: Failed to get cached tools string: {e}")

            # Fallback: use ToolListService to get all tools
            tools_str = tool_list_service.get_tools_string(
                workspace_id=workspace_id,
                profile_id=profile_id,
                enabled_only=True,
                max_description_length=100
            )

            if tools_str:
                logger.info(f"ToolListLoader: Loaded tools for workspace {workspace_id} using ToolListService")
                return tools_str
            else:
                logger.warning(f"ToolListLoader: No tools found for workspace {workspace_id}")
                return None

        except Exception as e:
            logger.warning(f"ToolListLoader: Failed to preload tools list: {e}", exc_info=True)
            return None

