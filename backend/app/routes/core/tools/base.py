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
from pathlib import Path
import yaml
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

def _load_capability_tools_from_installed_manifests() -> List[RegisteredTool]:
    """
    Fallback: load capability tools from installed capability manifests.

    Why this exists:
    - `ToolListService._get_capability_tools()` relies on capability registry state.
    - During hot-reload / startup ordering issues, registry-based enumeration can be empty.
    - Installed manifests in `backend/app/capabilities/*/manifest.yaml` are the install SOT.
    """
    try:
        # Resolve `backend/app` directory from this file: backend/app/routes/core/tools/base.py
        app_dir = Path(__file__).resolve().parents[3]  # .../backend/app
        capabilities_dir = app_dir / "capabilities"
        if not capabilities_dir.exists():
            return []

        results: List[RegisteredTool] = []
        for cap_dir in capabilities_dir.iterdir():
            if not cap_dir.is_dir():
                continue
            manifest_path = cap_dir / "manifest.yaml"
            if not manifest_path.exists():
                continue

            try:
                manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
            except Exception as e:
                logger.debug(f"Failed to read manifest for {cap_dir.name}: {e}")
                continue

            cap_code = manifest.get("code") or cap_dir.name
            for tool_cfg in manifest.get("tools", []) or []:
                if not isinstance(tool_cfg, dict):
                    continue
                tool_code = tool_cfg.get("code") or tool_cfg.get("name")
                if not tool_code:
                    continue
                tool_id = f"{cap_code}.{tool_code}"
                results.append(
                    RegisteredTool(
                        tool_id=tool_id,
                        site_id=cap_code,
                        provider="capability",
                        display_name=tool_cfg.get("display_name") or tool_code,
                        origin_capability_id=tool_id,
                        category=tool_cfg.get("category") or "capability",
                        description=tool_cfg.get("description") or "",
                        endpoint="",
                        methods=[],
                        danger_level="low",
                        input_schema=tool_cfg.get("input_schema") or {},
                        enabled=True,
                        read_only=False,
                        allowed_agent_roles=[],
                        side_effect_level=tool_cfg.get("side_effect_level") or "none",
                        scope="system",
                    )
                )

        return results
    except Exception as e:
        logger.warning(f"Fallback capability tool load failed: {e}", exc_info=True)
        return []


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
        for tool_info in capability_tools:
            # Skip if already in tools list (by tool_id)
            if any(t.tool_id == tool_info.tool_id for t in tools):
                continue

            # Apply filters
            if enabled_only and not tool_info.enabled:
                continue
            if category and tool_info.category != category:
                continue

            # Convert ToolInfo to RegisteredTool
            registered_tool = RegisteredTool(
                tool_id=tool_info.tool_id,
                site_id="capability",
                provider="capability",
                display_name=tool_info.name,
                origin_capability_id=tool_info.tool_id,
                category=tool_info.category,
                description=tool_info.description,
                endpoint="",
                methods=[],
                danger_level="low",
                input_schema={},
                enabled=tool_info.enabled,
                read_only=False,
                allowed_agent_roles=[],
                side_effect_level="none",
                scope="system",
            )
            tools.append(registered_tool)
            added_count += 1
        logger.info(f"list_tools: Added {added_count} capability tools to response")
    except Exception as e:
        logger.warning(f"Failed to load capability tools: {e}", exc_info=True)

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
