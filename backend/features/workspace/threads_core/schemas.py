"""Request schemas for workspace thread routes."""

from typing import Literal, Optional

from pydantic import BaseModel, Field


class CreateThreadRequest(BaseModel):
    """Request to create a new conversation thread."""

    title: Optional[str] = Field(
        None, description="Thread title (auto-generated if not provided)"
    )
    project_id: Optional[str] = Field(
        None, description="Optional: associate with a project"
    )
    pinned_scope: Optional[str] = Field(
        None, description="Optional: pin a scope for this thread"
    )


class UpdateThreadRequest(BaseModel):
    """Request to update a conversation thread."""

    title: Optional[str] = Field(None, description="Thread title")
    project_id: Optional[str] = Field(None, description="Project ID")
    pinned_scope: Optional[str] = Field(None, description="Pinned scope")


class AddReferenceRequest(BaseModel):
    """Request to add a reference to a thread."""

    source_type: Literal[
        "obsidian", "notion", "wordpress", "local_file", "url", "google_drive"
    ] = Field(..., description="Source connector type")
    uri: str = Field(..., description="Real URI (clickable)")
    title: str = Field(..., description="Reference title")
    snippet: Optional[str] = Field(None, description="Short summary snippet")
    reason: Optional[str] = Field(None, description="Reason for pinning")


class UpdateReferenceRequest(BaseModel):
    """Request to update a thread reference."""

    title: Optional[str] = Field(None, description="Reference title")
    snippet: Optional[str] = Field(None, description="Short summary snippet")
    reason: Optional[str] = Field(None, description="Reason for pinning")
