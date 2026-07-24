"""Process-local WebRTC signaling registry for bound source devices."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from backend.app.models.media_transport import (
    MediaSignalEvent,
    MediaSignalMessage,
    MediaSignalParticipant,
)
from backend.app.services.orchestration.meeting.device_binding_registry import (
    DeviceBindingRegistry,
)


MAX_WEBRTC_SIGNAL_MESSAGE_BYTES = 64 * 1024
MAX_PENDING_WEBRTC_SIGNAL_EVENTS_PER_PEER = 32


class WebRTCSignalingRegistryError(Exception):
    """Registry-level WebRTC signaling error."""

    def __init__(
        self,
        *,
        reason: str,
        message: str,
        status_code: int = 400,
        close_code: int = 4400,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message
        self.status_code = status_code
        self.close_code = close_code


@dataclass
class _WebRTCSignalSession:
    workspace_id: str
    device_session_id: str
    media_session_id: str
    workspace_websocket: Any = None
    source_websocket: Any = None
    pending_to_workspace: list[MediaSignalEvent] = field(default_factory=list)
    pending_to_source: list[MediaSignalEvent] = field(default_factory=list)
    created_at_epoch: float = field(default_factory=time.time)
    updated_at_epoch: float = field(default_factory=time.time)

    def websocket_for(self, participant: MediaSignalParticipant) -> Any:
        return (
            self.workspace_websocket
            if participant == "workspace"
            else self.source_websocket
        )

    def set_websocket(self, participant: MediaSignalParticipant, websocket: Any) -> None:
        if participant == "workspace":
            self.workspace_websocket = websocket
        else:
            self.source_websocket = websocket
        self.updated_at_epoch = time.time()

    def clear_websocket(self, participant: MediaSignalParticipant, websocket: Any) -> None:
        if participant == "workspace" and self.workspace_websocket is websocket:
            self.workspace_websocket = None
        if participant == "source" and self.source_websocket is websocket:
            self.source_websocket = None
        self.updated_at_epoch = time.time()

    def pending_for(self, participant: MediaSignalParticipant) -> list[MediaSignalEvent]:
        return (
            self.pending_to_workspace
            if participant == "workspace"
            else self.pending_to_source
        )

    def empty(self) -> bool:
        return self.workspace_websocket is None and self.source_websocket is None


class WebRTCSignalingRegistry:
    """Tracks active LAN-only WebRTC signaling peers for device sessions."""

    def __init__(self) -> None:
        self._sessions: dict[str, _WebRTCSignalSession] = {}

    def attach_participant(
        self,
        *,
        workspace_id: str,
        device_session_id: str,
        media_session_id: str,
        participant: MediaSignalParticipant,
        websocket: Any,
        device_binding_registry: DeviceBindingRegistry,
    ) -> tuple[MediaSignalEvent, list[MediaSignalEvent], Any | None, Any | None]:
        self._require_active_device_session(
            workspace_id=workspace_id,
            device_session_id=device_session_id,
            device_binding_registry=device_binding_registry,
        )
        key = self._key(
            workspace_id=workspace_id,
            device_session_id=device_session_id,
            media_session_id=media_session_id,
        )
        active_session = self._active_session_for_device(
            workspace_id=workspace_id,
            device_session_id=device_session_id,
        )
        if active_session is not None and active_session.media_session_id != media_session_id:
            raise WebRTCSignalingRegistryError(
                reason="active_media_session_exists",
                message="This device binding session already has one active media session.",
                status_code=409,
                close_code=4409,
            )
        session = self._sessions.setdefault(
            key,
            _WebRTCSignalSession(
                workspace_id=workspace_id,
                device_session_id=device_session_id,
                media_session_id=media_session_id,
            ),
        )
        replaced_websocket = session.websocket_for(participant)
        if replaced_websocket is websocket:
            replaced_websocket = None

        session.set_websocket(participant, websocket)
        peer: MediaSignalParticipant = "source" if participant == "workspace" else "workspace"
        peer_websocket = session.websocket_for(peer)
        pending = list(session.pending_for(participant))
        session.pending_for(participant).clear()
        return (
            self._event(
                event_type="participant_joined",
                workspace_id=workspace_id,
                device_session_id=device_session_id,
                media_session_id=media_session_id,
                sender=participant,
            ),
            pending,
            peer_websocket,
            replaced_websocket,
        )

    def is_active_participant(
        self,
        *,
        workspace_id: str,
        device_session_id: str,
        media_session_id: str,
        participant: MediaSignalParticipant,
        websocket: Any,
    ) -> bool:
        key = self._key(
            workspace_id=workspace_id,
            device_session_id=device_session_id,
            media_session_id=media_session_id,
        )
        session = self._sessions.get(key)
        if session is None:
            return False
        return session.websocket_for(participant) is websocket

    def detach_participant(
        self,
        *,
        workspace_id: str,
        device_session_id: str,
        media_session_id: str,
        participant: MediaSignalParticipant,
        websocket: Any,
    ) -> MediaSignalEvent | None:
        key = self._key(
            workspace_id=workspace_id,
            device_session_id=device_session_id,
            media_session_id=media_session_id,
        )
        session = self._sessions.get(key)
        if session is None:
            return None
        session.clear_websocket(participant, websocket)
        event = self._event(
            event_type="participant_left",
            workspace_id=workspace_id,
            device_session_id=device_session_id,
            media_session_id=media_session_id,
            sender=participant,
        )
        if session.empty():
            self._sessions.pop(key, None)
        return event

    def forward_or_queue(
        self,
        *,
        workspace_id: str,
        device_session_id: str,
        media_session_id: str,
        sender: MediaSignalParticipant,
        message: MediaSignalMessage,
    ) -> tuple[Any | None, MediaSignalEvent]:
        session = self._require_session(
            workspace_id=workspace_id,
            device_session_id=device_session_id,
            media_session_id=media_session_id,
        )
        recipient: MediaSignalParticipant = "source" if sender == "workspace" else "workspace"
        event = self._event(
            event_type=message.type,
            workspace_id=workspace_id,
            device_session_id=device_session_id,
            media_session_id=media_session_id,
            sender=sender,
            sdp=message.sdp,
            candidate=message.candidate,
            reason=message.reason,
        )
        peer_websocket = session.websocket_for(recipient)
        if peer_websocket is None:
            pending = session.pending_for(recipient)
            pending.append(event)
            if len(pending) > MAX_PENDING_WEBRTC_SIGNAL_EVENTS_PER_PEER:
                del pending[0 : len(pending) - MAX_PENDING_WEBRTC_SIGNAL_EVENTS_PER_PEER]
        session.updated_at_epoch = time.time()
        return peer_websocket, event

    def active_count(self) -> int:
        return len(self._sessions)

    def _require_active_device_session(
        self,
        *,
        workspace_id: str,
        device_session_id: str,
        device_binding_registry: DeviceBindingRegistry,
    ) -> None:
        if device_binding_registry.get_active_session(
            workspace_id=workspace_id,
            session_id=device_session_id,
        ) is None:
            raise WebRTCSignalingRegistryError(
                reason="unknown_device_session",
                message="No active device binding session exists for this media session.",
                status_code=404,
                close_code=4404,
            )

    def _require_session(
        self,
        *,
        workspace_id: str,
        device_session_id: str,
        media_session_id: str,
    ) -> _WebRTCSignalSession:
        session = self._sessions.get(
            self._key(
                workspace_id=workspace_id,
                device_session_id=device_session_id,
                media_session_id=media_session_id,
            )
        )
        if session is None:
            raise WebRTCSignalingRegistryError(
                reason="unknown_media_session",
                message="No active media signaling session exists for this peer.",
                status_code=404,
                close_code=4404,
            )
        return session

    def _active_session_for_device(
        self,
        *,
        workspace_id: str,
        device_session_id: str,
    ) -> _WebRTCSignalSession | None:
        for session in self._sessions.values():
            if (
                session.workspace_id == workspace_id
                and session.device_session_id == device_session_id
                and not session.empty()
            ):
                return session
        return None

    @staticmethod
    def _key(*, workspace_id: str, device_session_id: str, media_session_id: str) -> str:
        return f"{workspace_id}:{device_session_id}:{media_session_id}"

    @staticmethod
    def _event(
        *,
        event_type: str,
        workspace_id: str,
        device_session_id: str,
        media_session_id: str,
        sender: MediaSignalParticipant | None = None,
        sdp: str | None = None,
        candidate: dict[str, Any] | None = None,
        reason: str | None = None,
        message: str | None = None,
        recoverable: bool | None = None,
    ) -> MediaSignalEvent:
        return MediaSignalEvent(
            type=event_type,
            workspace_id=workspace_id,
            device_session_id=device_session_id,
            media_session_id=media_session_id,
            sender=sender,
            sdp=sdp,
            candidate=candidate,
            reason=reason,
            message=message,
            recoverable=recoverable,
            ice_servers=[],
            created_at_epoch=time.time(),
        )


_registry = WebRTCSignalingRegistry()


def get_webrtc_signaling_registry() -> WebRTCSignalingRegistry:
    return _registry


__all__ = [
    "MAX_PENDING_WEBRTC_SIGNAL_EVENTS_PER_PEER",
    "MAX_WEBRTC_SIGNAL_MESSAGE_BYTES",
    "WebRTCSignalingRegistry",
    "WebRTCSignalingRegistryError",
    "get_webrtc_signaling_registry",
]
