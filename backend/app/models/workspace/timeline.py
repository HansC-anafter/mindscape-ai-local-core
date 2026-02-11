"""
Timeline models — TimelineItem, ConversationThread.
"""

from datetime import datetime
from typing import Optional, Dict, Any, List

from pydantic import BaseModel, Field

from ._common import _utc_now
from .enums import TimelineItemType


class TimelineItem(BaseModel):
    """
    TimelineItem model - represents a result card displayed in the timeline

    TimelineItems are derived from MindEvents and stored in the timeline_items table.
    They represent the results of Pack executions and are displayed in the right panel.
    """

    id: str = Field(..., description="Unique timeline item identifier")
    workspace_id: str = Field(..., description="Workspace ID")
    message_id: str = Field(..., description="Associated message/event ID")
    task_id: Optional[str] = Field(
        None, description="Associated task ID (optional for file analysis items)"
    )
    type: TimelineItemType = Field(..., description="Timeline item type")
    title: str = Field(..., description="Display title")
    summary: str = Field(..., description="Summary text")
    data: Dict[str, Any] = Field(default_factory=dict, description="Additional data")
    cta: Optional[List[Dict[str, Any]]] = Field(
        None, description="Call-to-action buttons (if applicable)"
    )
    created_at: datetime = Field(
        default_factory=_utc_now, description="Creation timestamp"
    )

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class ConversationThread(BaseModel):
    """
    Conversation Thread model - represents a conversation thread within a workspace

    Threads allow users to organize conversations into separate streams,
    similar to ChatGPT's conversation threads or Cursor's "new agent" feature.
    """

    id: str = Field(..., description="Unique thread identifier")
    workspace_id: str = Field(..., description="Workspace ID this thread belongs to")
    title: str = Field(..., description="Thread title")
    project_id: Optional[str] = Field(
        None, description="Optional associated project ID"
    )
    pinned_scope: Optional[str] = Field(
        None, description="Optional pinned scope for this thread"
    )
    created_at: datetime = Field(
        default_factory=_utc_now, description="Creation timestamp"
    )
    updated_at: datetime = Field(
        default_factory=_utc_now, description="Last update timestamp"
    )
    last_message_at: datetime = Field(
        default_factory=_utc_now, description="Last message timestamp"
    )
    message_count: int = Field(
        default=0, description="Number of messages in this thread"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Extensible metadata"
    )
    is_default: bool = Field(
        default=False,
        description="Whether this is the default thread for the workspace",
    )

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}
