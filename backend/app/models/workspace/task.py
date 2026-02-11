"""
Task models — Task, TaskFeedback, TaskPreference.
"""

from datetime import datetime
from typing import Optional, Dict, Any, List

from pydantic import BaseModel, Field

from ._common import _utc_now
from .enums import (
    TaskStatus,
    TaskFeedbackAction,
    TaskFeedbackReasonCode,
    TaskPreferenceAction,
)


# ==================== Task Model ====================


class Task(BaseModel):
    """
    Task model - represents a single execution task from a Pack

    Tasks are derived from MindEvents and stored in the tasks table.
    They represent the execution state of a Pack within a workspace.
    """

    id: str = Field(..., description="Unique task identifier")
    workspace_id: str = Field(..., description="Workspace ID")
    message_id: str = Field(..., description="Associated message/event ID")
    execution_id: Optional[str] = Field(
        None, description="Associated playbook execution ID (if applicable)"
    )
    project_id: Optional[str] = Field(
        None, description="Associated project ID (if applicable)"
    )
    pack_id: str = Field(..., description="Pack identifier")
    task_type: str = Field(
        ..., description="Task type (e.g., 'extract_intents', 'generate_tasks')"
    )
    status: TaskStatus = Field(..., description="Task execution status")
    params: Dict[str, Any] = Field(default_factory=dict, description="Task parameters")
    result: Optional[Dict[str, Any]] = Field(None, description="Task execution result")
    execution_context: Optional[Dict[str, Any]] = Field(
        None,
        description="Execution context (playbook_code, trigger_source, current_step_index, etc.)",
    )
    storyline_tags: List[str] = Field(
        default_factory=list,
        description="Storyline tags for cross-project story tracking (e.g., brand storylines, learning paths, research themes)",
    )
    created_at: datetime = Field(
        default_factory=_utc_now, description="Creation timestamp"
    )
    started_at: Optional[datetime] = Field(None, description="Task start timestamp")
    completed_at: Optional[datetime] = Field(
        None, description="Task completion timestamp"
    )
    error: Optional[str] = Field(None, description="Error message if task failed")

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


# ==================== Task Feedback Models ====================


class TaskFeedback(BaseModel):
    """
    Task feedback model - records user feedback on AI-generated tasks

    Used to track user rejections, dismissals, and acceptances of tasks
    to improve task recommendation strategies and personalize preferences.
    """

    id: str = Field(..., description="Unique feedback identifier")
    task_id: str = Field(..., description="Associated task ID")
    workspace_id: str = Field(..., description="Workspace ID")
    user_id: str = Field(..., description="User profile ID")
    action: TaskFeedbackAction = Field(
        ..., description="Feedback action: accept/reject/dismiss"
    )
    reason_code: Optional[TaskFeedbackReasonCode] = Field(
        None, description="Reason code for rejection/dismissal (optional)"
    )
    comment: Optional[str] = Field(
        None, description="Optional user comment explaining the feedback"
    )
    created_at: datetime = Field(
        default_factory=_utc_now, description="Creation timestamp"
    )

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


# ==================== Task Preference Models ====================


class TaskPreference(BaseModel):
    """
    Task preference model - records user preferences for task types and packs

    Used to personalize task recommendations by tracking which packs/task_types
    the user prefers, rejects, or wants to see less frequently.
    """

    id: str = Field(..., description="Unique preference identifier")
    workspace_id: str = Field(..., description="Workspace ID")
    user_id: str = Field(..., description="User profile ID")
    pack_id: Optional[str] = Field(
        None, description="Pack ID (if preference is pack-level)"
    )
    task_type: Optional[str] = Field(
        None,
        description="Task type (if preference is task-level, more specific than pack_id)",
    )
    action: TaskPreferenceAction = Field(
        ..., description="Preference action: enable/disable/auto_suggest/manual_only"
    )
    auto_suggest: bool = Field(
        default=True,
        description="Whether to auto-suggest this pack/task_type (default: True)",
    )
    last_feedback: Optional[TaskFeedbackAction] = Field(
        None,
        description="Last feedback action (accept/reject/dismiss) for this pack/task_type",
    )
    reject_count_30d: int = Field(
        default=0, description="Number of rejections in the last 30 days"
    )
    accept_count_30d: int = Field(
        default=0, description="Number of acceptances in the last 30 days"
    )
    created_at: datetime = Field(
        default_factory=_utc_now, description="Creation timestamp"
    )
    updated_at: datetime = Field(
        default_factory=_utc_now, description="Last update timestamp"
    )

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}
