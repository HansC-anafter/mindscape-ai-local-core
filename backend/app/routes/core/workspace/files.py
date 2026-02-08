import logging
import subprocess
import platform
import base64
from pathlib import Path
from typing import Optional

from fastapi import (
    APIRouter,
    HTTPException,
    Path as PathParam,
    Body,
    File,
    UploadFile,
    Form,
)

from ....services.mindscape_store import MindscapeStore
from ....services.file_analysis_service import FileAnalysisService
from ....services.stores.timeline_items_store import TimelineItemsStore
from ....services.stores.tasks_store import TasksStore

router = APIRouter()
logger = logging.getLogger(__name__)
store = MindscapeStore()


@router.post("/{workspace_id}/open-folder")
async def open_folder(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    path: str = Body(..., description="Path to open"),
):
    """
    Open folder in system file manager

    Opens the specified path in the system's default file manager.
    Supports macOS, Windows, and Linux.
    """
    try:
        # Verify workspace exists
        workspace = await store.get_workspace(workspace_id)
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")

        # Validate path exists
        path_obj = Path(path).expanduser().resolve()
        if not path_obj.exists():
            raise HTTPException(status_code=400, detail=f"Path does not exist: {path}")

        # Open folder based on platform
        system = platform.system()
        try:
            if system == "Darwin":  # macOS
                subprocess.run(["open", str(path_obj)], check=True)
            elif system == "Windows":
                subprocess.run(["explorer", str(path_obj)], check=True)
            else:  # Linux and others
                subprocess.run(["xdg-open", str(path_obj)], check=True)

            return {"success": True, "message": f"Opened folder: {path}"}
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to open folder: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to open folder. Please open manually: {path}",
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error opening folder: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to open folder: {str(e)}")


@router.post("/{workspace_id}/files/upload")
async def upload_file(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    file: UploadFile = File(...),
    file_name: Optional[str] = Form(None),
    file_type: Optional[str] = Form(None),
    file_size: Optional[int] = Form(None),
):
    """
    Upload file to workspace

    Supports multipart/form-data:
    - file: File to upload
    - file_name: File name (optional, defaults to uploaded file name)
    - file_type: File MIME type (optional)
    - file_size: File size in bytes (optional)
    """
    try:
        workspace = await store.get_workspace(workspace_id)
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")

        timeline_items_store = TimelineItemsStore(db_path=store.db_path)
        tasks_store = TasksStore(db_path=store.db_path)
        file_service = FileAnalysisService(store, timeline_items_store, tasks_store)

        # Read file content
        file_content = await file.read()

        # Convert to base64 data URL
        file_base64 = base64.b64encode(file_content).decode("utf-8")
        file_data_url = f"data:{file.content_type or 'application/octet-stream'};base64,{file_base64}"

        # Use provided file_name or fallback to uploaded file name
        actual_file_name = file_name or file.filename or "uploaded_file"
        actual_file_type = file_type or file.content_type
        actual_file_size = file_size or len(file_content)

        result = await file_service.upload_file(
            workspace_id=workspace_id,
            file_data=file_data_url,
            file_name=actual_file_name,
            file_type=actual_file_type,
            file_size=actual_file_size,
        )

        return {
            "file_id": result["file_id"],
            "file_path": result["file_path"],
            "file_name": result["file_name"],
            "file_type": result.get("file_type"),
            "file_size": result.get("file_size"),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to upload file: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{workspace_id}/files/analyze")
async def analyze_file(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    request: dict = Body(...),
):
    """
    Analyze uploaded file

    Request body:
    - file_id: File ID from upload (preferred)
    - file_data: Base64 encoded file data (fallback)
    - file_name: File name
    - file_type: File MIME type (optional)
    - file_size: File size in bytes (optional)
    - file_path: File path on server (optional)
    """
    try:
        workspace = await store.get_workspace(workspace_id)
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")

        timeline_items_store = TimelineItemsStore(db_path=store.db_path)
        tasks_store = TasksStore(db_path=store.db_path)
        file_service = FileAnalysisService(store, timeline_items_store, tasks_store)

        file_id = request.get("file_id")
        file_data = request.get("file_data")
        file_name = request.get("file_name")
        file_type = request.get("file_type")
        file_size = request.get("file_size")
        file_path = request.get("file_path")

        if not file_id and not file_data:
            raise HTTPException(
                status_code=400, detail="Either file_id or file_data is required"
            )
        if not file_name:
            raise HTTPException(status_code=400, detail="file_name is required")

        profile_id = workspace.owner_user_id
        result = await file_service.analyze_file(
            workspace_id=workspace_id,
            profile_id=profile_id,
            file_id=file_id,
            file_data=file_data,
            file_name=file_name,
            file_type=file_type,
            file_size=file_size,
            file_path=file_path,
        )

        return {
            "file_id": result.get("file_id"),
            "file_path": result.get("file_path"),
            "event_id": result.get("event_id"),
            "saved_file_path": result.get("file_path"),
            "collaboration_results": result.get("collaboration_results", {}),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to analyze file: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
