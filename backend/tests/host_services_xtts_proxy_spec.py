from __future__ import annotations

import asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.routes.core import host_services
from backend.app.services.host_services import quality_voice_facade
from backend.app.services.host_services.quality_voice_facade import (
    DEFAULT_QUALITY_VOICE_PROFILE_ID,
    QualityVoiceAudioResult,
    QualityVoiceSynthesisRequest,
    QualityVoiceUnavailable,
    normalize_quality_voice_language,
    synthesize_quality_voice_audio,
)


def test_host_services_router_keeps_legacy_tts_path_only() -> None:
    paths = {route.path for route in host_services.router.routes}

    assert "/api/v1/host/services/xtts/tts" in paths
    assert "/api/v1/host/services/xtts/health" not in paths


def test_quality_voice_route_returns_audio(monkeypatch) -> None:
    async def _fake_synthesize(
        payload: QualityVoiceSynthesisRequest,
    ) -> QualityVoiceAudioResult:
        assert payload.text == "hello"
        assert payload.voice_profile_id == DEFAULT_QUALITY_VOICE_PROFILE_ID
        return QualityVoiceAudioResult(audio_bytes=b"RIFF", media_type="audio/wav")

    monkeypatch.setattr(
        host_services, "synthesize_quality_voice_audio", _fake_synthesize
    )
    app = FastAPI()
    app.include_router(host_services.router)

    response = TestClient(app).post(
        "/api/v1/host/services/xtts/tts",
        json={"text": "hello", "language": "zh-cn", "output_format": "wav"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/wav")
    assert response.content == b"RIFF"


def test_quality_voice_route_returns_structured_unavailable(monkeypatch) -> None:
    async def _fake_synthesize(
        payload: QualityVoiceSynthesisRequest,
    ) -> QualityVoiceAudioResult:
        raise QualityVoiceUnavailable(
            reason="qwen_quality_voice_unreachable",
            error="name resolution failed",
        )

    monkeypatch.setattr(
        host_services, "synthesize_quality_voice_audio", _fake_synthesize
    )
    app = FastAPI()
    app.include_router(host_services.router)

    response = TestClient(app).post(
        "/api/v1/host/services/xtts/tts",
        json={"text": "hello", "language": "zh-cn", "output_format": "wav"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == {
        "reason": "qwen_quality_voice_unreachable",
        "error": "name resolution failed",
    }


def test_quality_voice_route_rejects_overlong_text() -> None:
    app = FastAPI()
    app.include_router(host_services.router)

    response = TestClient(app).post(
        "/api/v1/host/services/xtts/tts",
        json={"text": "x" * 701, "language": "zh-cn", "output_format": "wav"},
    )

    assert response.status_code == 422


def test_normalize_quality_voice_language_maps_app_locales() -> None:
    assert normalize_quality_voice_language("zh-TW") == "zh-cn"
    assert normalize_quality_voice_language("zh_Hant") == "zh-cn"
    assert normalize_quality_voice_language("ja-JP") == "ja"
    assert normalize_quality_voice_language("en-US") == "en"


def test_synthesize_quality_voice_audio_posts_selected_profile(monkeypatch) -> None:
    captured = {}

    class _FakeResponse:
        status_code = 200
        content = b"RIFF"
        headers = {"content-type": "audio/wav"}
        text = ""

        @staticmethod
        def json() -> dict:
            return {}

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

    monkeypatch.setattr(quality_voice_facade.httpx, "AsyncClient", _FakeClient)

    result = asyncio.run(
        synthesize_quality_voice_audio(
            QualityVoiceSynthesisRequest(
                text="今天的練習完成了。",
                language="zh-TW",
                output_format="wav",
            ),
            base_url="http://qwen.local",
        ),
    )

    assert result.audio_bytes == b"RIFF"
    assert result.media_type == "audio/wav"
    assert captured == {
        "timeout": 240.0,
        "endpoint": "http://qwen.local/tts",
        "json": {
            "text": "今天的練習完成了。",
            "language": "zh-cn",
            "voice_profile_id": DEFAULT_QUALITY_VOICE_PROFILE_ID,
            "output_format": "wav",
        },
    }
