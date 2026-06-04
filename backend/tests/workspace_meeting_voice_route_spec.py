from __future__ import annotations

import base64
import importlib.util
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.models.meeting_voice import MeetingVoiceTurnResponse


def _load_meeting_voice_module():
    module_path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "routes"
        / "core"
        / "workspace"
        / "meeting_voice.py"
    )
    spec = importlib.util.spec_from_file_location(
        "meeting_voice_route_under_test",
        module_path,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _audio_base64() -> str:
    return base64.b64encode(b"RIFF....WAVE").decode("ascii")


def test_meeting_voice_route_returns_terminal_response(monkeypatch) -> None:
    meeting_voice = _load_meeting_voice_module()

    class _FakeVoiceService:
        async def submit_voice_turn(self, **kwargs):
            assert kwargs["workspace_id"] == "ws_voice"
            assert kwargs["meeting_id"] == "mtg_voice"
            assert kwargs["request"].client_turn_id == "turn_1"
            return MeetingVoiceTurnResponse(
                status="ignored_empty_transcript",
                transcript="",
                reason="empty_transcript",
            )

    monkeypatch.setattr(meeting_voice, "MeetingVoiceIngressService", _FakeVoiceService)
    app = FastAPI()
    app.include_router(meeting_voice.router, prefix="/api/v1/workspaces")
    app.dependency_overrides[meeting_voice.get_workspace] = lambda: SimpleNamespace(
        id="ws_voice"
    )
    app.dependency_overrides[meeting_voice.get_orchestrator] = lambda: SimpleNamespace()
    app.dependency_overrides[meeting_voice.get_store] = lambda: SimpleNamespace()

    response = TestClient(app).post(
        "/api/v1/workspaces/ws_voice/meetings/mtg_voice/voice-turns",
        json={
            "client_turn_id": "turn_1",
            "audio_base64": _audio_base64(),
            "mime_type": "audio/webm",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ignored_empty_transcript"
