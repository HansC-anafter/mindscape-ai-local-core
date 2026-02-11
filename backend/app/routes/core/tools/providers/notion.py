"""
Notion tool provider routes
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)

from backend.app.models.tool_registry import ToolConnectionModel
from backend.app.services.tool_registry import ToolRegistryService
from backend.app.services.tools.discovery_provider import ToolConfig
from ..base import get_tool_registry, raise_api_error

router = APIRouter(prefix="/api/v1/tools", tags=["tools"])


class NotionConnectionRequest(BaseModel):
    """Notion connection request"""
    connection_id: str
    name: str
    api_key: str = Field(..., description="Notion Integration Token (starts with 'secret_')")


@router.post("/notion/discover", response_model=Dict[str, Any])
async def discover_notion_capabilities(
    request: NotionConnectionRequest,
    registry: ToolRegistryService = Depends(get_tool_registry),
):
    """
    Discover Notion workspace capabilities

    Requires Notion Integration Token (create at notion.so/my-integrations)

    Example:
        POST /api/tools/notion/discover
        {
            "connection_id": "notion-workspace-1",
            "name": "My Notion Workspace",
            "api_key": "secret_..."
        }
    """
    try:
        config = ToolConfig(
            tool_type="notion",
            connection_type="http_api",
            api_key=request.api_key
        )

        result = await registry.discover_tool_capabilities(
            provider_name="notion",
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
        raise_api_error(500, f"Discovery failed: {str(e)}")


@router.post("/notion/connect", response_model=ToolConnectionModel)
async def create_notion_connection(
    request: NotionConnectionRequest,
    profile_id: str = Query("default-user", description="Profile ID for multi-tenant support"),
    registry: ToolRegistryService = Depends(get_tool_registry),
):
    """Create a Notion connection (without discovery)"""
    try:
        connection = ToolConnectionModel(
            id=request.connection_id,
            profile_id=profile_id,
            tool_type="notion",
            connection_type="local",
            name=request.name,
            description=f"Notion connection: {request.name}",
            api_key=request.api_key,
            is_active=True,
            created_at=_utc_now(),
            updated_at=_utc_now()
        )
        conn = registry.create_connection(connection)
        return conn
    except Exception as e:
        raise_api_error(500, f"Failed to create connection: {str(e)}")

