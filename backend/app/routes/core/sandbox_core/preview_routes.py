"""Sandbox preview server routes."""

import logging
from typing import Any, Dict

from fastapi import APIRouter, Body, Path as PathParam

from backend.app.services.sandbox.preview_server import SandboxPreviewServer
from backend.app.services.sandbox.workspace_sync import get_workspace_sync_service

from .schemas import EnsurePreviewRequest, StartPreviewRequest
from .state import (
    _get_preview_server_key,
    _preview_servers,
    sandbox_manager,
    store,
)

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/preview/ensure", response_model=Dict[str, Any])
async def ensure_preview_ready(
    workspace_id: str = PathParam(..., description="Workspace identifier"),
    request: EnsurePreviewRequest = Body(...)
):
    """
    Ensure preview is ready - create/sync sandbox and start server.

    This is the main entry point for preview. It will:
    1. Find or create a web_page sandbox
    2. Sync workspace files to sandbox
    3. Initialize Next.js template if needed
    4. Start preview server

    If sandbox is corrupted, it will be rebuilt from workspace files.

    Returns:
        - sandbox_id: Sandbox identifier
        - synced_files: List of synced files
        - preview_url: Preview server URL
        - status: Current status
    """
    try:
        sync_service = get_workspace_sync_service(store)

        result = await sync_service.ensure_sandbox_for_preview(
            workspace_id=workspace_id,
            project_id=request.project_id
        )

        if result.get("status") == "error":
            return {
                "success": False,
                "error": result.get("error", "Failed to ensure sandbox"),
                "sandbox_id": None,
                "preview_url": None,
                "synced_files": []
            }

        sandbox_id = result["sandbox_id"]

        sandbox = await sandbox_manager.get_sandbox(sandbox_id, workspace_id)
        if not sandbox:
            return {
                "success": False,
                "error": "Sandbox not found after creation",
                "sandbox_id": sandbox_id,
                "preview_url": None,
                "synced_files": result.get("synced_files", [])
            }

        server_key = _get_preview_server_key(workspace_id, sandbox_id)

        # Check if server already running
        if server_key in _preview_servers:
            existing_server = _preview_servers[server_key]
            if existing_server.is_running:
                return {
                    "success": True,
                    "sandbox_id": sandbox_id,
                    "preview_url": existing_server.get_preview_url(),
                    "port": existing_server.actual_port or existing_server.port,
                    "synced_files": result.get("synced_files", []),
                    "status": "ready",
                    "message": "Preview already running"
                }

        # Get sandbox path and start server
        # Use storage.base_path and current directory
        sandbox_path = sandbox.storage.current_path
        if not sandbox_path.exists():
            return {
                "success": False,
                "error": f"Sandbox path does not exist: {sandbox_path}",
                "sandbox_id": sandbox_id,
                "preview_url": None,
                "synced_files": result.get("synced_files", [])
            }

        preview_server = SandboxPreviewServer(
            sandbox_id=sandbox_id,
            sandbox_path=sandbox_path,
            preferred_port=request.port
        )
        server_result = await preview_server.start()

        if server_result["success"]:
            _preview_servers[server_key] = preview_server
            logger.info(f"Started preview server for {workspace_id}:{sandbox_id} on port {server_result['port']}")

        return {
            "success": server_result["success"],
            "sandbox_id": sandbox_id,
            "preview_url": server_result.get("url"),
            "port": server_result.get("port"),
            "synced_files": result.get("synced_files", []),
            "status": "ready" if server_result["success"] else "error",
            "error": server_result.get("error"),
            "port_conflict": server_result.get("port_conflict", False)
        }

    except Exception as e:
        logger.error(f"Failed to ensure preview: {e}")
        return {
            "success": False,
            "error": str(e),
            "sandbox_id": None,
            "preview_url": None,
            "synced_files": []
        }

