"""
MCP (Model Context Protocol) tool provider routes
"""
from fastapi import APIRouter, HTTPException
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

from ..base import raise_api_error

router = APIRouter(prefix="/api/v1/tools", tags=["tools"])


class MCPConnectRequest(BaseModel):
    """Connect MCP server request"""
    server_id: str = Field(..., description="Server unique identifier")
    name: str = Field(..., description="Server display name")
    transport: str = Field(default="stdio", description="Transport type: stdio or http")

    command: Optional[str] = Field(None, description="Command (e.g., 'npx')")
    args: Optional[List[str]] = Field(None, description="Command arguments")
    env: Optional[Dict[str, str]] = Field(None, description="Environment variables")

    base_url: Optional[str] = Field(None, description="HTTP server URL")
    api_key: Optional[str] = Field(None, description="API authentication key")


class MCPImportClaudeConfigRequest(BaseModel):
    """Import Claude MCP configuration request"""
    config_path: Optional[str] = Field(
        default="~/.config/claude/mcp.json",
        description="Claude mcp.json file path"
    )


@router.get("/mcp/servers", response_model=Dict[str, Any])
async def list_mcp_servers():
    """
    List all configured MCP servers

    Used by Config Assistant to view connected servers
    """
    try:
        from backend.app.services.tools.adapters.mcp_manager import MCPServerManager

        manager = MCPServerManager()
        servers_info = []

        for server_id in manager.servers:
            status = manager.get_server_status(server_id)
            servers_info.append(status)

        return {
            "success": True,
            "servers": servers_info,
            "count": len(servers_info)
        }
    except Exception as e:
        raise_api_error(500, str(e))


@router.post("/mcp/connect", response_model=Dict[str, Any])
async def connect_mcp_server(request: MCPConnectRequest):
    """
    Connect new MCP server

    Used by Config Assistant for automatic MCP server configuration
    """
    try:
        from backend.app.services.tools.adapters.mcp_manager import MCPServerManager
        from backend.app.services.tools.adapters.mcp_client import MCPServerConfig, MCPTransportType

        manager = MCPServerManager()

        if request.transport == "stdio":
            config = MCPServerConfig(
                id=request.server_id,
                name=request.name,
                transport=MCPTransportType.STDIO,
                command=request.command,
                args=request.args or [],
                env=request.env or {}
            )
        else:
            config = MCPServerConfig(
                id=request.server_id,
                name=request.name,
                transport=MCPTransportType.HTTP_SSE,
                base_url=request.base_url,
                api_key=request.api_key
            )

        tools = await manager.add_server(config, auto_discover=True)

        return {
            "success": True,
            "server_id": request.server_id,
            "tools_count": len(tools),
            "message": f"MCP server {request.name} connected, discovered {len(tools)} tools"
        }
    except Exception as e:
        raise_api_error(500, f"Connection failed: {str(e)}")


@router.post("/mcp/import-claude-config", response_model=Dict[str, Any])
async def import_claude_mcp_config(request: MCPImportClaudeConfigRequest):
    """
    Import Claude Desktop MCP configuration

    Used for quick setup: one-click import Claude configuration
    """
    try:
        from pathlib import Path
        from backend.app.services.tools.adapters.mcp_manager import MCPServerManager

        config_path = Path(request.config_path).expanduser()

        if not config_path.exists():
            raise_api_error(404, f"Configuration file not found: {config_path}")

        manager = MCPServerManager()
        imported_count = manager.import_from_claude_config(str(config_path))
        await manager.connect_all()

        servers_status = []
        for server_id in manager.servers:
            status = manager.get_server_status(server_id)
            servers_status.append(status)

        return {
            "success": True,
            "imported_count": imported_count,
            "servers": servers_status,
            "message": f"Successfully imported {imported_count} MCP servers"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise_api_error(500, f"Import failed: {str(e)}")


@router.get("/mcp/available-servers", response_model=Dict[str, Any])
async def get_available_mcp_servers():
    """
    Get predefined common MCP servers list

    Used by Config Assistant to recommend to users
    """
    available_servers = [
        {
            "id": "github",
            "name": "GitHub",
            "description": "Access GitHub repositories, issues, pull requests, etc.",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-github"],
            "requires_env": ["GITHUB_TOKEN"],
            "category": "development"
        },
        {
            "id": "filesystem",
            "name": "File System",
            "description": "Read and write local file system",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem"],
            "category": "file_operations",
            "danger_level": "high"
        },
        {
            "id": "postgres",
            "name": "PostgreSQL",
            "description": "Query and operate PostgreSQL database",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-postgres"],
            "requires_env": ["DATABASE_URL"],
            "category": "database"
        },
    ]

    return {
        "success": True,
        "servers": available_servers,
        "count": len(available_servers)
    }

