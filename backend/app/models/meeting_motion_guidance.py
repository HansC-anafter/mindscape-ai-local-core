"""Contracts for Meeting Engine motion practice guidance sessions."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


MotionGuidanceSessionState = Literal[
    "idle",
    "active",
    "interrupted",
    "closed",
]

MotionGuidanceClientMessageType = Literal[
    "session_start",
    "motion_window",
    "rollup_delta",
    "practice_state",
    "interrupt",
    "ack",
    "session_close",
]

MotionGuidanceServerEventType = Literal[
    "session_ready",
    "guidance_cue",
    "guidance_suppressed",
    "interrupted",
    "session_closed",
    "session_error",
]

MotionGuidanceCuePriority = Literal["info", "warning", "correction"]


class MeetingMotionGuidanceClientMessage(BaseModel):
    """Client message over the motion guidance WebSocket."""

    model_config = ConfigDict(extra="allow")

    type: MotionGuidanceClientMessageType
    event_id: Optional[str] = None
    live_session_id: Optional[str] = None
    motion_window_ref: Optional[str] = None
    rollup_ref: Optional[str] = None
    command_ref: Optional[str] = None
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    mean_confidence: Optional[float] = Field(default=None, ge=0, le=1)
    top_findings: List[str] = Field(default_factory=list)
    findings: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class MeetingMotionGuidanceEvent(BaseModel):
    """Server event emitted over the motion guidance WebSocket."""

    model_config = ConfigDict(extra="forbid")

    type: MotionGuidanceServerEventType
    workspace_id: str
    meeting_id: str
    practice_session_id: str
    state: Optional[MotionGuidanceSessionState] = None
    event_id: Optional[str] = None
    cue_id: Optional[str] = None
    cue_key: Optional[str] = None
    cue_text: Optional[str] = None
    cue_priority: Optional[MotionGuidanceCuePriority] = None
    speakable: Optional[bool] = None
    motion_window_ref: Optional[str] = None
    rollup_ref: Optional[str] = None
    command_ref: Optional[str] = None
    reason: Optional[str] = None
    message: Optional[str] = None
    recoverable: Optional[bool] = None
    throttle_until_epoch: Optional[float] = None


__all__ = [
    "MeetingMotionGuidanceClientMessage",
    "MeetingMotionGuidanceEvent",
    "MotionGuidanceClientMessageType",
    "MotionGuidanceCuePriority",
    "MotionGuidanceServerEventType",
    "MotionGuidanceSessionState",
]
