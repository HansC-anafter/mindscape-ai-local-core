"""
File System Utility Routes

Provides simple file system inspection endpoints for frontend components.
"""

import os
from typing import Optional, List, Dict, Any
from pathlib import Path
from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

router = APIRouter(prefix="/files", tags=["files"])


@router.get("/exists")
async def check_file_exists(
    path: str = Query(
        ..., description="File path to check (relative to /app or absolute)"
    )
):
    """
    Check if a file or directory exists.

    Args:
        path: File path to check. Can be:
              - Absolute path (e.g., /app/data/ig-browser-profiles/default)
              - Relative path from /app (e.g., data/ig-browser-profiles/default)

    Returns:
        JSON with exists (bool), is_file (bool), is_dir (bool)
    """
    # Normalize path
    if not path.startswith("/"):
        path = f"/app/{path}"

    # Security: only allow checking paths under /app
    resolved = Path(path).resolve()
    app_root = Path("/app").resolve()

    try:
        resolved.relative_to(app_root)
    except ValueError:
        return {
            "exists": False,
            "is_file": False,
            "is_dir": False,
            "error": "Path must be under /app directory",
        }

    exists = resolved.exists()
    is_file = resolved.is_file() if exists else False
    is_dir = resolved.is_dir() if exists else False

    return {
        "exists": exists,
        "is_file": is_file,
        "is_dir": is_dir,
        "path": str(resolved),
    }


class FileItem(BaseModel):
    name: str
    path: str
    is_dir: bool
    size: Optional[int] = None
    modified_at: Optional[float] = None


@router.get("/ls", response_model=Dict[str, Any])
async def list_directory(
    path: str = Query("/", description="Directory path to list"),
    show_hidden: bool = Query(False, description="Whether to show hidden files"),
):
    """
    List contents of a directory.

    Security: Paths must be absolute and resolve to something under /app
    (which covers /app/backend, /app/data, /app/scripts, and any host mounts like /host/documents).
    """
    # Normalize path
    if not path.startswith("/"):
        path = f"/app/{path}"

    resolved = Path(path).resolve()
    app_root = Path("/app").resolve()

    try:
        resolved.relative_to(app_root)
    except ValueError:
        return {
            "success": False,
            "error": "Access denied. Path must be under /app directory.",
            "items": [],
        }

    if not resolved.exists():
        return {"success": False, "error": "Directory does not exist.", "items": []}

    if not resolved.is_dir():
        return {"success": False, "error": "Path is not a directory.", "items": []}

    try:
        items = []
        for entry in os.scandir(resolved):
            if not show_hidden and entry.name.startswith("."):
                continue

            is_dir = entry.is_dir()
            stat = entry.stat()

            items.append(
                FileItem(
                    name=entry.name,
                    path=str(Path(entry.path).resolve()),
                    is_dir=is_dir,
                    size=None if is_dir else stat.st_size,
                    modified_at=stat.st_mtime,
                )
            )

        # Sort: directories first, then alphabetically
        items.sort(key=lambda x: (not x.is_dir, x.name.lower()))

        return {
            "success": True,
            "current_path": str(resolved),
            "parent_path": str(resolved.parent) if resolved != app_root else None,
            "items": items,
        }
    except Exception as e:
        return {"success": False, "error": str(e), "items": []}
