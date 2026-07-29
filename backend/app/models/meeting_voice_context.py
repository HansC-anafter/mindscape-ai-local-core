"""Normalized Meeting command context carried by voice transports."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from backend.app.models.meeting_command import (
    MeetingCommandWriteMode,
    MeetingRequestedAction,
)
from backend.app.models.object_runtime import ObjectRoleEntry


class MeetingVoiceCommandContext(BaseModel):
    """Meeting command envelope fields that are independent of transcript identity."""

    model_config = ConfigDict(extra="forbid")

    context_objects: List[ObjectRoleEntry] = Field(default_factory=list)
    requested_action: Optional[MeetingRequestedAction] = None
    expected_outputs: List[str] = Field(default_factory=list)
    write_mode: MeetingCommandWriteMode = "recommendation_only"
    thread_id: Optional[str] = None
    meeting_mentions: List[Dict[str, Any]] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


def normalize_meeting_voice_command_context(
    *,
    command_context: MeetingVoiceCommandContext | None,
    context_objects: List[ObjectRoleEntry],
    metadata: Dict[str, Any],
) -> MeetingVoiceCommandContext:
    """Normalize legacy voice context without merging two ambiguous authorities."""

    if command_context is not None:
        if context_objects or metadata:
            raise ValueError("conflicting_command_context")
        return command_context
    return MeetingVoiceCommandContext(
        context_objects=context_objects,
        metadata=metadata,
    )


__all__ = [
    "MeetingVoiceCommandContext",
    "normalize_meeting_voice_command_context",
]
