"""Sandbox port manager routes."""

from typing import Any, Dict

from fastapi import APIRouter, Path as PathParam

from backend.app.services.sandbox.port_manager import port_manager

router = APIRouter()

@router.get("/ports/status", response_model=Dict[str, Any])
async def get_port_manager_status(
    workspace_id: str = PathParam(..., description="Workspace identifier")
):
    """
    Get port manager status

    Returns current port allocation status including:
    - Configured port range
    - Number of allocated/available ports
    - Current allocations (sandbox_id -> port mapping)
    """
    return port_manager.get_status()

@router.post("/ports/cleanup", response_model=Dict[str, Any])
async def cleanup_stale_ports(
    workspace_id: str = PathParam(..., description="Workspace identifier")
):
    """
    Cleanup stale port allocations

    Removes allocations for ports that are no longer in use.
    Useful after server restarts or crashes.
    """
    cleaned = port_manager.cleanup_stale()
    return {
        "cleaned": cleaned,
        "status": port_manager.get_status()
    }
