"""
Local Content API Routes

Manages Device Node file access authorization and Apple Notes folder selection.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.app.services.device_node_filesystem import (
    DeviceNodeFilesystemService,
    DeviceNodeError,
    get_device_node_filesystem,
)
from backend.app.services.device_node_notes import (
    DeviceNodeNotesService,
    NotesServiceError,
    get_device_node_notes,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/local-content", tags=["local-content"])

# ---------------------------------------------------------------------------
# Config persistence (simple JSON file)
# ---------------------------------------------------------------------------

CONFIG_DIR = os.getenv(
    "LOCAL_CONTENT_CONFIG_DIR",
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "data"),
)
CONFIG_FILE = os.path.join(CONFIG_DIR, "local_content_config.json")


def _load_config() -> Dict[str, Any]:
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to load local content config: {e}")
    return {"directories": _default_directories(), "notes_folders": []}


def _save_config(config: Dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Failed to save local content config: {e}")


def _default_directories() -> List[Dict[str, Any]]:
    return [
        {"path": "~/Documents", "enabled": False},
        {"path": "~/Projects", "enabled": False},
        {"path": "~/Desktop", "enabled": False},
    ]


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class DirectoryEntry(BaseModel):
    path: str
    enabled: bool = False


class NotesFolder(BaseModel):
    name: str
    enabled: bool = False


class StatusResponse(BaseModel):
    connected: bool
    notesAvailable: bool


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/status", response_model=StatusResponse)
async def get_status():
    """Check Device Node connection and Notes availability."""
    fs_service = get_device_node_filesystem()
    notes_service = get_device_node_notes()

    connected = await fs_service.is_available()
    notes_available = False

    if connected:
        try:
            notes_available = await notes_service.is_available()
        except Exception:
            pass

    return StatusResponse(connected=connected, notesAvailable=notes_available)


@router.get("/directories", response_model=List[DirectoryEntry])
async def get_directories():
    """Get authorized directory list."""
    config = _load_config()
    return [
        DirectoryEntry(**d) for d in config.get("directories", _default_directories())
    ]


from starlette.concurrency import run_in_threadpool


def _sync_directories_to_registry(enabled_dirs: List[str]):
    try:
        from backend.app.services.tool_registry import ToolRegistryService
        from backend.app.models.tool_registry import ToolConnectionModel
        from datetime import datetime

        tool_registry = ToolRegistryService()

        connections = tool_registry.get_connections_by_tool_type(
            profile_id="default-user", tool_type="local_filesystem"
        )

        if connections and connections[0].is_active:
            # Update existing primary connection
            conn = connections[0]
            if conn.config is None:
                conn.config = {}
            conn.config["allowed_directories"] = enabled_dirs
            tool_registry.update_connection(conn)
            logger.info(
                f"Synced {len(enabled_dirs)} local directories to ToolConnection {conn.id}"
            )
        else:
            # Create a new connection if none exists
            conn_id = f"local_filesystem-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            conn = ToolConnectionModel(
                id=conn_id,
                profile_id="default-user",
                name="System Local Access",
                tool_type="local_filesystem",
                connection_type="local",
                config={"allowed_directories": enabled_dirs},
            )
            tool_registry.create_connection(conn)
            logger.info(
                f"Created new ToolConnection {conn.id} with {len(enabled_dirs)} synced directories"
            )

    except Exception as e:
        logger.error(
            f"Failed to sync local content directories to ToolConnections: {e}"
        )


@router.put("/directories", response_model=List[DirectoryEntry])
async def update_directories(directories: List[DirectoryEntry]):
    """
    Update authorized directory list and sync to ToolRegistry.

    This ensures directories enabled in Local Content are available
    to Workspace Settings via StoragePathValidator.
    """
    config = _load_config()
    config["directories"] = [d.model_dump() for d in directories]
    _save_config(config)

    # Sync enabled directories to ToolRegistry in a threadpool to avoid async blocking
    enabled_dirs = [d.path for d in directories if d.enabled]
    await run_in_threadpool(_sync_directories_to_registry, enabled_dirs)

    return directories


@router.get("/notes/folders", response_model=List[NotesFolder])
async def get_notes_folders():
    """
    Get Apple Notes folders with authorization status.

    Fetches live folder list from Device Node, merges with saved config.
    """
    config = _load_config()
    saved_folders = {f["name"]: f["enabled"] for f in config.get("notes_folders", [])}

    notes_service = get_device_node_notes()

    try:
        live_folders = await notes_service.list_folders()
    except NotesServiceError as e:
        logger.warning(f"Failed to fetch Notes folders: {e}")
        # Return saved config as fallback
        return [NotesFolder(**f) for f in config.get("notes_folders", [])]

    # Merge: live folders with saved enabled state
    result = []
    for folder_name in live_folders:
        result.append(
            NotesFolder(
                name=folder_name,
                enabled=saved_folders.get(folder_name, False),
            )
        )

    return result


@router.put("/notes/folders", response_model=List[NotesFolder])
async def update_notes_folders(folders: List[NotesFolder]):
    """Update Notes folder authorization."""
    config = _load_config()
    config["notes_folders"] = [f.model_dump() for f in folders]
    _save_config(config)
    return folders


# ---------------------------------------------------------------------------
# File Type Governance endpoints
# ---------------------------------------------------------------------------


class FileTypeConfig(BaseModel):
    allowed_extensions: List[str]
    blocked_extensions: List[str]
    source: Optional[str] = None


class FileTypeUpdateRequest(BaseModel):
    allowed_extensions: Optional[List[str]] = None
    blocked_extensions: Optional[List[str]] = None


@router.get("/file-types", response_model=FileTypeConfig)
async def get_file_types(workspace_id: Optional[str] = None):
    """Get effective file type governance config (global or workspace-merged)."""
    from backend.app.services.file_type_governance import get_file_type_governance

    gov = get_file_type_governance()
    config = gov.get_effective_config(workspace_id=workspace_id)
    return FileTypeConfig(**config)


@router.put("/file-types", response_model=FileTypeConfig)
async def update_global_file_types(request: FileTypeUpdateRequest):
    """Update global file type governance config."""
    from backend.app.services.file_type_governance import get_file_type_governance

    gov = get_file_type_governance()
    gov.update_global_config(
        allowed_extensions=request.allowed_extensions,
        blocked_extensions=request.blocked_extensions,
    )
    config = gov.get_effective_config()
    return FileTypeConfig(**config)


@router.put("/file-types/{workspace_id}", response_model=FileTypeConfig)
async def update_workspace_file_types(
    workspace_id: str, request: FileTypeUpdateRequest
):
    """Update workspace-level file type override (can only tighten)."""
    from backend.app.services.file_type_governance import get_file_type_governance

    gov = get_file_type_governance()
    gov.update_workspace_config(
        workspace_id=workspace_id,
        allowed_extensions=request.allowed_extensions,
        blocked_extensions=request.blocked_extensions,
    )
    config = gov.get_effective_config(workspace_id=workspace_id)
    return FileTypeConfig(**config)
