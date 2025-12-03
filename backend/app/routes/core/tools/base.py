"""
Base tools router with shared models, dependencies, and core endpoints.

Contains:
- Shared request/response models
- ToolRegistry dependency injection
- Core tool management endpoints (providers, discover, list, get, update, agent tools)
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Optional, Dict, Any
from pydantic import BaseModel

from backend.app.models.tool_registry import RegisteredTool
from backend.app.services.tool_registry import ToolRegistryService
from backend.app.services.tools.discovery_provider import ToolConfig
import os
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/tools", tags=["tools"])


def get_tool_registry() -> ToolRegistryService:
    """
    Initialize Tool Registry and register community extensions
    """
    data_dir = os.getenv("DATA_DIR", "./data")
    registry = ToolRegistryService(data_dir=data_dir)

    # Register external extensions (WordPress provider)
    try:
        from backend.app.extensions.console_kit import register_console_kit_tools
        register_console_kit_tools(registry)
    except ImportError:
        pass  # External extension not installed, skip

    # Register community extensions (optional)
    try:
        from backend.app.extensions.community import register_community_extensions
        register_community_extensions(registry)
    except ImportError:
        pass  # Community extensions not installed, skip

    return registry


def raise_api_error(status_code: int, detail: str) -> None:
    """
    Helper function to raise HTTPException with consistent error handling
    """
    raise HTTPException(status_code=status_code, detail=detail)


# Request/Response models
class DiscoverToolsRequest(BaseModel):
    """Generic tool discovery request"""
    provider: str
    config: ToolConfig
    connection_id: Optional[str] = None


class ToolUpdateRequest(BaseModel):
    """Tool update request"""
    enabled: Optional[bool] = None
    read_only: Optional[bool] = None
    allowed_agent_roles: Optional[List[str]] = None


# Core routes
@router.get("/providers", response_model=Dict[str, Any])
async def get_available_providers(
    registry: ToolRegistryService = Depends(get_tool_registry),
):
    """
    Get all available tool discovery providers

    Returns:
    - Core built-in providers (e.g., generic_http)
    - Extension providers (e.g., wordpress, notion - if installed)

    Example Response:
        {
            "providers": [
                {
                    "provider": "generic_http",
                    "display_name": "Generic HTTP API",
                    "description": "...",
                    "required_config": ["base_url"],
                    ...
                },
                {
                    "provider": "wordpress",
                    "display_name": "WordPress",
                    "description": "...",
                    "required_config": ["base_url", "api_key", "api_secret"],
                    ...
                }
            ]
        }
    """
    providers = registry.get_available_providers()
    return {
        "providers": providers
    }


@router.post("/discover", response_model=Dict[str, Any])
async def discover_tool_capabilities(
    request: DiscoverToolsRequest,
    registry: ToolRegistryService = Depends(get_tool_registry),
):
    """
    Discover tool capabilities using specified provider (generic endpoint)

    Supported providers:
    - 'generic_http': Generic HTTP API
    - 'wordpress': WordPress site (requires external extension)
    - 'notion': Notion workspace (requires external extension)
    - Other user-defined providers

    Example Request:
        POST /api/tools/discover
        {
            "provider": "wordpress",
            "config": {
                "tool_type": "wordpress",
                "connection_type": "http_api",
                "base_url": "https://mysite.com",
                "api_key": "admin",
                "api_secret": "xxxx xxxx xxxx xxxx"
            },
            "connection_id": "my-wp-site"
        }

    Example Response:
        {
            "provider": "wordpress",
            "connection_id": "my-wp-site",
            "discovered_tools": [...],
            "discovery_metadata": {...}
        }
    """
    try:
        result = await registry.discover_tool_capabilities(
            provider_name=request.provider,
            config=request.config,
            connection_id=request.connection_id
        )
        return result
    except ValueError as e:
        raise_api_error(400, str(e))
    except Exception as e:
        raise_api_error(500, f"Discovery failed: {str(e)}")


@router.get("/", response_model=List[RegisteredTool])
async def list_tools(
    site_id: Optional[str] = None,
    category: Optional[str] = None,
    enabled_only: bool = True,
    registry: ToolRegistryService = Depends(get_tool_registry),
):
    """List registered tools with optional filters"""
    tools = registry.get_tools(
        site_id=site_id,
        category=category,
        enabled_only=enabled_only,
    )
    return tools


@router.get("/{tool_id}", response_model=RegisteredTool)
async def get_tool(
    tool_id: str,
    registry: ToolRegistryService = Depends(get_tool_registry),
):
    """Get a specific tool"""
    tool = registry.get_tool(tool_id)
    if not tool:
        raise_api_error(404, "Tool not found")
    return tool


@router.patch("/{tool_id}", response_model=RegisteredTool)
async def update_tool(
    tool_id: str,
    request: ToolUpdateRequest,
    registry: ToolRegistryService = Depends(get_tool_registry),
):
    """Update tool settings (enable/disable, read-only mode, allowed roles)"""
    tool = registry.update_tool(
        tool_id=tool_id,
        enabled=request.enabled,
        read_only=request.read_only,
        allowed_agent_roles=request.allowed_agent_roles,
    )
    if not tool:
        raise_api_error(404, "Tool not found")
    return tool


@router.get("/agent/{agent_role}", response_model=List[RegisteredTool])
async def get_tools_for_agent(
    agent_role: str,
    registry: ToolRegistryService = Depends(get_tool_registry),
):
    """Get tools available for a specific agent role"""
    tools = registry.get_tools_for_agent_role(agent_role)
    return tools
