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


__all__ = [
    "FORBIDDEN_RAW_MEDIA_KEYS",
    "MediaSignalEvent",
    "MediaSignalEventType",
    "MediaSignalMessage",
    "MediaSignalMessageType",
    "MediaSignalParticipant",
    "MediaSourceKind",
    "MediaStreamRef",
    "contains_raw_media_payload",
]
