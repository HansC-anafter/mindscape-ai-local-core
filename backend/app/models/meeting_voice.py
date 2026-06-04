"""Contracts for Meeting Engine bounded voice turns."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from backend.app.models.meeting_command import MeetingCommandAcceptResponse
from backend.app.models.object_runtime import ObjectRoleEntry


MeetingVoiceTurnStatus = Literal[
    "transcribed_command_submitted",
    "ignored_empty_transcript",
    "stt_unavailable",
]


class MeetingVoiceTurnRequest(BaseModel):
    """Client request for one bounded voice turn."""

    model_config = ConfigDict(extra="forbid")

    client_turn_id: str = Field(min_length=1)
    audio_base64: str = Field(min_length=1)
    mime_type: str = Field(min_length=1)
    language: Optional[str] = "auto"
    origin_surface: str = "meeting_voice"
    context_objects: List[ObjectRoleEntry] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class MeetingVoiceTurnResponse(BaseModel):
    """Terminal response for a bounded voice turn."""

    model_config = ConfigDict(extra="forbid")

    status: MeetingVoiceTurnStatus
    transcript: Optional[str] = None
    language: Optional[str] = None
    duration: Optional[float] = None
    audio_byte_count: Optional[int] = None
    command_response: Optional[MeetingCommandAcceptResponse] = None
    reason: Optional[str] = None


__all__ = [
    "MeetingVoiceTurnRequest",
    "MeetingVoiceTurnResponse",
    "MeetingVoiceTurnStatus",
]
