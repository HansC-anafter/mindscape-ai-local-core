"""Sandbox file routes."""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Path as PathParam, Query

from .state import sandbox_manager

logger = logging.getLogger(__name__)
router = APIRouter()

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
