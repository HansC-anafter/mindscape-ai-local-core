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

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/sandboxes", tags=["sandboxes"])

logger = logging.getLogger(__name__)

store = MindscapeStore()
sandbox_manager = SandboxManager(store)


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

