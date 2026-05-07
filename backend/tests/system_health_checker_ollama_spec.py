import json
import urllib.request

import pytest

from backend.app.services.system_health_checker import SystemHealthChecker


class _FakeOllamaResponse:
    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self._payload).encode("utf-8")


def test_ollama_health_accepts_available_local_model(monkeypatch):
    calls = []

    def fake_urlopen(url, timeout):
        calls.append((url, timeout))
        return _FakeOllamaResponse({
            "models": [
                {"name": "qwen2.5:7b", "model": "qwen2.5:7b"},
                {"name": "gemma3:4b", "model": "gemma3:4b"},
            ]
        })

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    checker = object.__new__(SystemHealthChecker)
    issues = []

    status = checker._check_ollama_configuration(
        "http://host.docker.internal:11434/",
        "ollama/qwen2.5:7b",
        issues,
    )

    assert status["configured"] is True
    assert status["available"] is True
    assert status["provider"] == "ollama"
    assert status["model"] == "qwen2.5:7b"
    assert issues == []
    assert calls == [("http://host.docker.internal:11434/api/tags", 5)]


def test_ollama_health_reports_missing_selected_model(monkeypatch):
    def fake_urlopen(url, timeout):
        return _FakeOllamaResponse({
            "models": [
                {"name": "gemma3:4b", "model": "gemma3:4b"},
            ]
        })

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    checker = object.__new__(SystemHealthChecker)
    issues = []

    status = checker._check_ollama_configuration(
        "http://host.docker.internal:11434",
        "qwen2.5:7b",
        issues,
    )

    assert status["configured"] is True
    assert status["available"] is False
    assert status["model"] == "qwen2.5:7b"
    assert [issue.type for issue in issues] == ["ollama_model_missing"]


class _OptionalOCRClient:
    service_url = "http://ocr-service:8001"

    async def check_health(self):
        raise AssertionError("optional default OCR service must not be probed")


class _RequiredOCRClient:
    service_url = "http://ocr-service:8001"

    async def check_health(self):
        return {"status": "unavailable", "error": "[Errno -2] Name or service not known"}


@pytest.mark.asyncio
async def test_default_ocr_service_is_disabled_when_optional(monkeypatch):
    monkeypatch.delenv("OCR_SERVICE_URL", raising=False)
    monkeypatch.delenv("OCR_SERVICE_REQUIRED", raising=False)
    monkeypatch.setattr(
        "backend.app.capabilities.core_files.services.ocr_client.get_ocr_client",
        lambda: _OptionalOCRClient(),
    )
    checker = object.__new__(SystemHealthChecker)
    issues = []

    status = await checker._check_ocr_service(issues)

    assert status["status"] == "disabled"
    assert status["available"] is False
    assert status["required"] is False
    assert issues == []


@pytest.mark.asyncio
async def test_default_ocr_service_warns_when_required(monkeypatch):
    monkeypatch.delenv("OCR_SERVICE_URL", raising=False)
    monkeypatch.setenv("OCR_SERVICE_REQUIRED", "true")
    monkeypatch.setattr(
        "backend.app.capabilities.core_files.services.ocr_client.get_ocr_client",
        lambda: _RequiredOCRClient(),
    )
    checker = object.__new__(SystemHealthChecker)
    issues = []

    status = await checker._check_ocr_service(issues)

    assert status["status"] == "unhealthy"
    assert status["available"] is False
    assert [issue.type for issue in issues] == ["ocr_service_unhealthy"]
