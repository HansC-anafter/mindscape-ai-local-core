"""
Local filesystem tool provider routes
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import List, Dict, Any
from pydantic import BaseModel, Field

from backend.app.services.tool_registry import ToolRegistryService
from backend.app.services.tools.discovery_provider import ToolConfig
from ..base import get_tool_registry, raise_api_error

router = APIRouter(prefix="/api/v1/tools", tags=["tools"])


class LocalFilesystemConfigRequest(BaseModel):
    """Local filesystem configuration request"""
    connection_id: str
    name: str
    allowed_directories: List[str] = Field(..., description="List of allowed directory paths")
    allow_write: bool = Field(default=False, description="Allow write operations")


@router.post("/local-filesystem/configure", response_model=Dict[str, Any])
async def configure_local_filesystem(
    request: LocalFilesystemConfigRequest,
    registry: ToolRegistryService = Depends(get_tool_registry),
):
    """
    Configure local filesystem access

    Sets up allowed directories for file system access.
    Used for document collection and RAG functionality.

    Example:
        POST /api/tools/local-filesystem/configure
        {
            "connection_id": "local-fs-1",
            "name": "Documents Directory",
            "allowed_directories": ["~/Documents", "./data/documents"],
            "allow_write": false
        }
    """
    try:
        config = ToolConfig(
            tool_type="local_filesystem",
            connection_type="local",
            custom_config={
                "allowed_directories": request.allowed_directories,
                "allow_write": request.allow_write
            }
        )

        result = await registry.discover_tool_capabilities(
            provider_name="local_filesystem",
            config=config,
            connection_id=request.connection_id
        )

        return {
            "success": True,
            "connection_id": request.connection_id,
            "name": request.name,
            "discovered_tools": result.get("discovered_tools", []),
            "tools_count": len(result.get("discovered_tools", []))
        }
    except Exception as e:
        raise_api_error(500, f"Configuration failed: {str(e)}")


@router.get("/local-filesystem/directories", response_model=Dict[str, Any])
async def get_configured_directories(
    registry: ToolRegistryService = Depends(get_tool_registry),
):
    """
    Get list of configured local filesystem directories

    Returns all connections that use local filesystem provider
    """
    try:
        connections = registry.get_connections()
        local_fs_connections = [
            conn for conn in connections
            if conn.tool_type == "local_filesystem"
        ]

        directories_info = []
        for conn in local_fs_connections:
            directories_info.append({
                "connection_id": conn.id,
                "name": conn.name,
                "allowed_directories": conn.custom_config.get("allowed_directories", []),
                "allow_write": conn.custom_config.get("allow_write", False)
            })

        return {
            "success": True,
            "connections": directories_info,
            "count": len(directories_info)
        }
    except Exception as e:
        raise_api_error(500, str(e))
