"""
Tool Connection API Routes
Endpoints for managing tool connections
"""

from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from datetime import datetime
import uuid

from ...models.tool_connection import (
    ToolConnection,
    CreateToolConnectionRequest,
    UpdateToolConnectionRequest,
    ValidateToolConnectionRequest,
    ToolConnectionValidationResult,
)
from ...services.tool_connection_store import ToolConnectionStore

router = APIRouter(prefix="/api/tool-connections", tags=["tool-connections"])

# Initialize tool connection store
tool_connection_store = ToolConnectionStore()


@router.post("/", response_model=ToolConnection)
async def create_connection(request: CreateToolConnectionRequest, profile_id: str = Query(...)):
    """
    Create a new tool connection

    This endpoint is called when a user adds a new tool integration.
    """
    try:
        # Generate connection ID
        connection_id = str(uuid.uuid4())

        # Create connection
        connection = ToolConnection(
            id=connection_id,
            profile_id=profile_id,
            tool_type=request.tool_type,
            connection_type=request.connection_type,
            name=request.name,
            description=request.description,
            api_key=request.api_key,
            api_secret=request.api_secret,
            oauth_token=request.oauth_token,
            base_url=request.base_url,
            remote_cluster_url=request.remote_cluster_url,
            remote_connection_id=request.remote_connection_id,
            config=request.config,
            associated_roles=request.associated_roles,
            is_active=True,
        )

        return tool_connection_store.save_connection(connection)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create connection: {str(e)}")


@router.get("/", response_model=List[ToolConnection])
async def list_connections(
    profile_id: str = Query(...),
    tool_type: Optional[str] = Query(None, description="Filter by tool type"),
    active_only: bool = Query(True, description="Return only active connections")
):
    """
    List all tool connections for a profile
    """
    try:
        if tool_type:
            connections = tool_connection_store.get_connections_by_tool_type(profile_id, tool_type)
        else:
            connections = tool_connection_store.get_connections_by_profile(profile_id, active_only)

        return connections

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list connections: {str(e)}")


@router.get("/by-role/{role_id}", response_model=List[ToolConnection])
async def get_connections_by_role(role_id: str, profile_id: str = Query(...)):
    """
    Get all tool connections associated with a specific AI role
    """
    try:
        connections = tool_connection_store.get_connections_by_role(profile_id, role_id)
        return connections

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get connections: {str(e)}")


@router.get("/{connection_id}", response_model=ToolConnection)
async def get_connection(connection_id: str, profile_id: str = Query(...)):
    """
    Get a specific tool connection
    """
    try:
        connection = tool_connection_store.get_connection(connection_id, profile_id)

        if not connection:
            raise HTTPException(status_code=404, detail=f"Connection not found: {connection_id}")

        return connection

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get connection: {str(e)}")


@router.patch("/{connection_id}", response_model=ToolConnection)
async def update_connection(
    connection_id: str,
    request: UpdateToolConnectionRequest,
    profile_id: str = Query(...)
):
    """
    Update a tool connection
    """
    try:
        connection = tool_connection_store.get_connection(connection_id, profile_id)

        if not connection:
            raise HTTPException(status_code=404, detail=f"Connection not found: {connection_id}")

        # Update fields
        if request.name is not None:
            connection.name = request.name
        if request.description is not None:
            connection.description = request.description
        if request.api_key is not None:
            connection.api_key = request.api_key
        if request.api_secret is not None:
            connection.api_secret = request.api_secret
        if request.oauth_token is not None:
            connection.oauth_token = request.oauth_token
        if request.base_url is not None:
            connection.base_url = request.base_url
        if request.config is not None:
            connection.config = request.config
        if request.associated_roles is not None:
            connection.associated_roles = request.associated_roles
        if request.is_active is not None:
            connection.is_active = request.is_active

        connection.updated_at = datetime.utcnow()

        return tool_connection_store.save_connection(connection)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update connection: {str(e)}")


@router.delete("/{connection_id}")
async def delete_connection(connection_id: str, profile_id: str = Query(...)):
    """
    Delete a tool connection
    """
    try:
        deleted = tool_connection_store.delete_connection(connection_id, profile_id)

        if not deleted:
            raise HTTPException(status_code=404, detail=f"Connection not found: {connection_id}")

        return {"success": True, "message": f"Connection {connection_id} deleted"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete connection: {str(e)}")


@router.post("/validate", response_model=ToolConnectionValidationResult)
async def validate_connection(
    request: ValidateToolConnectionRequest,
    profile_id: str = Query(...)
):
    """
    Validate a tool connection

    This endpoint tests if the connection is working properly.
    """
    try:
        connection = tool_connection_store.get_connection(request.connection_id, profile_id)

        if not connection:
            raise HTTPException(status_code=404, detail=f"Connection not found: {request.connection_id}")

        # TODO: Implement actual validation logic based on tool type
        # For now, we'll do a basic check
        is_valid = True
        error_message = None

        if connection.connection_type == "local":
            # Check required fields for local connection
            if connection.tool_type == "wordpress":
                if not connection.base_url or not connection.api_key:
                    is_valid = False
                    error_message = "Missing required fields: base_url and api_key"
            elif connection.tool_type == "notion":
                if not connection.api_key:
                    is_valid = False
                    error_message = "Missing required field: api_key"
            elif connection.tool_type == "canva":
                if not connection.api_key and not connection.oauth_token:
                    is_valid = False
                    error_message = "Missing required field: either api_key or oauth_token"
                else:
                    # Try actual validation by calling Canva API
                    try:
                        from ...services.tools.base import ToolConnection
                        from ...services.tools.registry import register_canva_tools, get_mindscape_tool

                        # Register tools if not already registered
                        register_canva_tools(connection)

                        # Test connection
                        tool_id = f"{connection.id}.canva.list_templates"
                        tool = get_mindscape_tool(tool_id)
                        if tool:
                            import asyncio
                            result = asyncio.run(tool.execute({"limit": 1}))
                            if not result.get("success"):
                                is_valid = False
                                error_message = result.get("error", "Canva API connection failed")
                    except Exception as e:
                        is_valid = False
                        error_message = f"Canva validation error: {str(e)}"

        # Update validation status
        tool_connection_store.update_validation_status(
            request.connection_id,
            profile_id,
            is_valid,
            error_message
        )

        return ToolConnectionValidationResult(
            connection_id=request.connection_id,
            is_valid=is_valid,
            error_message=error_message,
            validated_at=datetime.utcnow(),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to validate connection: {str(e)}")


@router.post("/{connection_id}/record-usage")
async def record_connection_usage(
    connection_id: str,
    profile_id: str = Query(...)
):
    """
    Record that a connection was used

    This should be called after each tool invocation.
    """
    try:
        tool_connection_store.record_connection_usage(connection_id, profile_id)
        return {"success": True}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to record usage: {str(e)}")


@router.get("/{connection_id}/statistics")
async def get_connection_statistics(connection_id: str, profile_id: str = Query(...)):
    """
    Get usage statistics for a connection
    """
    try:
        connection = tool_connection_store.get_connection(connection_id, profile_id)

        if not connection:
            raise HTTPException(status_code=404, detail=f"Connection not found: {connection_id}")

        return {
            "connection_id": connection.id,
            "tool_type": connection.tool_type,
            "name": connection.name,
            "usage_count": connection.usage_count,
            "last_used_at": connection.last_used_at.isoformat() if connection.last_used_at else None,
            "is_validated": connection.is_validated,
            "last_validated_at": connection.last_validated_at.isoformat() if connection.last_validated_at else None,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get statistics: {str(e)}")
