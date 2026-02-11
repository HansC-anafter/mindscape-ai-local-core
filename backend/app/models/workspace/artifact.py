"""
Artifact models — Artifact, ThreadReference, BackgroundRoutine.
"""

from datetime import datetime
from typing import Optional, Dict, Any, List, Literal

from pydantic import BaseModel, Field

from ._common import _utc_now
from .enums import ArtifactType, PrimaryActionType


class Artifact(BaseModel):
    """
    Artifact model - represents a playbook execution output

    Artifacts are automatically created when playbooks complete execution.
    They represent the tangible outputs (checklists, drafts, configs, etc.)
    that users can view, copy, download, or publish.
    """

    id: str = Field(..., description="Unique artifact identifier")
    workspace_id: str = Field(..., description="Workspace ID")
    intent_id: Optional[str] = Field(
        None, description="Associated Intent ID (supports driver-led experience)"
    )
    task_id: Optional[str] = Field(None, description="Associated task ID")
    execution_id: Optional[str] = Field(None, description="Associated execution ID")
    thread_id: Optional[str] = Field(
        None, description="Associated conversation thread ID"
    )
    playbook_code: str = Field(..., description="Source playbook code")
    artifact_type: ArtifactType = Field(..., description="Artifact type")
    title: str = Field(..., description="Artifact title")
    summary: str = Field(..., description="Artifact summary")
    content: Dict[str, Any] = Field(
        default_factory=dict, description="Artifact content (JSON)"
    )
    storage_ref: Optional[str] = Field(
        None,
        description="Storage location: DB/file path/external URL (supports external sync)",
    )
    sync_state: Optional[str] = Field(
        None,
        description="Sync state: None (local) / pending / synced / failed (for external sync)",
    )
    primary_action_type: PrimaryActionType = Field(
        ..., description="Primary action type"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )
    created_at: datetime = Field(
        default_factory=_utc_now, description="Creation timestamp"
    )
    updated_at: datetime = Field(
        default_factory=_utc_now, description="Last update timestamp"
    )

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class ThreadReference(BaseModel):
    """
    ThreadReference model - represents a reference pinned to a conversation thread

    References are external resources (Obsidian notes, Notion pages, WordPress posts,
    local files, URLs) that are associated with a thread for context and retrieval.
    """

    id: str = Field(..., description="Unique reference identifier")
    workspace_id: str = Field(..., description="Workspace ID")
    thread_id: str = Field(..., description="Conversation thread ID")
    source_type: Literal[
        "obsidian", "notion", "wordpress", "local_file", "url", "google_drive"
    ] = Field(..., description="Source connector type")
    uri: str = Field(..., description="Real URI (clickable, can navigate back)")
    title: str = Field(..., description="Reference title")
    snippet: Optional[str] = Field(None, description="Short summary snippet")
    reason: Optional[str] = Field(None, description="Reason for pinning (optional)")
    pinned_by: Literal["user", "ai"] = Field(
        default="user", description="Who pinned this reference"
    )
    created_at: datetime = Field(
        default_factory=_utc_now, description="Creation timestamp"
    )
    updated_at: datetime = Field(
        default_factory=_utc_now, description="Last update timestamp"
    )

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class BackgroundRoutine(BaseModel):
    """
    BackgroundRoutine model - represents a long-running background task

    Background routines are like cron jobs / daemons that run on a schedule.
    Once enabled, they run automatically without requiring user confirmation for each execution.
    Examples: habit_learning, daily_reminders
    """

    id: str = Field(..., description="Unique background routine identifier")
    workspace_id: str = Field(..., description="Workspace ID")
    playbook_code: str = Field(..., description="Playbook code to run")
    enabled: bool = Field(default=False, description="Whether the routine is enabled")
    config: Dict[str, Any] = Field(
        default_factory=dict, description="Schedule and condition configuration"
    )
    last_run_at: Optional[datetime] = Field(
        None, description="Last execution timestamp"
    )
    next_run_at: Optional[datetime] = Field(
        None, description="Next scheduled execution timestamp"
    )
    last_status: Optional[str] = Field(
        None, description="Last execution status: 'ok' | 'failed'"
    )

    # Tool dependency readiness status (system-managed, stored as separate columns)
    readiness_status: Optional[str] = Field(
        default=None, description="Readiness status: ready / needs_setup / unsupported"
    )
    tool_statuses: Optional[Dict[str, str]] = Field(
        default=None,
        description="Status of required tools: tool_type -> status (JSON string in DB)",
    )
    error_count: int = Field(
        default=0, description="Consecutive error count (for auto-pause)"
    )
    auto_paused: bool = Field(
        default=False, description="Whether routine was auto-paused due to errors"
    )

    created_at: datetime = Field(
        default_factory=_utc_now, description="Creation timestamp"
    )
    updated_at: datetime = Field(
        default_factory=_utc_now, description="Last update timestamp"
    )

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}