@router.post("/{sandbox_id}/preview/start", response_model=Dict[str, Any])
async def start_preview_server(
    workspace_id: str = PathParam(..., description="Workspace identifier"),
    sandbox_id: str = PathParam(..., description="Sandbox identifier"),
    request: StartPreviewRequest = Body(...)
):
    """
    Start preview server for sandbox

    Starts a development server for real-time preview of web pages.
    Automatically handles port conflicts.

    Returns:
        - success: True if started successfully
        - port: Actual port number used
        - url: Preview server URL
        - error: Error message if failed
        - port_conflict: True if original port was in use
    """
    try:
        sandbox = await sandbox_manager.get_sandbox(sandbox_id, workspace_id)
        if not sandbox:
            raise HTTPException(status_code=404, detail="Sandbox not found")

        server_key = _get_preview_server_key(workspace_id, sandbox_id)

        # Check if server already running
        if server_key in _preview_servers:
            existing_server = _preview_servers[server_key]
            if existing_server.is_running:
                return {
                    "success": True,
                    "port": existing_server.actual_port,
                    "url": existing_server.get_preview_url(),
                    "error": None,
                    "port_conflict": False,
                    "message": "Preview already running"
                }

        # Get sandbox path
        sandbox_path = sandbox.storage.current_path
        if not sandbox_path.exists():
            return {
                "success": False,
                "port": None,
                "url": None,
                "error": f"Sandbox path does not exist: {sandbox_path}",
                "port_conflict": False
            }

        # Create and start preview server
        preview_server = SandboxPreviewServer(
            sandbox_id=sandbox_id,
            sandbox_path=sandbox_path,
            preferred_port=request.port
        )
        result = await preview_server.start()

        if result["success"]:
            _preview_servers[server_key] = preview_server
            logger.info(f"Started preview server for {server_key} on port {result['port']}")

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start preview server: {e}")
        return {
            "success": False,
            "port": None,
            "url": None,
            "error": str(e),
            "port_conflict": False
        }

@router.post("/{sandbox_id}/preview/stop", response_model=Dict[str, Any])
async def stop_preview_server(
    workspace_id: str = PathParam(..., description="Workspace identifier"),
    sandbox_id: str = PathParam(..., description="Sandbox identifier")
):
    """
    Stop preview server for sandbox

    Returns:
        - success: True if stopped successfully
    """
    try:
        server_key = _get_preview_server_key(workspace_id, sandbox_id)

        if server_key not in _preview_servers:
            return {"success": True, "message": "No preview server running"}

        preview_server = _preview_servers[server_key]
        success = await preview_server.stop()

        if success:
            del _preview_servers[server_key]
            logger.info(f"Stopped preview server for {server_key}")

        return {"success": success}

    except Exception as e:
        logger.error(f"Failed to stop preview server: {e}")
        return {"success": False, "error": str(e)}

@router.get("/{sandbox_id}/preview/status", response_model=Dict[str, Any])
async def get_preview_server_status(
    workspace_id: str = PathParam(..., description="Workspace identifier"),
    sandbox_id: str = PathParam(..., description="Sandbox identifier")
):
    """
    Get preview server status

    Returns:
        - running: True if server is running
        - port: Port number if running
        - url: Preview URL if running
        - error: Last error message if any
    """
    try:
        server_key = _get_preview_server_key(workspace_id, sandbox_id)

        if server_key not in _preview_servers:
            return {
                "running": False,
                "port": None,
                "url": None,
                "error": None
            }

        preview_server = _preview_servers[server_key]

        # Check if still healthy
        is_healthy = await preview_server.is_healthy()

        if not is_healthy and preview_server.is_running:
            # Server crashed, clean up
            preview_server.is_running = False
            del _preview_servers[server_key]
            return {
                "running": False,
                "port": None,
                "url": None,
                "error": "Preview server crashed"
            }

        return {
            "running": preview_server.is_running,
            "port": preview_server.actual_port if preview_server.is_running else None,
            "url": preview_server.get_preview_url() if preview_server.is_running else None,
            "error": preview_server.error_message
        }

    except Exception as e:
        logger.error(f"Failed to get preview server status: {e}")
        return {
            "running": False,
            "port": None,
            "url": None,
            "error": str(e)
        }


# Port Manager API
