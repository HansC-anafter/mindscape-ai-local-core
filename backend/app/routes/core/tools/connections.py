"""
Connection management routes

Handles CRUD operations for tool connections with multi-tenant support.
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Optional
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)

from backend.app.models.tool_registry import ToolConnectionModel
from backend.app.models.tool_connection import (
    CreateToolConnectionRequest,
    UpdateToolConnectionRequest,
    ValidateToolConnectionRequest,
    ToolConnectionValidationResult,
)
from backend.app.services.tool_registry import ToolRegistryService
from .base import get_tool_registry, raise_api_error

router = APIRouter(prefix="/api/v1/tools", tags=["tools"])


@router.post("/connections", response_model=ToolConnectionModel)
async def create_connection(
    request: CreateToolConnectionRequest,
    profile_id: str = Query(..., description="Profile ID"),
    registry: ToolRegistryService = Depends(get_tool_registry),
):
    """
    Create a new tool connection

    Args:
        request: Connection creation request
        profile_id: Profile ID for multi-tenant support
        registry: Tool registry service

    Returns:
        Created connection
    """
    import uuid

    connection_id = str(uuid.uuid4())

    # Map request to ToolConnectionModel
    connection = ToolConnectionModel(
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
        x_platform=request.x_platform,
        is_active=True,
    )

    created_connection = registry.create_connection(connection)

    # Remote tools are now registered via system capability packs in cloud repo

    return created_connection


@router.get("/connections", response_model=List[ToolConnectionModel])
async def list_connections(
    profile_id: Optional[str] = Query(None, description="Profile ID filter"),
    tool_type: Optional[str] = Query(None, description="Filter by tool type"),
    active_only: bool = Query(True, description="Return only active connections"),
    registry: ToolRegistryService = Depends(get_tool_registry),
):
    """
    List tool connections

    Args:
        profile_id: Optional profile ID to filter connections
        tool_type: Optional tool type filter
        active_only: If True, return only active connections
        registry: Tool registry service

    Returns:
        List of tool connections
    """
    if profile_id:
        if tool_type:
            connections = registry.get_connections_by_tool_type(profile_id, tool_type)
        else:
            connections = registry.get_connections_by_profile(profile_id, active_only)
    else:
        connections = registry.get_connections()
        if active_only:
            connections = [c for c in connections if c.is_active]
        if tool_type:
            connections = [c for c in connections if c.tool_type == tool_type]

    return connections


@router.get("/connections/by-role/{role_id}", response_model=List[ToolConnectionModel])
async def get_connections_by_role(
    role_id: str,
    profile_id: str = Query(..., description="Profile ID"),
    registry: ToolRegistryService = Depends(get_tool_registry),
):
    """
    Get all connections associated with a specific AI role

    Args:
        role_id: AI role ID
        profile_id: Profile ID
        registry: Tool registry service

    Returns:
        List of tool connections
    """
    return registry.get_connections_by_role(profile_id, role_id)


@router.get("/connections/{connection_id}", response_model=ToolConnectionModel)
async def get_connection(
    connection_id: str,
    profile_id: Optional[str] = Query(None, description="Profile ID"),
    registry: ToolRegistryService = Depends(get_tool_registry),
):
    """
    Get a specific connection

    Args:
        connection_id: Connection ID
        profile_id: Optional profile ID
        registry: Tool registry service

    Returns:
        Tool connection
    """
    conn = registry.get_connection(connection_id, profile_id)
    if not conn:
        raise_api_error(404, "Connection not found")
    return conn


@router.patch("/connections/{connection_id}", response_model=ToolConnectionModel)
async def update_connection(
    connection_id: str,
    request: UpdateToolConnectionRequest,
    profile_id: str = Query(..., description="Profile ID"),
    registry: ToolRegistryService = Depends(get_tool_registry),
):
    """
    Update a tool connection

    Args:
        connection_id: Connection ID
        request: Update request
        profile_id: Profile ID
        registry: Tool registry service

    Returns:
        Updated connection
    """
    conn = registry.get_connection(connection_id, profile_id)
    if not conn:
        raise_api_error(404, "Connection not found")

    # Update fields
    if request.name is not None:
        conn.name = request.name
    if request.description is not None:
        conn.description = request.description
    if request.api_key is not None:
        conn.api_key = request.api_key
    if request.api_secret is not None:
        conn.api_secret = request.api_secret
    if request.oauth_token is not None:
        conn.oauth_token = request.oauth_token
    if request.base_url is not None:
        conn.base_url = request.base_url
    if request.config is not None:
        conn.config = request.config
    if request.associated_roles is not None:
        conn.associated_roles = request.associated_roles
    if request.is_active is not None:
        conn.is_active = request.is_active
    if request.x_platform is not None:
        conn.x_platform = request.x_platform

    conn.updated_at = _utc_now()

    return registry.update_connection(conn)


@router.delete("/connections/{connection_id}")
async def delete_connection(
    connection_id: str,
    profile_id: Optional[str] = Query(None, description="Profile ID"),
    registry: ToolRegistryService = Depends(get_tool_registry),
):
    """
    Delete a connection and all its tools

    Args:
        connection_id: Connection ID
        profile_id: Optional profile ID
        registry: Tool registry service

    Returns:
        Success response
    """
    success = registry.delete_connection(connection_id, profile_id)
    if not success:
        raise_api_error(404, "Connection not found")
    return {"success": True}


@router.post("/connections/validate", response_model=ToolConnectionValidationResult)
async def validate_connection(
    request: ValidateToolConnectionRequest,
    profile_id: str = Query(..., description="Profile ID"),
    registry: ToolRegistryService = Depends(get_tool_registry),
):
    """
    Validate a tool connection

    Args:
        request: Validation request
        profile_id: Profile ID
        registry: Tool registry service

    Returns:
        Validation result
    """
    conn = registry.get_connection(request.connection_id, profile_id)
    if not conn:
        raise_api_error(404, "Connection not found")

    # For now, do basic validation
    is_valid = True
    error_message = None

    if conn.connection_type == "local":
        if conn.tool_type == "wordpress":
            if not conn.base_url or not conn.api_key:
                is_valid = False
                error_message = "Missing required fields: base_url and api_key"
        elif conn.tool_type == "notion":
            if not conn.api_key:
                is_valid = False
                error_message = "Missing required field: api_key"
        elif conn.tool_type == "canva":
            if not conn.api_key and not conn.oauth_token:
                is_valid = False
                error_message = "Missing required field: either api_key or oauth_token"

    # Update validation status
    registry.update_validation_status(
        request.connection_id,
        profile_id,
        is_valid,
        error_message
    )

    return ToolConnectionValidationResult(
        connection_id=request.connection_id,
        is_valid=is_valid,
        error_message=error_message,
        validated_at=_utc_now(),
    )


@router.post("/connections/{connection_id}/record-usage")
async def record_connection_usage(
    connection_id: str,
    profile_id: str = Query(..., description="Profile ID"),
    registry: ToolRegistryService = Depends(get_tool_registry),
):
    """
    Record that a connection was used

    Args:
        connection_id: Connection ID
        profile_id: Profile ID
        registry: Tool registry service

    Returns:
        Success response
    """
    registry.record_connection_usage(connection_id, profile_id)
    return {"success": True}


@router.get("/connections/{connection_id}/statistics")
async def get_connection_statistics(
    connection_id: str,
    profile_id: str = Query(..., description="Profile ID"),
    registry: ToolRegistryService = Depends(get_tool_registry),
):
    """
    Get usage statistics for a connection

    Args:
        connection_id: Connection ID
        profile_id: Profile ID
        registry: Tool registry service

    Returns:
        Connection statistics
    """
    conn = registry.get_connection(connection_id, profile_id)
    if not conn:
        raise_api_error(404, "Connection not found")

    return {
        "connection_id": conn.id,
        "tool_type": conn.tool_type,
        "name": conn.name,
        "usage_count": conn.usage_count,
        "last_used_at": conn.last_used_at.isoformat() if conn.last_used_at else None,
        "is_validated": conn.is_validated,
        "last_validated_at": conn.last_validated_at.isoformat() if conn.last_validated_at else None,
    }
