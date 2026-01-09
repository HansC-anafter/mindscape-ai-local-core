"""
Thread Bundle models for API responses

Thread Bundle represents the complete aggregation of deliverables, references,
runs, and sources for a conversation thread.
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Literal
from datetime import datetime


class ThreadOverview(BaseModel):
    """Overview section of Thread Bundle"""
    title: str = Field(..., description="Thread title")
    brief: Optional[str] = Field(None, description="Brief description")
    status: Literal['in_progress', 'delivered', 'pending_data'] = Field(
        ..., description="Thread status"
    )
    summary: Optional[str] = Field(None, description="Auto-generated or user-edited summary")
    project_id: Optional[str] = Field(None, description="Associated project ID")
    labels: List[str] = Field(default_factory=list, description="Thread labels")
    pinned_scope: Optional[dict] = Field(None, description="Pinned scope/connector configuration")


class ThreadDeliverable(BaseModel):
    """Deliverable item in Thread Bundle"""
    id: str = Field(..., description="Artifact ID")
    title: str = Field(..., description="Artifact title")
    artifact_type: str = Field(..., description="Artifact type")
    source: Literal['playbook', 'connector', 'manual', 'ai_generated'] = Field(
        ..., description="Source of the artifact"
    )
    source_event_id: str = Field(..., description="Source event ID")
    status: Literal['draft', 'final', 'archived'] = Field(..., description="Artifact status")
    updated_at: str = Field(..., description="Last update timestamp (ISO format)")


class ThreadReferenceResponse(BaseModel):
    """Reference item in Thread Bundle (API response format)"""
    id: str = Field(..., description="Reference ID")
    source_type: Literal['obsidian', 'notion', 'wordpress', 'local_file', 'url', 'google_drive'] = Field(
        ..., description="Source connector type"
    )
    uri: str = Field(..., description="Real URI (clickable)")
    title: str = Field(..., description="Reference title")
    snippet: Optional[str] = Field(None, description="Short summary snippet")
    reason: Optional[str] = Field(None, description="Reason for pinning")
    created_at: str = Field(..., description="Creation timestamp (ISO format)")
    pinned_by: Literal['user', 'ai'] = Field(default='user', description="Who pinned this reference")


class ThreadRun(BaseModel):
    """Execution run in Thread Bundle"""
    id: str = Field(..., description="Execution ID")
    playbook_name: str = Field(..., description="Playbook name")
    status: Literal['running', 'completed', 'failed', 'cancelled'] = Field(
        ..., description="Execution status"
    )
    started_at: str = Field(..., description="Start timestamp (ISO format)")
    duration_ms: Optional[int] = Field(None, description="Execution duration in milliseconds")
    steps_completed: int = Field(..., description="Number of completed steps")
    steps_total: int = Field(..., description="Total number of steps")
    deliverable_ids: List[str] = Field(default_factory=list, description="Associated artifact IDs")


class ThreadSource(BaseModel):
    """Source/connector in Thread Bundle"""
    id: str = Field(..., description="Source identifier")
    type: Literal['wordpress_site', 'obsidian_vault', 'notion_db', 'google_drive', 'local_folder'] = Field(
        ..., description="Source type"
    )
    identifier: str = Field(..., description="Source identifier (site_id, vault_name, etc.)")
    display_name: str = Field(..., description="Display name")
    permissions: List[Literal['read', 'write']] = Field(
        default_factory=list, description="Permissions"
    )
    last_sync_at: Optional[str] = Field(None, description="Last sync timestamp (ISO format)")
    sync_status: Literal['connected', 'disconnected', 'syncing'] = Field(
        default='connected', description="Sync status"
    )


class ThreadBundle(BaseModel):
    """Complete Thread Bundle response"""
    thread_id: str = Field(..., description="Thread ID")
    overview: ThreadOverview = Field(..., description="Thread overview")
    deliverables: List[ThreadDeliverable] = Field(
        default_factory=list, description="Deliverables (artifacts)"
    )
    references: List[ThreadReferenceResponse] = Field(
        default_factory=list, description="References (pinned resources)"
    )
    runs: List[ThreadRun] = Field(
        default_factory=list, description="Execution runs"
    )
    sources: List[ThreadSource] = Field(
        default_factory=list, description="Sources/connectors"
    )
