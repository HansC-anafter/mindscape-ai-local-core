"""
Artifact Registry model for Project-based artifact tracking.

The live PostgreSQL schema currently persists only the minimal project-scoped
registry identity: artifact_id, status, and creator metadata. Legacy fields
like path/type/dependencies are retained here as optional compatibility fields
because some call sites still pass them during registration, but they are not
written to the live table.
"""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field


class ArtifactRegistry(BaseModel):
    """
    Artifact Registry entry - tracks artifacts within a Project

    Each entry represents an artifact that was created during a Project's
    flow execution, along with its dependencies and metadata.
    """

    id: str = Field(..., description="Unique registry entry identifier")
    project_id: str = Field(..., description="Project ID this artifact belongs to")
    artifact_id: str = Field(..., description="Artifact identifier (reference to Artifact.id or path)")
    status: Optional[str] = Field(
        default=None,
        description="Project-local artifact lifecycle status",
    )
    path: Optional[str] = Field(
        default=None,
        description="Legacy artifact file path within project sandbox (not persisted in live PG schema)",
    )
    type: Optional[str] = Field(
        default=None,
        description="Legacy artifact type metadata (not persisted in live PG schema)",
    )
    created_by: str = Field(..., description="Playbook node ID that created this artifact")
    dependencies: List[str] = Field(
        default_factory=list,
        description="Legacy dependency list (not persisted in live PG schema)",
    )
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Last update timestamp")

    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})
