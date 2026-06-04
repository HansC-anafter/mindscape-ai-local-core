"""In-memory registry for Meeting Engine realtime voice sessions."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from backend.app.models.meeting_voice_session import MeetingVoiceSessionState


MEETING_VOICE_SESSION_TTL_SECONDS = 300


class MeetingVoiceSessionRegistryError(Exception):
    """Registry-level voice session error."""

    def __init__(self, *, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message


@dataclass
class MeetingVoiceSessionEntry:
    """One active in-memory voice session."""

    key: str
    workspace_id: str
    meeting_id: str
    client_session_id: str
    websocket: Any
    state: MeetingVoiceSessionState
    created_at_epoch: float
    updated_at_epoch: float

    def expired(self, now_epoch: float) -> bool:
        return now_epoch - self.updated_at_epoch > MEETING_VOICE_SESSION_TTL_SECONDS


class MeetingVoiceSessionRegistry:
    """Process-local registry with one active socket per session key."""

    def __init__(self) -> None:
        self._entries: dict[str, MeetingVoiceSessionEntry] = {}

    @staticmethod
    def build_key(
        *,
        workspace_id: str,
        meeting_id: str,
        client_session_id: str,
    ) -> str:
        return f"{workspace_id}:{meeting_id}:{client_session_id}"

    def connect(
        self,
        *,
        workspace_id: str,
        meeting_id: str,
        client_session_id: str,
        websocket: Any,
    ) -> MeetingVoiceSessionEntry:
        now = time.time()
        self.cleanup_expired(now_epoch=now)
        key = self.build_key(
            workspace_id=workspace_id,
            meeting_id=meeting_id,
            client_session_id=client_session_id,
        )
        existing = self._entries.get(key)
        if existing is not None and existing.state != "closed":
            raise MeetingVoiceSessionRegistryError(
                reason="duplicate_active_session",
                message="A realtime voice session is already active for this meeting.",
            )
        entry = MeetingVoiceSessionEntry(
            key=key,
            workspace_id=workspace_id,
            meeting_id=meeting_id,
            client_session_id=client_session_id,
            websocket=websocket,
            state="idle",
            created_at_epoch=now,
            updated_at_epoch=now,
        )
        self._entries[key] = entry
        return entry

    def get(
        self,
        *,
        workspace_id: str,
        meeting_id: str,
        client_session_id: str,
    ) -> MeetingVoiceSessionEntry | None:
        key = self.build_key(
            workspace_id=workspace_id,
            meeting_id=meeting_id,
            client_session_id=client_session_id,
        )
        return self._entries.get(key)

    def update_state(
        self,
        entry: MeetingVoiceSessionEntry,
        state: MeetingVoiceSessionState,
    ) -> MeetingVoiceSessionEntry:
        entry.state = state
        entry.updated_at_epoch = time.time()
        self._entries[entry.key] = entry
        return entry

    def close(self, entry: MeetingVoiceSessionEntry) -> None:
        entry.state = "closed"
        entry.updated_at_epoch = time.time()
        self._entries.pop(entry.key, None)

    def cleanup_expired(self, *, now_epoch: float | None = None) -> int:
        now = time.time() if now_epoch is None else now_epoch
        expired_keys = [
            key for key, entry in self._entries.items() if entry.expired(now)
        ]
        for key in expired_keys:
            self._entries.pop(key, None)
        return len(expired_keys)

    def active_count(self) -> int:
        self.cleanup_expired()
        return len(self._entries)


_registry = MeetingVoiceSessionRegistry()


def get_meeting_voice_session_registry() -> MeetingVoiceSessionRegistry:
    return _registry


__all__ = [
    "MEETING_VOICE_SESSION_TTL_SECONDS",
    "MeetingVoiceSessionEntry",
    "MeetingVoiceSessionRegistry",
    "MeetingVoiceSessionRegistryError",
    "get_meeting_voice_session_registry",
]
