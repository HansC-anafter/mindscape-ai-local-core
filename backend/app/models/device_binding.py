"""Contracts for workspace-scoped device binding sessions."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


DeviceSourceType = Literal[
    "phone_camera",
    "desktop_camera",
    "usb_camera",
    "virtual_camera",
    "external_provider_camera",
    "microphone",
]

DeviceBindingSessionState = Literal[
    "pairing",
    "paired",
    "active",
    "revoked",
    "expired",
    "closed",
    "rejected",
]

DeviceControlMessageType = Literal[
    "workspace_subscribe",
    "source_join",
    "reference_lesson_state",
    "heartbeat",
    "session_close",
    "ack",
]

DeviceControlEventType = Literal[
    "pairing_ready",
    "reference_lesson_state",
    "session_paired",
    "session_active",
    "session_revoked",
    "session_expired",
    "session_closed",
    "session_rejected",
    "heartbeat_ack",
    "session_error",
]


class DeviceCapabilityDeclaration(BaseModel):
    """Capabilities declared by one source device."""

    model_config = ConfigDict(extra="forbid")

    device_id: Optional[str] = None
    display_name: Optional[str] = None
    source_types: List[DeviceSourceType] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DevicePairingCode(BaseModel):
    """Short-lived pairing code issued for a workspace."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    pairing_code: str
    expires_at_epoch: float
    expires_in_seconds: int
    device_link_path: str


class DeviceMediaAnalysisHandoff(BaseModel):
    """Credential-free analysis identity retained across Workbench mounts."""

    model_config = ConfigDict(extra="forbid")

    live_motion_session_id: str = Field(min_length=1, max_length=160)
    meeting_session_id: str = Field(min_length=1, max_length=160)
    practice_session_id: str = Field(min_length=1, max_length=240)
    coach_pack: Literal["yogacoach", "dance_motion_coach"]
    practice_mode: Literal["record_summary", "teacher_assessment", "live_guidance"]


class DeviceSessionEntry(BaseModel):
    """Process-local active source device session."""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    session_id: str
    workspace_id: str
    pairing_code: str
    device_id: str
    display_name: Optional[str] = None
    source_types: List[DeviceSourceType] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    state: DeviceBindingSessionState
    created_at_epoch: float
    updated_at_epoch: float
    expires_at_epoch: float
    media_session_id: Optional[str] = None
    media_session_state: Optional[str] = None
    media_receiver_metrics: Dict[str, Any] = Field(default_factory=dict)
    media_analysis_handoff: Optional[DeviceMediaAnalysisHandoff] = None
    media_session_expires_at_epoch: Optional[float] = None
    terminal_reason: Optional[str] = None
    websocket: Any = Field(default=None, exclude=True)


class DeviceControlMessage(BaseModel):
    """Client message over the device binding control WebSocket."""

    model_config = ConfigDict(extra="allow")

    type: DeviceControlMessageType
    device_id: Optional[str] = None
    display_name: Optional[str] = None
    source_types: List[DeviceSourceType] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    reference_lesson_state: Optional[Dict[str, Any]] = None
    heartbeat_sequence: Optional[int] = Field(default=None, ge=1)


class DeviceControlEvent(BaseModel):
    """Server event emitted over the device binding control WebSocket."""

    model_config = ConfigDict(extra="forbid")

    type: DeviceControlEventType
    workspace_id: str
    pairing_code: Optional[str] = None
    session_id: Optional[str] = None
    device_id: Optional[str] = None
    display_name: Optional[str] = None
    source_types: List[DeviceSourceType] = Field(default_factory=list)
    state: Optional[DeviceBindingSessionState] = None
    expires_at_epoch: Optional[float] = None
    active_sessions: List[DeviceSessionEntry] = Field(default_factory=list)
    reason: Optional[str] = None
    message: Optional[str] = None
    recoverable: Optional[bool] = None
    reference_lesson_state: Optional[Dict[str, Any]] = None
    heartbeat_sequence: Optional[int] = Field(default=None, ge=1)


__all__ = [
    "DeviceBindingSessionState",
    "DeviceCapabilityDeclaration",
    "DeviceControlEvent",
    "DeviceControlEventType",
    "DeviceControlMessage",
    "DeviceControlMessageType",
    "DevicePairingCode",
    "DeviceSessionEntry",
    "DeviceSourceType",
]
