"""
Tool status checking routes

Handles status queries for tools and tool connections.
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Any
import os
import logging

from backend.app.services.tool_status_checker import ToolStatusChecker
from backend.app.services.tool_registry import ToolRegistryService
from backend.app.services.tool_info import get_tool_info
from fastapi import Depends
from .base import get_tool_registry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/tools", tags=["tools"])


def get_tool_status_checker(registry: ToolRegistryService = None) -> ToolStatusChecker:
    """
    Get ToolStatusChecker instance with unified initialization

    Args:
        registry: Optional ToolRegistryService instance. If None, creates a new one.

    Returns:
        ToolStatusChecker instance
    """
    if registry is None:
        data_dir = os.getenv("DATA_DIR", "./data")
        registry = ToolRegistryService(data_dir=data_dir)
    return ToolStatusChecker(registry)


@router.get("/status", response_model=Dict[str, Any])
async def get_tools_status(
    profile_id: str = Query('default-user', description="Profile ID")
):
    """
    Get status of all tools for a profile

    Returns tool connection status for all registered tools:
    - unavailable: Tool not registered
    - registered_but_not_connected: Tool registered but no active connection
    - connected: Tool has active and validated connection

    Example:
        GET /api/v1/tools/status?profile_id=user123
    """
    try:
        from .base import get_tool_registry
        registry = get_tool_registry()
        tool_status_checker = get_tool_status_checker(registry)
        statuses = tool_status_checker.list_all_tools_status(profile_id)

        return {
            "tools": {
                tool_type: {
                    "status": status.value,
                    "info": get_tool_info(tool_type)
                }
                for tool_type, status in statuses.items()
            }
        }
    except Exception as e:
        logger.error(f"Failed to get tools status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{tool_type}/status", response_model=Dict[str, Any])
async def get_tool_status(
    tool_type: str,
    profile_id: str = Query('default-user', description="Profile ID")
):
    """
    Get status of a specific tool

    Returns tool connection status for a specific tool.

    Example:
        GET /api/v1/tools/wordpress/status?profile_id=user123
    """
    try:
        from .base import get_tool_registry
        registry = get_tool_registry()
        tool_status_checker = get_tool_status_checker(registry)
        status = tool_status_checker.get_tool_status(tool_type, profile_id)

        return {
            "tool_type": tool_type,
            "status": status.value,
            "info": get_tool_info(tool_type)
        }
    except Exception as e:
        logger.error(f"Failed to get tool status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{tool_type}/health", response_model=Dict[str, Any])
async def check_tool_health(
    tool_type: str,
    profile_id: str = Query(..., description="Profile ID"),
    registry: ToolRegistryService = Depends(get_tool_registry),
):
    """
    Check tool health (connection + instance availability)

    Verifies both connection status and tool instance availability.
    Used by Playbook to ensure tools are ready for execution.

    Args:
        tool_type: Tool type (e.g., "wordpress", "notion")
        profile_id: Profile ID
        registry: Tool registry service

    Returns:
        Health check result
    """
    try:
        from backend.app.services.tools.registry import get_mindscape_tool

        # Check connection status
        connections = registry.get_connections_by_tool_type(profile_id, tool_type)
        connection_available = len(connections) > 0

        # Check tool instance availability
        tool = get_mindscape_tool(tool_type)
        instance_available = tool is not None

        # Overall health
        healthy = connection_available and instance_available

        return {
            "tool_type": tool_type,
            "connection_available": connection_available,
            "instance_available": instance_available,
            "healthy": healthy,
            "connection_count": len(connections),
            "info": get_tool_info(tool_type)
        }
    except Exception as e:
        logger.error(f"Failed to check tool health: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
