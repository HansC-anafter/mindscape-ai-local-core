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
from .manifest_tools import _load_capability_tools_from_installed_manifests
from .tool_policy import (
    _as_dict,
    _coerce_bool,
    _manifest_tool_input_schema,
    _overlay_registered_tool_policy_metadata,
    _planner_effect,
    _registered_tool_from_capability_tool_info,
    _registered_tool_from_manifest_tool,
    _tool_cfg_from_tool_info_metadata,
    _tool_cfg_read_only,
    _tool_cfg_risk_class,
    _tool_cfg_side_effect_level,
    _tool_info_has_policy_metadata,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/tools", tags=["tools"])

REPORTING_TOOL_IDS = {
    "core.workspace_write_html_report",
    "workspace_write_html_report",
}

import functools

@functools.lru_cache()
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
    """List registered tools with optional filters

    Also includes capability tools from ToolListService.
    """
    tools = registry.get_tools(
        site_id=site_id,
        category=category,
        enabled_only=enabled_only,
    )

    # Also include capability tools from ToolListService
    try:
        from backend.app.services.tool_list_service import ToolListService
        tool_list_service = ToolListService()
        capability_tools = tool_list_service._get_capability_tools()
        logger.info(f"list_tools: Found {len(capability_tools)} capability tools")

        # Convert ToolInfo to RegisteredTool format
        added_count = 0
        overlay_count = 0
        for tool_info in capability_tools:
            existing_tool = next(
                (tool for tool in tools if tool.tool_id == tool_info.tool_id),
                None,
            )
            if existing_tool is not None:
                if _tool_info_has_policy_metadata(tool_info):
                    registered_tool = _registered_tool_from_capability_tool_info(tool_info)
                    _overlay_registered_tool_policy_metadata(
                        existing_tool,
                        registered_tool,
                    )
                    overlay_count += 1
                continue

            # Apply filters
            if enabled_only and not tool_info.enabled:
                continue
            if category and tool_info.category != category:
                continue

            # Convert ToolInfo to RegisteredTool while preserving manifest policy metadata.
            registered_tool = _registered_tool_from_capability_tool_info(tool_info)
            tools.append(registered_tool)
            added_count += 1
        logger.info(
            "list_tools: Added %d capability tools to response, overlaid %d capability policy metadata entries",
            added_count,
            overlay_count,
        )
    except Exception as e:
        logger.warning(f"Failed to load capability tools: {e}", exc_info=True)

    # Include only the core reporting writer from builtin tools so the general
    # catalog can surface the Meeting Engine report output primitive without
    # broadening this legacy list route to every builtin tool.
    try:
        from backend.app.services.tool_list_service import ToolListService

        tool_list_service = ToolListService()
        builtin_tools = tool_list_service._get_builtin_tools()
        for tool_info in builtin_tools:
            if tool_info.tool_id not in REPORTING_TOOL_IDS:
                continue
            if any(t.tool_id == tool_info.tool_id for t in tools):
                continue
            tool = tool_info.metadata.get("tool") if tool_info.metadata else None
            metadata = getattr(tool, "metadata", None)
            input_schema = (
                metadata.input_schema.model_dump()
                if metadata is not None and getattr(metadata, "input_schema", None)
                else {}
            )
            danger_level = (
                getattr(metadata, "danger_level", "medium")
                if metadata is not None
                else "medium"
            )
            tools.append(
                RegisteredTool(
                    tool_id=tool_info.tool_id,
                    site_id="builtin",
                    provider="builtin",
                    display_name=tool_info.name,
                    origin_capability_id="core.reporting",
                    category=tool_info.category,
                    description=tool_info.description,
                    endpoint="",
                    methods=[],
                    danger_level=str(danger_level),
                    input_schema=input_schema,
                    enabled=tool_info.enabled,
                    read_only=False,
                    allowed_agent_roles=[],
                    side_effect_level="soft_write",
                    scope="system",
                )
            )
    except Exception as e:
        logger.warning(f"Failed to load reporting builtin tools: {e}", exc_info=True)

    # Fallback: if capability tools are still missing, load them from installed manifests.
    try:
        if not any((t.provider == "capability") for t in tools):
            fallback_tools = _load_capability_tools_from_installed_manifests()
            added = 0
            for t in fallback_tools:
                if any(existing.tool_id == t.tool_id for existing in tools):
                    continue
                if enabled_only and not t.enabled:
                    continue
                if category and t.category != category:
                    continue
                if site_id and t.site_id != site_id:
                    continue
                tools.append(t)
                added += 1
            logger.info(f"list_tools: Fallback added {added} capability tools from manifests")
    except Exception as e:
        logger.warning(f"Failed to load fallback capability tools: {e}", exc_info=True)

    return tools


@router.get("/{tool_id}", response_model=RegisteredTool)
async def get_tool(
    tool_id: str,
    registry: ToolRegistryService = Depends(get_tool_registry),
):
    """Get a specific tool"""
    tool = registry.get_tool(tool_id)
    if not tool:
        # Fallback: capability tools may not be stored in ToolRegistryService DB.
        for t in _load_capability_tools_from_installed_manifests():
            if t.tool_id == tool_id:
                return t
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
