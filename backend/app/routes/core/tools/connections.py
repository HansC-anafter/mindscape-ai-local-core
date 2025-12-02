"""
Connection management routes

Handles CRUD operations for tool connections.
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import List

from ...models.tool_registry import ToolConnectionModel
from ...services.tool_registry import ToolRegistryService
from .base import get_tool_registry, raise_api_error

router = APIRouter(prefix="/api/v1/tools", tags=["tools"])


@router.get("/connections", response_model=List[ToolConnectionModel])
async def list_connections(
    registry: ToolRegistryService = Depends(get_tool_registry),
):
    """List all tool connections"""
    return registry.get_connections()


@router.get("/connections/{connection_id}", response_model=ToolConnectionModel)
async def get_connection(
    connection_id: str,
    registry: ToolRegistryService = Depends(get_tool_registry),
):
    """Get a specific connection"""
    conn = registry.get_connection(connection_id)
    if not conn:
        raise_api_error(404, "Connection not found")
    return conn


@router.delete("/connections/{connection_id}")
async def delete_connection(
    connection_id: str,
    registry: ToolRegistryService = Depends(get_tool_registry),
):
    """Delete a connection and all its tools"""
    success = registry.delete_connection(connection_id)
    if not success:
        raise_api_error(404, "Connection not found")
    return {"success": True}

