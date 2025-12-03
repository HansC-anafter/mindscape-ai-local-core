"""
Airtable tool provider routes
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime
import logging

from backend.app.models.tool_registry import ToolConnectionModel
from backend.app.services.tool_registry import ToolRegistryService
from backend.app.services.tools.discovery_provider import ToolConfig
from ..base import get_tool_registry, raise_api_error

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/tools", tags=["tools"])


class AirtableConnectionRequest(BaseModel):
    """Airtable connection request"""
    connection_id: str
    name: str
    api_key: str = Field(..., description="Airtable Personal Access Token (starts with 'pat')")


@router.post("/airtable/discover", response_model=Dict[str, Any])
async def discover_airtable_capabilities(
    request: AirtableConnectionRequest,
    registry: ToolRegistryService = Depends(get_tool_registry),
):
    """
    Discover Airtable workspace capabilities using discovery provider

    Uses the new architecture ToolRegistryService with AirtableDiscoveryProvider.

    Example:
        POST /api/v1/tools/airtable/discover
        {
            "connection_id": "airtable-workspace-1",
            "name": "My Airtable Workspace",
            "api_key": "pat..."
        }
    """
    try:
        config = ToolConfig(
            tool_type="airtable",
            connection_type="http_api",
            api_key=request.api_key
        )

        result = await registry.discover_tool_capabilities(
            provider_name="airtable",
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
        logger.error(f"Airtable discovery failed: {e}", exc_info=True)
        raise_api_error(500, f"Discovery failed: {str(e)}")


@router.post("/airtable/connect", response_model=ToolConnectionModel)
async def create_airtable_connection(
    request: AirtableConnectionRequest,
    profile_id: str = Query("default-user", description="Profile ID for multi-tenant support"),
    registry: ToolRegistryService = Depends(get_tool_registry),
):
    """
    Create an Airtable connection

    Supports Personal Access Token authentication.
    """
    try:
        if not request.api_key:
            raise ValueError("Airtable API key (Personal Access Token) is required")

        # Create ToolConnectionModel instance
        connection = ToolConnectionModel(
            id=request.connection_id,
            profile_id=profile_id,
            tool_type="airtable",
            connection_type="local",
            name=request.name,
            description=f"Airtable connection: {request.name}",
            api_key=request.api_key,
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        # Create connection in registry
        conn_model = registry.create_connection(connection)

        # Register tools
        try:
            from backend.app.services.tools.base import ToolConnection
            from backend.app.services.tools.registry import register_airtable_tools

            tool_connection = ToolConnection(
                id=conn_model.id,
                tool_type="airtable",
                connection_type="local",
                api_key=request.api_key,
                name=conn_model.name
            )
            tools = register_airtable_tools(tool_connection)
            logger.info(f"Registered {len(tools)} Airtable tools for connection: {request.connection_id}")
        except ImportError:
            logger.warning("Airtable tools registration not available, skipping tool registration")

        return conn_model
    except Exception as e:
        logger.error(f"Failed to create Airtable connection: {e}", exc_info=True)
        raise_api_error(500, f"Failed to create connection: {str(e)}")


@router.post("/airtable/validate", response_model=Dict[str, Any])
async def validate_airtable_connection(
    connection_id: str,
    profile_id: str = Query("default-user", description="Profile ID"),
    registry: ToolRegistryService = Depends(get_tool_registry),
):
    """
    Validate Airtable connection

    Tests if the Airtable API connection is working by calling meta/bases.
    """
    try:
        connection_model = registry.get_connection(connection_id=connection_id, profile_id=profile_id)
        if not connection_model:
            raise_api_error(404, f"Airtable connection not found: {connection_id}")

        api_key = connection_model.api_key
        if not api_key:
            raise_api_error(400, "No API key found in connection")

        # Test connection by calling meta/bases
        import aiohttp
        url = "https://api.airtable.com/v0/meta/bases"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Airtable API error: {response.status} - {error_text}")

                result = await response.json()

                # Update connection validation status
                registry.update_validation_status(
                    connection_id=connection_id,
                    profile_id=profile_id,
                    is_valid=True,
                    error_message=None
                )

                return {
                    "success": True,
                    "valid": True,
                    "bases_count": len(result.get("bases", [])),
                    "message": "Airtable connection is valid"
                }
    except Exception as e:
        logger.error(f"Failed to validate Airtable connection: {e}", exc_info=True)
        raise_api_error(500, f"Failed to validate connection: {str(e)}")

