"""
Artifact Registry model for Project-based artifact tracking

The Artifact Registry tracks artifacts within a Project context, maintaining
dependencies and relationships between artifacts created during flow execution.

This is separate from the global Artifact model which is workspace-scoped.
ArtifactRegistry entries are project-scoped and used for flow orchestration.
"""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class ArtifactRegistry(BaseModel):
    """
    Artifact Registry entry - tracks artifacts within a Project

    Each entry represents an artifact that was created during a Project's
    flow execution, along with its dependencies and metadata.
    """

    id: str = Field(..., description="Unique registry entry identifier")
    project_id: str = Field(..., description="Project ID this artifact belongs to")
    artifact_id: str = Field(..., description="Artifact identifier (reference to Artifact.id or path)")
    path: str = Field(..., description="Artifact file path within project sandbox")
    type: str = Field(..., description="Artifact type (markdown, json, html, etc.)")
    created_by: str = Field(..., description="Playbook node ID that created this artifact")
    dependencies: List[str] = Field(default_factory=list, description="List of artifact_ids this depends on")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Last update timestamp")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

