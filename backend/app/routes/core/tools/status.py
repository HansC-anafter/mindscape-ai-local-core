"""
Tool status checking routes

Handles status queries for tools and tool connections.
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Any
import os
import logging

from backend.app.services.tool_status_checker import ToolStatusChecker
from backend.app.services.tool_connection_store import ToolConnectionStore
from backend.app.services.tool_info import get_tool_info

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/tools", tags=["tools"])


def get_tool_status_checker() -> ToolStatusChecker:
    """
    Get ToolStatusChecker instance with unified initialization
    """
    data_dir = os.getenv("DATA_DIR", "./data")
    tool_connection_store = ToolConnectionStore(db_path=f"{data_dir}/my_agent_console.db")
    return ToolStatusChecker(tool_connection_store)


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
        tool_status_checker = get_tool_status_checker()
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
        tool_status_checker = get_tool_status_checker()
        status = tool_status_checker.get_tool_status(tool_type, profile_id)

        return {
            "tool_type": tool_type,
            "status": status.value,
            "info": get_tool_info(tool_type)
        }
    except Exception as e:
        logger.error(f"Failed to get tool status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
