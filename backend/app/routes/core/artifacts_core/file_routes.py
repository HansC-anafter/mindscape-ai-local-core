
import asyncio
import os
from pathlib import Path as PathLib

from fastapi import APIRouter, HTTPException, Path
from fastapi.responses import FileResponse, RedirectResponse, Response

from .state import logger, store

router = APIRouter()

@router.get("/workspaces/{workspace_id}/artifacts/{artifact_id}/file")
async def get_artifact_file(
    workspace_id: str = Path(..., description="Workspace ID"),
    artifact_id: str = Path(..., description="Artifact ID"),
):
    """
    Get artifact file content

    Returns the file content for an artifact if it has a file_path.
    Supports both local file paths and external URLs.
    """
    try:
        artifact = await asyncio.to_thread(store.artifacts.get_artifact, artifact_id)
        if not artifact:
            raise HTTPException(
                status_code=404, detail=f"Artifact {artifact_id} not found"
            )

        # Verify artifact belongs to workspace
        if artifact.workspace_id != workspace_id:
            raise HTTPException(
                status_code=403, detail="Artifact does not belong to this workspace"
            )

        # Get file path from metadata or storage_ref
        file_path = None
        if artifact.metadata and artifact.metadata.get("file_path"):
            file_path = artifact.metadata.get("file_path")
        elif artifact.metadata and artifact.metadata.get("actual_file_path"):
            file_path = artifact.metadata.get("actual_file_path")
        elif artifact.storage_ref:
            # Check if storage_ref is a URL
            if artifact.storage_ref.startswith(
                "http://"
            ) or artifact.storage_ref.startswith("https://"):
                # Redirect to external URL
                return RedirectResponse(url=artifact.storage_ref)
            else:
                file_path = artifact.storage_ref

        if not file_path:
            raise HTTPException(
                status_code=404, detail="Artifact does not have a file path"
            )

        # Check if file exists
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail=f"File not found: {file_path}")

        # Determine media type based on file extension
        file_ext = PathLib(file_path).suffix.lower()
        media_type_map = {
            ".json": "application/json",
            ".txt": "text/plain",
            ".md": "text/markdown",
            ".html": "text/html",
            ".css": "text/css",
            ".js": "application/javascript",
            ".tsx": "application/javascript",
            ".ts": "application/javascript",
            ".pdf": "application/pdf",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".doc": "application/msword",
            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".xls": "application/vnd.ms-excel",
            ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            ".ppt": "application/vnd.ms-powerpoint",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".svg": "image/svg+xml",
            ".mp4": "video/mp4",
            ".mp3": "audio/mpeg",
        }
        media_type = media_type_map.get(file_ext, "application/octet-stream")

        # For text-based files (JSON, text, markdown), return content directly
        # This allows frontend to display inline instead of forcing download
        text_based_types = {
            ".json",
            ".txt",
            ".md",
            ".html",
            ".css",
            ".js",
            ".tsx",
            ".ts",
        }
        if file_ext in text_based_types:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                return Response(
                    content=content,
                    media_type=media_type,
                    headers={
                        "Content-Disposition": f'inline; filename="{PathLib(file_path).name}"'
                    },
                )
            except Exception as e:
                logger.warning(
                    f"Failed to read file as text, falling back to FileResponse: {e}"
                )

        # For binary files (images, videos, documents), return as file download
        return FileResponse(
            path=file_path, media_type=media_type, filename=PathLib(file_path).name
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get artifact file {artifact_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to get artifact file: {str(e)}"
        )
