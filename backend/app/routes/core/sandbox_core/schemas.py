"""Request schemas for sandbox routes."""

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

class CreateSandboxRequest(BaseModel):
    """Request model for creating a sandbox"""
    sandbox_type: str = Field(..., description="Type of sandbox (threejs_hero, writing_project, project_repo, web_page)")
    context: Optional[Dict[str, Any]] = Field(None, description="Optional context dictionary")

class CreateVersionRequest(BaseModel):
    """Request model for creating a version"""
    version: str = Field(..., description="Version identifier (e.g., v1, v2)")
    source_version: Optional[str] = Field(None, description="Optional source version to copy from")

class StartPreviewRequest(BaseModel):
    """Request model for starting preview server"""
    port: int = Field(3000, description="Port number for preview server")

class EnsurePreviewRequest(BaseModel):
    """Request model for ensuring preview is ready"""
    project_id: Optional[str] = Field(None, description="Optional project ID")
    port: int = Field(3000, description="Port number for preview server")

class SyncToWorkspaceRequest(BaseModel):
    """Request for syncing sandbox to workspace"""
    create_backup: bool = Field(True, description="Backup existing files before overwriting")
    confirmed: bool = Field(False, description="User has confirmed the sync")
