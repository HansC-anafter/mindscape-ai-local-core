"""Contracts for workspace-scoped real-time media signaling."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


MediaSignalParticipant = Literal["workspace", "source"]

MediaSourceKind = Literal[
    "phone_camera",
    "desktop_camera",
    "usb_camera",
    "virtual_camera",
    "external_provider_camera",
]

LiveMediaRelayProfile = Literal["public"]
LiveMediaCapability = Literal["video", "audio"]
LiveMediaSessionState = Literal[
    "waiting_for_publisher",
    "publishing",
    "ready",
    "degraded",
    "stopped",
    "expired",
]
LiveMotionCoachPack = Literal["yogacoach", "dance_motion_coach"]

MediaSignalMessageType = Literal[
    "workspace_join",
    "source_join",
    "ready",
    "offer",
    "answer",
    "ice_candidate",
    "close",
]

MediaSignalEventType = Literal[
    "participant_joined",
    "participant_left",
    "ready",
    "offer",
    "answer",
    "ice_candidate",
    "close",
    "session_error",
]

FORBIDDEN_RAW_MEDIA_KEYS = {
    "audio_base64",
    "video_base64",
    "frame_base64",
    "media_base64",
    "image_base64",
    "payload_base64",
    "data_url",
}


def contains_raw_media_payload(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in FORBIDDEN_RAW_MEDIA_KEYS:
                return True
            if contains_raw_media_payload(item):
                return True
        return False
    if isinstance(value, list):
        return any(contains_raw_media_payload(item) for item in value)
    if isinstance(value, str):
        lowered = value.lower()
        return lowered.startswith("data:audio/") or lowered.startswith("data:video/")
    return False


class MediaSignalMessage(BaseModel):
    """Client message over the WebRTC signaling WebSocket."""

    model_config = ConfigDict(extra="forbid")

    type: MediaSignalMessageType
    sdp: Optional[str] = None
    candidate: Optional[Dict[str, Any]] = None
    reason: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def reject_raw_media_payload(cls, value: Any) -> Any:
        if contains_raw_media_payload(value):
            raise ValueError("raw_media_payload_not_allowed")
        return value


class MediaSignalEvent(BaseModel):
    """Server event emitted over the WebRTC signaling WebSocket."""

    model_config = ConfigDict(extra="forbid")

    type: MediaSignalEventType
    workspace_id: str
    device_session_id: str
    media_session_id: str
    sender: Optional[MediaSignalParticipant] = None
    sdp: Optional[str] = None
    candidate: Optional[Dict[str, Any]] = None
    reason: Optional[str] = None
    message: Optional[str] = None
    recoverable: Optional[bool] = None
    ice_servers: List[Dict[str, Any]] = Field(default_factory=list)
    created_at_epoch: float


class MediaStreamRef(BaseModel):
    """Compact reference to a browser-owned live media stream."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    device_session_id: str
    media_session_id: str
    source_kind: MediaSourceKind
    stream_id: str
    track_kinds: List[str] = Field(default_factory=list)
    started_at_epoch: float


class CreateLiveMediaSessionRequest(BaseModel):
    """Bounded input for one device-owned live media path."""

    model_config = ConfigDict(extra="forbid")

    source_kind: MediaSourceKind
    relay_profile: LiveMediaRelayProfile = "public"
    capabilities: List[LiveMediaCapability] = Field(default_factory=lambda: ["video"])
    analysis_reserved: bool = True

    @model_validator(mode="after")
    def normalize_capabilities(self) -> "CreateLiveMediaSessionRequest":
        unique_capabilities = list(dict.fromkeys(self.capabilities))
        if not unique_capabilities:
            raise ValueError("media_capabilities_required")
        self.capabilities = unique_capabilities
        return self


class LiveMediaSessionEndpoints(BaseModel):
    """Credential-free endpoints derived from one opaque relay path."""

    model_config = ConfigDict(extra="forbid")

    whip_publish_url: str
    whep_preview_url: str
    rtmps_publish_url: str
    rtsps_receiver_url: str


class LiveMediaSessionDescriptor(BaseModel):
    """Credential-free identity and lifecycle for one live media path."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    device_session_id: str
    media_session_id: str
    stream_path: str
    source_kind: MediaSourceKind
    relay_profile: LiveMediaRelayProfile
    capabilities: List[LiveMediaCapability]
    analysis_reserved: bool
    state: LiveMediaSessionState
    endpoints: LiveMediaSessionEndpoints
    receiver_descriptor_ref: str
    created_at_epoch: float
    updated_at_epoch: float
    expires_at_epoch: float
    terminal_reason: Optional[str] = None


class LiveMediaSessionTokens(BaseModel):
    """Source and preview tokens returned only by create or refresh."""

    model_config = ConfigDict(extra="forbid")

    publish: str = Field(repr=False)
    preview: str = Field(repr=False)


class LiveMediaReceiverBinding(BaseModel):
    """Server-only identities that bind one receiver to one append writer."""

    model_config = ConfigDict(extra="forbid")

    receiver_identity: str = Field(min_length=1, repr=False)
    append_owner_id: str = Field(min_length=1, repr=False)


class LiveMediaReceiverAccess(BaseModel):
    """Server-only receiver access; never expose this model from a route."""

    model_config = ConfigDict(extra="forbid")

    session: LiveMediaSessionDescriptor
    binding: LiveMediaReceiverBinding = Field(repr=False)
    receiver_token: str = Field(min_length=1, repr=False)


class StartLiveMediaReceiverRequest(BaseModel):
    """Credential-free practice context used to start the host receiver."""

    model_config = ConfigDict(extra="forbid")

    live_motion_session_id: str = Field(min_length=1, max_length=160)
    meeting_session_id: str = Field(min_length=1, max_length=160)
    practice_session_id: str = Field(min_length=1, max_length=240)
    coach_pack: LiveMotionCoachPack
    practice_mode: str = Field(min_length=1, max_length=80)
    reference_url: Optional[str] = Field(default=None, max_length=4096)
    motion_reference_profile_artifact_id: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=160,
    )
    user_goal: Optional[str] = Field(default=None, max_length=2000)
    expected_duration_ms: float = Field(default=0.0, ge=0.0)


class LiveMediaSessionAccess(BaseModel):
    """Explicit credential response for an active live media session."""

    model_config = ConfigDict(extra="forbid")

    session: LiveMediaSessionDescriptor
    tokens: LiveMediaSessionTokens = Field(repr=False)


__all__ = [
    "CreateLiveMediaSessionRequest",
    "FORBIDDEN_RAW_MEDIA_KEYS",
    "LiveMediaCapability",
    "LiveMediaReceiverAccess",
    "LiveMediaReceiverBinding",
    "LiveMediaRelayProfile",
    "LiveMediaSessionAccess",
    "LiveMediaSessionDescriptor",
    "LiveMediaSessionEndpoints",
    "LiveMediaSessionState",
    "LiveMediaSessionTokens",
    "LiveMotionCoachPack",
    "MediaSignalEvent",
    "MediaSignalEventType",
    "MediaSignalMessage",
    "MediaSignalMessageType",
    "MediaSignalParticipant",
    "MediaSourceKind",
    "MediaStreamRef",
    "StartLiveMediaReceiverRequest",
    "contains_raw_media_payload",
]
