"""
Sandbox API routes

Provides REST API for sandbox management, file operations, and version control.
"""

import logging
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Path as PathParam, Query, Body
from pydantic import BaseModel, Field

from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.sandbox.sandbox_manager import SandboxManager
from backend.app.services.sandbox.preview_server import SandboxPreviewServer
from backend.app.services.sandbox.workspace_sync import get_workspace_sync_service
from pathlib import Path

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/sandboxes", tags=["sandboxes"])

logger = logging.getLogger(__name__)

store = MindscapeStore()
sandbox_manager = SandboxManager(store)

_preview_servers: Dict[str, SandboxPreviewServer] = {}


class CreateSandboxRequest(BaseModel):
    """Request model for creating a sandbox"""
    sandbox_type: str = Field(..., description="Type of sandbox (threejs_hero, writing_project, project_repo, web_page)")
    context: Optional[Dict[str, Any]] = Field(None, description="Optional context dictionary")


class CreateVersionRequest(BaseModel):
    """Request model for creating a version"""
    version: str = Field(..., description="Version identifier (e.g., v1, v2)")
    source_version: Optional[str] = Field(None, description="Optional source version to copy from")


@router.get("", response_model=List[Dict[str, Any]])
async def list_sandboxes(
    workspace_id: str = PathParam(..., description="Workspace identifier"),
    sandbox_type: Optional[str] = Query(None, description="Filter by sandbox type")
):
    """
    List all sandboxes in workspace

    Returns list of sandbox metadata dictionaries.
    """
    try:
        sandboxes = await sandbox_manager.list_sandboxes(
            workspace_id=workspace_id,
            sandbox_type=sandbox_type
        )
        return sandboxes
    except Exception as e:
        logger.error(f"Failed to list sandboxes: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("", status_code=201)
async def create_sandbox(
    workspace_id: str = PathParam(..., description="Workspace identifier"),
    request: CreateSandboxRequest = Body(...)
):
    """
    Create a new sandbox

    Returns sandbox identifier.
    """
    try:
        sandbox_id = await sandbox_manager.create_sandbox(
            sandbox_type=request.sandbox_type,
            workspace_id=workspace_id,
            context=request.context
        )
        return {"sandbox_id": sandbox_id}
    except ValueError as e:
        logger.error(f"Invalid sandbox type: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create sandbox: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{sandbox_id}", response_model=Dict[str, Any])
async def get_sandbox(
    workspace_id: str = PathParam(..., description="Workspace identifier"),
    sandbox_id: str = PathParam(..., description="Sandbox identifier")
):
    """
    Get sandbox details

    Returns sandbox metadata dictionary.
    """
    try:
        sandbox = await sandbox_manager.get_sandbox(sandbox_id, workspace_id)
        if not sandbox:
            raise HTTPException(status_code=404, detail="Sandbox not found")
        return sandbox.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get sandbox: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{sandbox_id}", status_code=204)
async def delete_sandbox(
    workspace_id: str = PathParam(..., description="Workspace identifier"),
    sandbox_id: str = PathParam(..., description="Sandbox identifier")
):
    """
    Delete sandbox

    Returns 204 No Content on success.
    """
    try:
        success = await sandbox_manager.delete_sandbox(sandbox_id, workspace_id)
        if not success:
            raise HTTPException(status_code=404, detail="Sandbox not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete sandbox: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{sandbox_id}/files", response_model=List[Dict[str, Any]])
async def list_files(
    workspace_id: str = PathParam(..., description="Workspace identifier"),
    sandbox_id: str = PathParam(..., description="Sandbox identifier"),
    directory: str = Query("", description="Directory path (empty for root)"),
    version: Optional[str] = Query(None, description="Version identifier"),
    recursive: bool = Query(True, description="List files recursively")
):
    """
    List files in sandbox

    Returns list of file metadata dictionaries.
    """
    try:
        sandbox = await sandbox_manager.get_sandbox(sandbox_id, workspace_id)
        if not sandbox:
            raise HTTPException(status_code=404, detail="Sandbox not found")

        files = await sandbox.list_files(directory, version, recursive)
        return files
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list files: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{sandbox_id}/files/{file_path:path}", response_model=Dict[str, Any])
async def get_file_content(
    workspace_id: str = PathParam(..., description="Workspace identifier"),
    sandbox_id: str = PathParam(..., description="Sandbox identifier"),
    file_path: str = PathParam(..., description="Relative file path"),
    version: Optional[str] = Query(None, description="Version identifier")
):
    """
    Get file content

    Returns file content and metadata.
    """
    try:
        sandbox = await sandbox_manager.get_sandbox(sandbox_id, workspace_id)
        if not sandbox:
            raise HTTPException(status_code=404, detail="Sandbox not found")

        content = await sandbox.read_file(file_path, version)
        file_exists = await sandbox.file_exists(file_path, version)

        if not file_exists:
            raise HTTPException(status_code=404, detail="File not found")

        files = await sandbox.list_files(version=version)
        file_info = next((f for f in files if f["path"] == file_path), None)

        return {
            "content": content,
            "path": file_path,
            "size": file_info["size"] if file_info else len(content.encode("utf-8")),
            "modified": file_info["modified"] if file_info else None,
        }
    except HTTPException:
        raise
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found")
    except Exception as e:
        logger.error(f"Failed to get file content: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{sandbox_id}/versions", status_code=201)
async def create_version(
    workspace_id: str = PathParam(..., description="Workspace identifier"),
    sandbox_id: str = PathParam(..., description="Sandbox identifier"),
    request: CreateVersionRequest = Body(...)
):
    """
    Create a new version snapshot

    Returns version identifier.
    """
    try:
        sandbox = await sandbox_manager.get_sandbox(sandbox_id, workspace_id)
        if not sandbox:
            raise HTTPException(status_code=404, detail="Sandbox not found")

        success = await sandbox.create_version(request.version, request.source_version)
        if not success:
            raise HTTPException(status_code=400, detail="Failed to create version")

        return {"version": request.version}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create version: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{sandbox_id}/versions", response_model=List[str])
async def list_versions(
    workspace_id: str = PathParam(..., description="Workspace identifier"),
    sandbox_id: str = PathParam(..., description="Sandbox identifier")
):
    """
    List all versions

    Returns list of version identifiers.
    """
    try:
        sandbox = await sandbox_manager.get_sandbox(sandbox_id, workspace_id)
        if not sandbox:
            raise HTTPException(status_code=404, detail="Sandbox not found")

        versions = await sandbox.list_versions()
        return versions
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list versions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{sandbox_id}/versions/{version}", response_model=Dict[str, Any])
async def get_version_metadata(
    workspace_id: str = PathParam(..., description="Workspace identifier"),
    sandbox_id: str = PathParam(..., description="Sandbox identifier"),
    version: str = PathParam(..., description="Version identifier")
):
    """
    Get version metadata

    Returns version metadata dictionary.
    """
    try:
        sandbox = await sandbox_manager.get_sandbox(sandbox_id, workspace_id)
        if not sandbox:
            raise HTTPException(status_code=404, detail="Sandbox not found")

        metadata = await sandbox.get_version_metadata(version)
        if not metadata:
            raise HTTPException(status_code=404, detail="Version not found")

        return metadata
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get version metadata: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/by-project/{project_id}", response_model=Optional[Dict[str, Any]])
async def get_sandbox_by_project(
    workspace_id: str = PathParam(..., description="Workspace identifier"),
    project_id: str = PathParam(..., description="Project identifier")
):
    """
    Get sandbox for a project

    Returns sandbox metadata if found, None otherwise.
    """
    try:
        sandboxes = await sandbox_manager.list_sandboxes(
            workspace_id=workspace_id
        )

        project_sandbox = next(
            (s for s in sandboxes if s.get("metadata", {}).get("context", {}).get("project_id") == project_id),
            None
        )

        if project_sandbox:
            sandbox = await sandbox_manager.get_sandbox(
                project_sandbox["sandbox_id"],
                workspace_id
            )
            if sandbox:
                return sandbox.to_dict()

        return None
    except Exception as e:
        logger.error(f"Failed to get sandbox by project: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Preview Server API
# =============================================================================

class StartPreviewRequest(BaseModel):
    """Request model for starting preview server"""
    port: int = Field(3000, description="Port number for preview server")


class EnsurePreviewRequest(BaseModel):
    """Request model for ensuring preview is ready"""
    project_id: Optional[str] = Field(None, description="Optional project ID")
    port: int = Field(3000, description="Port number for preview server")


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

        # Step 1: Ensure sandbox exists and is synced
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

        # Step 2: Start preview server
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
        sandbox_path = Path(sandbox.base_path) / sandbox.current_version
        if not sandbox_path.exists():
            return {
                "success": False,
                "error": f"Sandbox path does not exist: {sandbox_path}",
                "sandbox_id": sandbox_id,
                "preview_url": None,
                "synced_files": result.get("synced_files", [])
            }

        preview_server = SandboxPreviewServer(sandbox_path, request.port)
        server_result = await preview_server.start()

        if server_result["success"]:
            _preview_servers[server_key] = preview_server
            logger.info(f"Started preview server for {workspace_id} on port {server_result['port']}")

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


def _get_preview_server_key(workspace_id: str, sandbox_id: str) -> str:
    """Generate unique key for preview server"""
    return f"{workspace_id}:{sandbox_id}"


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
                    "port": existing_server.actual_port or existing_server.port,
                    "url": existing_server.get_preview_url(),
                    "error": None,
                    "port_conflict": False,
                    "message": "Preview server already running"
                }

        # Get sandbox path
        sandbox_path = Path(sandbox.base_path) / sandbox.current_version
        if not sandbox_path.exists():
            return {
                "success": False,
                "port": None,
                "url": None,
                "error": f"Sandbox path does not exist: {sandbox_path}",
                "port_conflict": False
            }

        # Create and start preview server
        preview_server = SandboxPreviewServer(sandbox_path, request.port)
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


@router.get("/{sandbox_id}/sync/diff", response_model=Dict[str, Any])
async def get_sync_diff(
    workspace_id: str = PathParam(..., description="Workspace identifier"),
    sandbox_id: str = PathParam(..., description="Sandbox identifier")
):
    """
    Get diff between workspace and sandbox.
    
    Shows what files would change if syncing sandbox to workspace.
    Useful for user confirmation before save.
    
    Returns:
        - added: Files in sandbox but not workspace
        - modified: Files that differ
        - deleted: Files in workspace but not sandbox
        - unchanged: Files that are identical
    """
    try:
        sync_service = get_workspace_sync_service(store)
        diff = await sync_service.get_sync_diff(workspace_id, sandbox_id)
        return diff
    except Exception as e:
        logger.error(f"Failed to get sync diff: {e}")
        return {"error": str(e)}


class SyncToWorkspaceRequest(BaseModel):
    """Request for syncing sandbox to workspace"""
    create_backup: bool = Field(True, description="Backup existing files before overwriting")
    confirmed: bool = Field(False, description="User has confirmed the sync")


@router.post("/{sandbox_id}/sync/to-workspace", response_model=Dict[str, Any])
async def sync_sandbox_to_workspace(
    workspace_id: str = PathParam(..., description="Workspace identifier"),
    sandbox_id: str = PathParam(..., description="Sandbox identifier"),
    request: SyncToWorkspaceRequest = Body(...)
):
    """
    Save sandbox files to workspace (persist changes).
    
    This is the "save" operation. Syncs sandbox changes back to workspace.
    Creates backups of existing files by default.
    
    **Safety**: Requires `confirmed: true` to proceed.
    Call GET /sync/diff first to preview changes.
    
    Returns:
        - synced_files: Files saved to workspace
        - backed_up_files: Files that were backed up
        - status: success/error
    """
    try:
        if not request.confirmed:
            # Return diff instead of syncing
            sync_service = get_workspace_sync_service(store)
            diff = await sync_service.get_sync_diff(workspace_id, sandbox_id)
            return {
                "status": "confirmation_required",
                "message": "Please review changes and set confirmed=true",
                "diff": diff
            }
        
        sync_service = get_workspace_sync_service(store)
        result = await sync_service.sync_sandbox_to_workspace(
            workspace_id=workspace_id,
            sandbox_id=sandbox_id,
            create_backup=request.create_backup
        )
        return result
        
    except Exception as e:
        logger.error(f"Failed to sync to workspace: {e}")
        return {"status": "error", "error": str(e)}


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
            "port": preview_server.actual_port or preview_server.port if preview_server.is_running else None,
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

