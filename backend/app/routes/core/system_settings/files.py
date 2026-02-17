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


@router.get("/browser-profile-status")
async def get_browser_profile_status(
    profile_name: str = Query("default", description="Profile name to check"),
    profile_path: Optional[str] = Query(
        None, description="Optional profile path to check (absolute or under /app)"
    ),
):
    """
    Check the status of a browser profile for IG automation.

    Reads session state from storage_state.json (the file Playwright actually
    uses at runtime). Validates that a sessionid cookie is present and has
    not expired.
    """
    import json
    import time

    if profile_path:
        if not profile_path.startswith("/"):
            profile_path = f"/app/{profile_path}"
        profile_dir = Path(profile_path)
        try:
            profile_dir.resolve().relative_to(Path("/app").resolve())
        except ValueError:
            return {
                "exists": False,
                "ready": False,
                "logged_in": False,
                "profile_path": str(profile_dir),
                "path_source": "profile_path",
                "message": "Profile path must be under /app",
                "ig_cookies": [],
            }
        path_source = "profile_path"
    else:
        profile_dir = Path(f"/app/data/ig-browser-profiles/{profile_name}")
        path_source = "profile_name"

    if not profile_dir.exists():
        return {
            "exists": False,
            "ready": False,
            "logged_in": False,
            "profile_path": str(profile_dir),
            "path_source": path_source,
            "message": "Profile directory does not exist",
            "ig_cookies": [],
        }

    # Read storage_state.json — the sole source of truth for Playwright sessions
    storage_state_path = profile_dir / "storage_state.json"

    if not storage_state_path.exists():
        return {
            "exists": True,
            "ready": False,
            "logged_in": False,
            "profile_path": str(profile_dir),
            "path_source": path_source,
            "storage_state_path": str(storage_state_path),
            "message": "No storage_state.json found (not logged in)",
            "ig_cookies": [],
        }

    try:
        with open(storage_state_path, "r", encoding="utf-8") as f:
            storage_state = json.load(f)
    except Exception as e:
        return {
            "exists": True,
            "ready": False,
            "logged_in": False,
            "profile_path": str(profile_dir),
            "path_source": path_source,
            "storage_state_path": str(storage_state_path),
            "message": f"Error reading storage_state.json: {e}",
            "ig_cookies": [],
        }

    all_cookies = storage_state.get("cookies", [])
    ig_cookies = [
        {"name": c.get("name"), "domain": c.get("domain")}
        for c in all_cookies
        if "instagram" in c.get("domain", "")
    ]

    sessionid_cookie = None
    for c in all_cookies:
        if c.get("name") == "sessionid" and "instagram" in c.get("domain", ""):
            sessionid_cookie = c
            break

    has_sessionid = sessionid_cookie is not None
    session_expired = False

    if has_sessionid:
        expires = sessionid_cookie.get("expires", 0)
        if expires and expires > 0 and expires < time.time():
            session_expired = True

    logged_in = has_sessionid and not session_expired

    if logged_in:
        message = "Logged in and ready"
    elif session_expired:
        message = "Session expired — sessionid cookie past expiry. Please re-login."
    else:
        message = (
            f"Profile exists with {len(ig_cookies)} IG cookies "
            f"but NO sessionid (not logged in)"
        )

    return {
        "exists": True,
        "ready": logged_in,
        "logged_in": logged_in,
        "profile_path": str(profile_dir),
        "path_source": path_source,
        "has_sessionid": has_sessionid,
        "sessionid_cookie": sessionid_cookie,
        "session_expired": session_expired,
        "storage_state_path": str(storage_state_path),
        "session_source": "storage_state" if has_sessionid else "none",
        "ig_cookie_count": len(ig_cookies),
        "ig_cookies": ig_cookies,
        "message": message,
    }
