"""
Core Export API Routes (Opensource)
Endpoints for backup and portable configuration export
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
import os

from backend.app.models.core_export import (
    BackupConfiguration,
    PortableConfiguration,
    ExportPreview,
    BackupRequest,
    PortableExportRequest,
    ExportResponse,
)
from backend.app.services.core_export_service import CoreExportService

router = APIRouter(tags=["export"])

# Initialize core export service
export_service = CoreExportService()


@router.get("/preview", response_model=ExportPreview)
async def preview_export(
    profile_id: str = Query(..., description="Profile ID to export")
):
    """
    Preview what will be exported

    Shows user what data will be included in the export (backup or portable).
    """
    try:
        preview = await export_service.preview_export(profile_id)
        return preview
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate preview: {str(e)}")


@router.post("/backup", response_model=ExportResponse)
async def create_backup(request: BackupRequest):
    """
    Create complete backup of configuration

    **Use case:** Backup entire configuration for restore.

    **Includes:**
    - Complete mindscape profile (with email)
    - All intent cards
    - All AI role configurations
    - All playbooks
    - Tool connections (with encrypted credentials if requested)

    **Purpose:** Local backup and restore
    """
    try:
        # Generate backup
        backup = await export_service.create_backup(request)

        # Save to file
        filepath = export_service.save_to_file(backup)

        # Get file size
        file_size = os.path.getsize(filepath)

        # Build response
        response = ExportResponse(
            success=True,
            export_id=f"backup_{backup.backup_timestamp.strftime('%Y%m%d_%H%M%S')}",
            export_type="backup",
            download_url=f"/api/v1/export/download/{os.path.basename(filepath)}",
            exported_at=backup.backup_timestamp,
            file_size_bytes=file_size,
        )

        return response

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create backup: {str(e)}")


@router.post("/portable", response_model=ExportResponse)
async def create_portable_config(request: PortableExportRequest):
    """
    Create portable configuration (without sensitive data)

    **Use case:** Share configuration with other local users.

    **Includes:**
    - Mindscape profile template (without email)
    - AI role configurations
    - Playbooks
    - Tool connection templates (without credentials)

    **Purpose:** Configuration sharing and migration
    """
    try:
        # Generate portable configuration
        portable = await export_service.create_portable_config(request)

        # Save to file
        filepath = export_service.save_to_file(portable)

        # Get file size
        file_size = os.path.getsize(filepath)

        # Build response
        response = ExportResponse(
            success=True,
            export_id=f"portable_{portable.config_name}_{portable.created_at.strftime('%Y%m%d_%H%M%S')}",
            export_type="portable",
            download_url=f"/api/v1/export/download/{os.path.basename(filepath)}",
            exported_at=portable.created_at,
            file_size_bytes=file_size,
        )

        return response

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create portable config: {str(e)}")


@router.get("/download/{filename}")
async def download_export_file(filename: str):
    """
    Download exported file

    Returns the JSON file for download.
    """
    from fastapi.responses import FileResponse

    filepath = f"exports/{filename}"

    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Export file not found")

    return FileResponse(
        path=filepath,
        media_type="application/json",
        filename=filename,
    )


@router.get("/list")
async def list_exports():
    """
    List all available export files

    Returns a list of previously exported backups and configurations.
    """
    exports_dir = "exports"

    if not os.path.exists(exports_dir):
        return {"exports": []}

    files = []
    for filename in os.listdir(exports_dir):
        if filename.endswith(".json"):
            filepath = os.path.join(exports_dir, filename)
            file_size = os.path.getsize(filepath)
            file_mtime = os.path.getmtime(filepath)

            # Determine export type from filename
            if filename.startswith("backup_"):
                export_type = "backup"
            elif filename.startswith("portable_"):
                export_type = "portable"
            else:
                export_type = "unknown"

            files.append({
                "filename": filename,
                "export_type": export_type,
                "size_bytes": file_size,
                "created_at": file_mtime,
                "download_url": f"/api/v1/export/download/{filename}",
            })

    # Sort by creation time (newest first)
    files.sort(key=lambda x: x["created_at"], reverse=True)

    return {"exports": files}


@router.delete("/delete/{filename}")
async def delete_export_file(filename: str):
    """Delete an exported file"""
    filepath = f"exports/{filename}"

    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Export file not found")

    try:
        os.remove(filepath)
        return {"success": True, "message": f"Deleted {filename}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete file: {str(e)}")
