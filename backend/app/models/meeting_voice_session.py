"""Contracts for Meeting Engine realtime voice sessions."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from backend.app.models.meeting_command import MeetingCommandAcceptResponse
from backend.app.models.meeting_voice_context import MeetingVoiceCommandContext
from backend.app.models.object_runtime import ObjectRoleEntry


MeetingVoiceSessionState = Literal[
    "idle",
    "listening",
    "transcribing",
    "speaking",
    "interrupted",
    "closed",
]

MeetingVoiceClientMessageType = Literal[
    "session_start",
    "audio_window",
    "utterance_end",
    "interrupt",
    "cancel",
    "ack",
    "session_close",
]

MeetingVoiceServerEventType = Literal[
    "session_ready",
    "transcript_candidate",
    "transcript_final",
    "command_submitted",
    "speech_unavailable",
    "interrupted",
    "cancelled",
    "session_closed",
    "session_error",
]


class MeetingVoiceSessionClientMessage(BaseModel):
    """Client message over the realtime voice session WebSocket."""

    model_config = ConfigDict(extra="allow")

    type: MeetingVoiceClientMessageType
    utterance_id: Optional[str] = None
    audio_base64: Optional[str] = None
    mime_type: Optional[str] = None
    language: Optional[str] = "auto"
    command_context: Optional[MeetingVoiceCommandContext] = None
    context_objects: List[ObjectRoleEntry] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class MeetingVoiceAudioWindow(BaseModel):
    """Complete client-side VAD utterance window."""

    model_config = ConfigDict(extra="forbid")

    client_session_id: str = Field(min_length=1)
    utterance_id: str = Field(min_length=1)
    audio_base64: str = Field(min_length=1)
    mime_type: str = Field(min_length=1)
    language: Optional[str] = "auto"
    command_context: Optional[MeetingVoiceCommandContext] = None
    context_objects: List[ObjectRoleEntry] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class MeetingVoiceTranscriptCandidate(BaseModel):
    """Transcript produced from one bounded utterance window."""

    model_config = ConfigDict(extra="forbid")

    client_session_id: str
    utterance_id: str
    transcript: str
    language: Optional[str] = None
    duration: Optional[float] = None
    audio_mime_type: str
    audio_byte_count: int
    command_context: Optional[MeetingVoiceCommandContext] = None
    context_objects: List[ObjectRoleEntry] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class MeetingVoiceSessionEvent(BaseModel):
    """Server event emitted over the realtime voice session WebSocket."""

    model_config = ConfigDict(extra="forbid")

    type: MeetingVoiceServerEventType
    workspace_id: str
    meeting_id: str
    client_session_id: str
    state: Optional[MeetingVoiceSessionState] = None
    utterance_id: Optional[str] = None
    transcript: Optional[str] = None
    language: Optional[str] = None
    duration: Optional[float] = None
    audio_byte_count: Optional[int] = None
    command_response: Optional[MeetingCommandAcceptResponse] = None
    reason: Optional[str] = None
    message: Optional[str] = None
    recoverable: Optional[bool] = None


__all__ = [
    "MeetingVoiceAudioWindow",
    "MeetingVoiceClientMessageType",
    "MeetingVoiceServerEventType",
    "MeetingVoiceSessionClientMessage",
    "MeetingVoiceSessionEvent",
    "MeetingVoiceSessionState",
    "MeetingVoiceTranscriptCandidate",
]
