"""
Local filesystem tool provider routes
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from pathlib import Path
import os

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

        # Update connection name if it was created
        connections = registry.get_connections()
        for conn in connections:
            if conn.id == request.connection_id and conn.tool_type == "local_filesystem":
                if conn.name != request.name:
                    conn.name = request.name
                    registry.update_connection(conn)
                break

        # Check if any directory needs host mounting and update .env if needed
        env_update_info = None
        for directory in request.allowed_directories:
            dir_path = Path(directory).expanduser().resolve()
            dir_str = str(dir_path)

            # Check if path is outside container's default data directory
            # and might need host mounting
            if (dir_str.startswith("/Users/") or
                dir_str.startswith("/home/") or
                dir_str.startswith("/root/") and dir_str != "/root"):
                # Extract parent directory for mounting
                # For paths like /Users/username/Documents/mindscape-ai
                # We should mount /Users/username/Documents
                if dir_str.startswith("/Users/"):
                    parts = dir_str.split("/")
                    if len(parts) >= 4:
                        mount_path = "/".join(parts[:4])  # /Users/username/Documents
                        env_update_info = {
                            "host_path": mount_path,
                            "container_path": "/host/documents",
                            "requires_restart": True
                        }
                        break
                elif dir_str.startswith("/home/"):
                    parts = dir_str.split("/")
                    if len(parts) >= 4:
                        mount_path = "/".join(parts[:4])  # /home/username/Documents
                        env_update_info = {
                            "host_path": mount_path,
                            "container_path": "/host/documents",
                            "requires_restart": True
                        }
                        break

        response = {
            "success": True,
            "connection_id": request.connection_id,
            "name": request.name,
            "discovered_tools": result.get("discovered_tools", []),
            "tools_count": len(result.get("discovered_tools", []))
        }

        # Add env update info if needed
        if env_update_info:
            response["env_update"] = env_update_info
            response["message"] = (
                f"Configuration saved. To access {request.allowed_directories[0]}, "
                f"please set HOST_DOCUMENTS_PATH={env_update_info['host_path']} in .env file "
                f"and restart the service."
            )

        return response
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
                "allowed_directories": conn.config.get("allowed_directories", []),
                "allow_write": conn.config.get("allow_write", False),
                "enabled": conn.enabled
            })

        return {
            "success": True,
            "connections": directories_info,
            "count": len(directories_info)
        }
    except Exception as e:
        raise_api_error(500, str(e))
