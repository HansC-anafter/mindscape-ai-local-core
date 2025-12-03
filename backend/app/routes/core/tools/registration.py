"""
Tool registration routes

Enhanced tool registration with verification to ensure tools are available in tools.registry.
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Dict, Any, Optional
from pydantic import BaseModel

from backend.app.models.tool_registry import ToolConnectionModel
from backend.app.services.tool_registry import ToolRegistryService
from backend.app.services.tools.registry import (
    get_mindscape_tool,
    register_mindscape_tool,
    get_tool_by_registered_id
)
from .base import get_tool_registry, raise_api_error

router = APIRouter(prefix="/api/v1/tools", tags=["tools"])


class RegisterToolRequest(BaseModel):
    """Request to register a tool"""
    tool_id: str
    connection_id: str
    profile_id: str


@router.post("/register", response_model=Dict[str, Any])
async def register_tool(
    request: RegisterToolRequest,
    registry: ToolRegistryService = Depends(get_tool_registry),
):
    """
    Register a tool and ensure it's available in tools.registry

    Gets connection from ToolRegistryService, registers tool to tools.registry,
    and verifies registration status.

    Args:
        request: Tool registration request
        registry: Tool registry service

    Returns:
        Registration result with verification status
    """
    try:
        connection = registry.get_connection(request.connection_id, request.profile_id)
        if not connection:
            raise_api_error(404, f"Connection {request.connection_id} not found")

        existing_tool = get_mindscape_tool(request.tool_id)
        if existing_tool:
            return {
                "success": True,
                "tool_id": request.tool_id,
                "already_registered": True,
                "message": "Tool already registered in tools.registry"
            }

        tool_instance = None
        try:
            from backend.app.services.tools.registry import get_tool
            from backend.app.services.tools.base import ToolConnection as BaseToolConnection

            base_connection = BaseToolConnection(
                id=connection.id,
                tool_type=connection.tool_type,
                connection_type=connection.connection_type,
                api_key=connection.api_key,
                api_secret=connection.api_secret,
                base_url=connection.base_url,
                name=connection.name,
            )

            if connection.tool_type in ["wordpress", "notion", "canva", "google_drive"]:
                tool = get_tool(connection.tool_type, connection.connection_type, base_connection)
                if tool:
                    from backend.app.services.tools.base import MindscapeTool
                    if isinstance(tool, MindscapeTool):
                        tool_instance = tool
        except Exception:
            pass

        if tool_instance:
            register_mindscape_tool(request.tool_id, tool_instance)
            verified = True
        else:
            verified = get_tool_by_registered_id(request.tool_id) is not None

        final_check = get_mindscape_tool(request.tool_id) or get_tool_by_registered_id(request.tool_id)

        return {
            "success": True,
            "tool_id": request.tool_id,
            "connection_id": request.connection_id,
            "registered": True,
            "verified": verified and final_check is not None,
            "message": "Tool registered successfully" if verified else "Connection registered, tool instance will be created on-demand"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise_api_error(500, f"Tool registration failed: {str(e)}")


@router.get("/verify/{tool_id}", response_model=Dict[str, Any])
async def verify_tool_registration(
    tool_id: str,
    registry: ToolRegistryService = Depends(get_tool_registry),
):
    """
    Verify that a tool is registered in both ToolRegistryService and tools.registry

    Args:
        tool_id: Tool ID to verify
        registry: Tool registry service

    Returns:
        Verification result
    """
    try:
        registered_tool = registry.get_tool(tool_id)
        in_registry_service = registered_tool is not None

        tool_instance = get_mindscape_tool(tool_id)
        dynamic_tool = get_tool_by_registered_id(tool_id)
        in_tools_registry = tool_instance is not None or dynamic_tool is not None

        return {
            "tool_id": tool_id,
            "in_registry_service": in_registry_service,
            "in_tools_registry": in_tools_registry,
            "fully_registered": in_registry_service and in_tools_registry,
            "registered_tool": registered_tool.dict() if registered_tool else None
        }
    except Exception as e:
        raise_api_error(500, f"Verification failed: {str(e)}")

