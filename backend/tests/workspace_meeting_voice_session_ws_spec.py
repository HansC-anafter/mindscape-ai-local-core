from __future__ import annotations

import base64
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.models.meeting_command import (
    MeetingCommandAcceptResponse,
    MeetingCommandRecord,
    MeetingCommandStatus,
)
from backend.app.models.meeting_voice_session import MeetingVoiceTranscriptCandidate
from backend.app.services.orchestration.meeting.realtime_voice_transcriber import (
    RealtimeVoiceTranscriptionError,
)
from backend.app.services.orchestration.meeting.voice_session_registry import (
    MeetingVoiceSessionRegistry,
)


def _load_meeting_voice_sessions_module():
    module_path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "routes"
        / "core"
        / "workspace"
        / "meeting_voice_sessions.py"
    )
    spec = importlib.util.spec_from_file_location(
        "meeting_voice_sessions_route_under_test",
        module_path,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _audio_base64() -> str:
    return base64.b64encode(b"RIFF....WAVE").decode("ascii")


class _FakeTranscriber:
    def __init__(self) -> None:
        self.submitted = []

    async def transcribe_audio_window(self, *, window):
        return MeetingVoiceTranscriptCandidate(
            client_session_id=window.client_session_id,
            utterance_id=window.utterance_id,
            transcript="Create a practice cue.",
            language="en",
            duration=0.8,
            audio_mime_type="audio/webm",
            audio_byte_count=len(base64.b64decode(window.audio_base64)),
        )

    async def submit_final_transcript(self, **kwargs):
        candidate = kwargs["candidate"]
        self.submitted.append(candidate)
        command = MeetingCommandRecord(
            command_id="cmd_ws_voice",
            workspace_id=kwargs["workspace_id"],
            meeting_id=kwargs["meeting_id"],
            origin_surface="meeting_voice_session",
            actor="user",
            intent_text=candidate.transcript,
            status=MeetingCommandStatus.ACCEPTED,
        )
        return MeetingCommandAcceptResponse(
            workspace_id=kwargs["workspace_id"],
            meeting_id=kwargs["meeting_id"],
            command_id="cmd_ws_voice",
            status=MeetingCommandStatus.ACCEPTED,
            command=command,
        )


class _EmptyTranscriber(_FakeTranscriber):
    async def transcribe_audio_window(self, *, window):
        raise RealtimeVoiceTranscriptionError(
            reason="empty_transcript",
            message="empty",
            recoverable=True,
        )


def _build_app(module, *, registry, transcriber):
    app = FastAPI()
    app.include_router(module.router, prefix="/api/v1/workspaces")
    app.dependency_overrides[module.get_workspace] = lambda: SimpleNamespace(
        id="ws_voice",
        default_locale="zh-TW",
    )
    app.dependency_overrides[module.get_orchestrator] = lambda: SimpleNamespace()
    app.dependency_overrides[module.get_store] = lambda: SimpleNamespace()
    app.dependency_overrides[module.get_meeting_voice_session_registry] = lambda: registry
    app.dependency_overrides[module.get_realtime_voice_transcriber] = lambda: transcriber
    return app


def _session_url(session_id: str = "session_1") -> str:
    return (
        "/api/v1/workspaces/ws_voice/meetings/mtg_voice/"
        f"voice-sessions/{session_id}/stream"
    )


def _receive(ws):
    return json.loads(ws.receive_text())


def test_voice_session_ws_submits_command_only_after_utterance_end() -> None:
    module = _load_meeting_voice_sessions_module()
    registry = MeetingVoiceSessionRegistry()
    transcriber = _FakeTranscriber()
    client = TestClient(_build_app(module, registry=registry, transcriber=transcriber))

    with client.websocket_connect(_session_url()) as ws:
        ws.send_json({"type": "session_start"})
        assert _receive(ws)["type"] == "session_ready"

        ws.send_json(
            {
                "type": "audio_window",
                "utterance_id": "utt_1",
                "audio_base64": _audio_base64(),
                "mime_type": "audio/webm",
            }
        )
        candidate = _receive(ws)
        assert candidate["type"] == "transcript_candidate"
        assert candidate["transcript"] == "Create a practice cue."
        assert transcriber.submitted == []

        ws.send_json({"type": "utterance_end", "utterance_id": "utt_1"})
        assert _receive(ws)["type"] == "transcript_final"
        submitted = _receive(ws)
        assert submitted["type"] == "command_submitted"
        assert submitted["command_response"]["command_id"] == "cmd_ws_voice"
        assert len(transcriber.submitted) == 1

        ws.send_json({"type": "session_close"})
        assert _receive(ws)["type"] == "session_closed"

    assert registry.active_count() == 0


def test_voice_session_ws_rejects_duplicate_active_session() -> None:
    module = _load_meeting_voice_sessions_module()
    registry = MeetingVoiceSessionRegistry()
    transcriber = _FakeTranscriber()
    client = TestClient(_build_app(module, registry=registry, transcriber=transcriber))

    with client.websocket_connect(_session_url()) as first:
        first.send_json({"type": "session_start"})
        assert _receive(first)["type"] == "session_ready"

        with client.websocket_connect(_session_url()) as second:
            error = _receive(second)
            assert error["type"] == "session_error"
            assert error["reason"] == "duplicate_active_session"
            assert error["recoverable"] is False


def test_voice_session_ws_empty_transcript_is_recoverable_and_no_command() -> None:
    module = _load_meeting_voice_sessions_module()
    registry = MeetingVoiceSessionRegistry()
    transcriber = _EmptyTranscriber()
    client = TestClient(_build_app(module, registry=registry, transcriber=transcriber))

    with client.websocket_connect(_session_url()) as ws:
        ws.send_json({"type": "session_start"})
        assert _receive(ws)["type"] == "session_ready"
        ws.send_json(
            {
                "type": "audio_window",
                "utterance_id": "utt_empty",
                "audio_base64": _audio_base64(),
                "mime_type": "audio/webm",
            }
        )
        error = _receive(ws)
        assert error["type"] == "session_error"
        assert error["reason"] == "empty_transcript"
        assert error["recoverable"] is True
        assert transcriber.submitted == []
