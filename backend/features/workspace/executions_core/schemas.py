"""Schemas for workspace execution routes."""

from typing import Optional

from pydantic import BaseModel, Field


class ExecutionChatRequest(BaseModel):
    """Request model for posting execution chat messages."""

    content: str = Field(..., description="Message content")
    step_id: Optional[str] = Field(
        None, description="Optional: step ID this message is about"
    )
    message_type: str = Field(
        "question",
        description="Message type: question/note/route_proposal/system_hint",
    )
