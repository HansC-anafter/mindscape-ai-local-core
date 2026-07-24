from __future__ import annotations

import asyncio
import base64

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.routes.core import host_services
from backend.app.services.host_services import whisper_proxy
from backend.app.services.host_services.whisper_proxy import (
    WhisperTranscriptionRequest,
    WhisperTranscriptionResult,
    WhisperTranscriptionUnavailable,
    normalize_whisper_language,
    transcribe_whisper_audio,
)


def _audio_payload() -> str:
    return base64.b64encode(b"RIFF....WAVE").decode("ascii")


def test_host_services_router_adds_stt_transcribe_without_stt_health_route() -> None:
    paths = {route.path for route in host_services.router.routes}

    assert "/api/v1/host/services/stt/transcribe" in paths
    assert "/api/v1/host/services/stt/health" not in paths


def test_stt_transcribe_route_returns_json(monkeypatch) -> None:
    async def _fake_transcribe(
        payload: WhisperTranscriptionRequest,
    ) -> WhisperTranscriptionResult:
        assert payload.audio_base64 == _audio_payload()
        return WhisperTranscriptionResult(
            text="start the meeting",
            segments=[],
            language="en",
            duration=1.25,
        )

    monkeypatch.setattr(host_services, "transcribe_whisper_audio", _fake_transcribe)
    app = FastAPI()
    app.include_router(host_services.router)

    response = TestClient(app).post(
        "/api/v1/host/services/stt/transcribe",
        json={"audio_base64": _audio_payload(), "language": "auto"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "text": "start the meeting",
        "segments": [],
        "language": "en",
        "duration": 1.25,
    }


def test_stt_transcribe_route_returns_structured_unavailable(monkeypatch) -> None:
    async def _fake_transcribe(
        payload: WhisperTranscriptionRequest,
    ) -> WhisperTranscriptionResult:
        raise WhisperTranscriptionUnavailable(
            reason="stt_unreachable",
            error="name resolution failed",
        )

    monkeypatch.setattr(host_services, "transcribe_whisper_audio", _fake_transcribe)
    app = FastAPI()
    app.include_router(host_services.router)

    response = TestClient(app).post(
        "/api/v1/host/services/stt/transcribe",
        json={"audio_base64": _audio_payload(), "language": "auto"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == {
        "reason": "stt_unreachable",
        "error": "name resolution failed",
    }


def test_stt_transcribe_rejects_invalid_base64() -> None:
    app = FastAPI()
    app.include_router(host_services.router)

    response = TestClient(app).post(
        "/api/v1/host/services/stt/transcribe",
        json={"audio_base64": "not base64", "language": "auto"},
    )

    assert response.status_code == 422


def test_transcribe_whisper_audio_posts_sidecar_payload(monkeypatch) -> None:
    captured = {}

    class _FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            return {
                "text": "hello",
                "segments": [{"start": 0, "end": 1, "text": "hello"}],
                "language": "en",
                "duration": 1.0,
            }

    class _FakeClient:
        def __init__(self, timeout: float) -> None:
            captured["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, endpoint: str, json: dict) -> _FakeResponse:
            captured["endpoint"] = endpoint
            captured["json"] = json
            return _FakeResponse()

    monkeypatch.setattr(whisper_proxy.httpx, "AsyncClient", _FakeClient)

    result = asyncio.run(
        transcribe_whisper_audio(
            WhisperTranscriptionRequest(audio_base64=_audio_payload(), language="auto"),
            base_url="http://whisper.local",
        )
    )

    assert result.text == "hello"
    assert captured == {
        "timeout": 600.0,
        "endpoint": "http://whisper.local/transcribe",
        "json": {
            "audio": _audio_payload(),
            "language": "auto",
            "task": "transcribe",
            "model": "openai/whisper-small",
            "device": "cpu",
        },
    }


def test_normalize_whisper_language_maps_product_locales_to_model_ids() -> None:
    assert normalize_whisper_language("zh-TW") == "zh"
    assert normalize_whisper_language("zh_Hant_TW") == "zh"
    assert normalize_whisper_language("en-US") == "en"
    assert normalize_whisper_language("yue-HK") == "yue"
    assert normalize_whisper_language("auto") == "auto"
    assert normalize_whisper_language(None) == "auto"


def test_transcribe_whisper_audio_normalizes_bcp47_language(monkeypatch) -> None:
    captured = {}

    class _FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            return {"text": "開始練習", "segments": [], "language": "zh", "duration": 1.0}

    class _FakeClient:
        def __init__(self, timeout: float) -> None:
            captured["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, endpoint: str, json: dict) -> _FakeResponse:
            captured["language"] = json["language"]
            return _FakeResponse()

    monkeypatch.setattr(whisper_proxy.httpx, "AsyncClient", _FakeClient)

    result = asyncio.run(
        transcribe_whisper_audio(
            WhisperTranscriptionRequest(
                audio_base64=_audio_payload(),
                language="zh-TW",
            ),
            base_url="http://whisper.local",
        )
    )

    assert result.text == "開始練習"
    assert captured["language"] == "zh"
