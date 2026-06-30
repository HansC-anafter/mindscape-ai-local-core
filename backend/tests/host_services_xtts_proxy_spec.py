from __future__ import annotations

import asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.routes.core import host_services
from backend.app.services.host_services import xtts_proxy
from backend.app.services.host_services.xtts_proxy import (
    XTTSAudioResult,
    XTTSSynthesisRequest,
    XTTSSynthesisUnavailable,
    normalize_xtts_language,
    synthesize_xtts_audio,
)


def test_host_services_router_only_adds_xtts_tts_route() -> None:
    paths = {route.path for route in host_services.router.routes}

    assert "/api/v1/host/services/xtts/tts" in paths
    assert "/api/v1/host/services/xtts/health" not in paths


def test_xtts_tts_route_returns_audio(monkeypatch) -> None:
    async def _fake_synthesize(payload: XTTSSynthesisRequest) -> XTTSAudioResult:
        assert payload.text == "hello"
        return XTTSAudioResult(audio_bytes=b"RIFF", media_type="audio/wav")

    monkeypatch.setattr(host_services, "synthesize_xtts_audio", _fake_synthesize)
    app = FastAPI()
    app.include_router(host_services.router)

    response = TestClient(app).post(
        "/api/v1/host/services/xtts/tts",
        json={"text": "hello", "language": "zh-cn", "output_format": "wav"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/wav")
    assert response.content == b"RIFF"


def test_xtts_tts_route_returns_structured_unavailable(monkeypatch) -> None:
    async def _fake_synthesize(payload: XTTSSynthesisRequest) -> XTTSAudioResult:
        raise XTTSSynthesisUnavailable(
            reason="xtts_unreachable",
            error="name resolution failed",
        )

    monkeypatch.setattr(host_services, "synthesize_xtts_audio", _fake_synthesize)
    app = FastAPI()
    app.include_router(host_services.router)

    response = TestClient(app).post(
        "/api/v1/host/services/xtts/tts",
        json={"text": "hello", "language": "zh-cn", "output_format": "wav"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == {
        "reason": "xtts_unreachable",
        "error": "name resolution failed",
    }


def test_xtts_tts_route_rejects_overlong_text() -> None:
    app = FastAPI()
    app.include_router(host_services.router)

    response = TestClient(app).post(
        "/api/v1/host/services/xtts/tts",
        json={"text": "x" * 701, "language": "zh-cn", "output_format": "wav"},
    )

    assert response.status_code == 422


def test_normalize_xtts_language_maps_app_locales_to_supported_ids() -> None:
    assert normalize_xtts_language("zh-TW") == "zh-cn"
    assert normalize_xtts_language("zh_Hant") == "zh-cn"
    assert normalize_xtts_language("ja-JP") == "ja"
    assert normalize_xtts_language("en-US") == "en"


def test_synthesize_xtts_audio_posts_bounded_payload(monkeypatch) -> None:
    captured = {}

    class _FakeResponse:
        status_code = 200
        content = b"RIFF"
        headers = {"content-type": "audio/wav"}
        text = ""

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

    monkeypatch.setattr(xtts_proxy.httpx, "AsyncClient", _FakeClient)

    result = asyncio.run(
        synthesize_xtts_audio(
            XTTSSynthesisRequest(
                text="今天的練習完成了。",
                language="zh-TW",
                output_format="wav",
            ),
            base_url="http://xtts.local",
        ),
    )

    assert result.audio_bytes == b"RIFF"
    assert result.media_type == "audio/wav"
    assert captured == {
        "timeout": 180.0,
        "endpoint": "http://xtts.local/tts",
        "json": {
            "text": "今天的練習完成了。",
            "language": "zh-cn",
            "voice_profile_id": None,
            "output_format": "wav",
        },
    }
