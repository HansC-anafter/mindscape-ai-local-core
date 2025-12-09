"""
Tool Executor
Unified handler for capability package tools and external tools
"""

import logging
from typing import Any, Dict, Optional
import inspect

from backend.app.capabilities.registry import (
    call_tool,
    call_tool_async,
    get_tool_backend,
    get_registry,
)

logger = logging.getLogger(__name__)


class ToolExecutor:
    """Unified tool executor"""

    def __init__(self):
        self.registry = get_registry()

    def _ensure_filesystem_tools_registered(self):
        """
        Ensure filesystem tools are registered (cross-process sync via Redis).

        Uses Redis to coordinate tool registration across uvicorn workers:
        1. Check Redis for registration marker
        2. If marker exists, register tools in current process
        3. Set marker after successful registration
        """
        try:
            from backend.app.services.tools.registry import register_filesystem_tools, _mindscape_tools
            from backend.app.services.cache.redis_cache import get_cache_service

            required_tools = ["filesystem_list_files", "filesystem_read_file", "filesystem_write_file", "filesystem_search"]
            missing = [t for t in required_tools if t not in _mindscape_tools]

            if not missing:
                return  # All tools already registered in this process

            # Register tools in this process
            logger.info(f"Registering filesystem tools in worker (missing: {missing})")
            register_filesystem_tools()

            # Verify
            still_missing = [t for t in required_tools if t not in _mindscape_tools]
            if still_missing:
                logger.error(f"Failed to register filesystem tools: {still_missing}")
            else:
                logger.info(f"Successfully registered filesystem tools in worker")

                # Set Redis marker to signal other workers
                try:
                    cache = get_cache_service()
                    cache.set("builtin_tools:filesystem:registered", "true", ttl=3600)
                except Exception as e:
                    logger.debug(f"Could not set Redis marker (non-critical): {e}")

        except Exception as e:
            logger.error(f"Failed to register filesystem tools: {e}", exc_info=True)

    async def execute_tool(
        self,
        tool_name: str,
        **kwargs
    ) -> Any:
        """
        Execute tool (supports capability package tools and external tools)

        Args:
            tool_name: Tool name, format:
                - Capability package tool: `capability.tool_name` (e.g., `habit_learning.observe_event`)
                - MindscapeTool: `{connection_id}.{tool_type}.{tool_name}` (e.g., `canva-1.canva.create_design_from_template`)
                - Legacy format: Direct tool name (deprecated)
            **kwargs: Parameters passed to the tool

        Returns:
            Tool execution result
        """
        if '.' in tool_name:
            parts = tool_name.split('.', 1)
            if len(parts) == 2:
                capability, tool = parts
                tool_info = self.registry.get_tool(tool_name)
                if tool_info:
                    logger.debug(f"Calling capability tool: {tool_name}")
                    return await call_tool_async(capability, tool, **kwargs)

        logger.debug(f"Tool {tool_name} not found in capability registry, trying MindscapeTool registry...")

        # Ensure filesystem tools are registered (lazy init for worker processes)
        self._ensure_filesystem_tools_registered()

        # Normalize parameters for filesystem read/write tools (path -> file_path)
        # Only filesystem_read_file and filesystem_write_file use file_path parameter
        if tool_name in ("filesystem_read_file", "filesystem_write_file") and "path" in kwargs and "file_path" not in kwargs:
            kwargs["file_path"] = kwargs.pop("path")
            logger.debug(f"Normalized 'path' -> 'file_path' for {tool_name}")

        try:
            from backend.app.services.tools.registry import get_mindscape_tool
            from backend.app.services.tools.base import MindscapeTool

            tool = get_mindscape_tool(tool_name)
            if tool:
                logger.debug(f"Found MindscapeTool: {tool_name}")
                if inspect.iscoroutinefunction(tool.execute):
                    result = await tool.execute(**kwargs)
                else:
                    result = tool.execute(**kwargs)
                return result
        except ImportError:
            logger.warning("MindscapeTool registry not available")
        except Exception as e:
            logger.warning(f"Error accessing MindscapeTool registry: {e}")

        raise ValueError(
            f"Tool {tool_name} not found in any registry. "
            f"Supported formats: capability.tool_name, direct tool name (e.g., filesystem_write_file), or {{connection_id}}.{{tool_type}}.{{tool_name}}"
        )

    def execute_tool_sync(
        self,
        tool_name: str,
        **kwargs
    ) -> Any:
        """
        Synchronously execute tool (for non-async scenarios)

        Args:
            tool_name: Tool name, format:
                - Capability package tool: `capability.tool_name`
                - MindscapeTool: `{connection_id}.{tool_type}.{tool_name}`
            **kwargs: Parameters passed to the tool

        Returns:
            Tool execution result
        """
        if '.' in tool_name:
            parts = tool_name.split('.', 1)
            if len(parts) == 2:
                capability, tool = parts
                tool_info = self.registry.get_tool(tool_name)
                if tool_info:
                    return call_tool(capability, tool, **kwargs)

        try:
            from backend.app.services.tools.registry import get_mindscape_tool

            tool = get_mindscape_tool(tool_name)
            if tool:
                logger.debug(f"Found MindscapeTool (sync): {tool_name}")
                result = tool.execute(**kwargs)
                return result
        except ImportError:
            logger.warning("MindscapeTool registry not available")
        except Exception as e:
            logger.warning(f"Error accessing MindscapeTool registry: {e}")

        raise ValueError(
            f"Tool {tool_name} not found in any registry. "
            f"Supported formats: capability.tool_name or {{connection_id}}.{{tool_type}}.{{tool_name}}"
        )


# Global instance
_tool_executor = ToolExecutor()


async def execute_tool(tool_name: str, **kwargs) -> Any:
    """Convenience function: Execute tool"""
    logger.info(f"shared.execute_tool called: {tool_name}")

    # Force ensure filesystem tools are registered on every call
    _tool_executor._ensure_filesystem_tools_registered()

    return await _tool_executor.execute_tool(tool_name, **kwargs)


def execute_tool_sync(tool_name: str, **kwargs) -> Any:
    """Convenience function: Synchronously execute tool"""
    return _tool_executor.execute_tool_sync(tool_name, **kwargs)
