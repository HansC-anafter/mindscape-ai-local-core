from __future__ import annotations

import pytest

from backend.app.services.orchestration.meeting.voice_session_registry import (
    MEETING_VOICE_SESSION_TTL_SECONDS,
    MeetingVoiceSessionRegistry,
    MeetingVoiceSessionRegistryError,
)


def test_registry_rejects_duplicate_active_session() -> None:
    registry = MeetingVoiceSessionRegistry()
    first = registry.connect(
        workspace_id="ws_voice",
        meeting_id="mtg_voice",
        client_session_id="session_1",
        websocket=object(),
    )

    assert first.state == "idle"
    with pytest.raises(MeetingVoiceSessionRegistryError) as exc_info:
        registry.connect(
            workspace_id="ws_voice",
            meeting_id="mtg_voice",
            client_session_id="session_1",
            websocket=object(),
        )

    assert exc_info.value.reason == "duplicate_active_session"
    assert registry.active_count() == 1


def test_registry_close_removes_entry() -> None:
    registry = MeetingVoiceSessionRegistry()
    entry = registry.connect(
        workspace_id="ws_voice",
        meeting_id="mtg_voice",
        client_session_id="session_1",
        websocket=object(),
    )

    registry.close(entry)

    assert registry.active_count() == 0
    assert (
        registry.get(
            workspace_id="ws_voice",
            meeting_id="mtg_voice",
            client_session_id="session_1",
        )
        is None
    )


def test_registry_cleans_expired_entries() -> None:
    registry = MeetingVoiceSessionRegistry()
    entry = registry.connect(
        workspace_id="ws_voice",
        meeting_id="mtg_voice",
        client_session_id="session_1",
        websocket=object(),
    )

    removed = registry.cleanup_expired(
        now_epoch=entry.updated_at_epoch + MEETING_VOICE_SESSION_TTL_SECONDS + 1,
    )

    assert removed == 1
    assert registry.active_count() == 0
