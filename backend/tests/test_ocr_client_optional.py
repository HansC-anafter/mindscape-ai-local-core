import pytest

from backend.app.capabilities.core_files.services.ocr_client import OCRClient


@pytest.mark.asyncio
async def test_default_ocr_service_url_skips_when_optional(monkeypatch, tmp_path):
    image_path = tmp_path / "ref.jpg"
    image_path.write_bytes(b"not-a-real-image-but-client-should-not-open-it")
    monkeypatch.delenv("OCR_SERVICE_URL", raising=False)
    monkeypatch.delenv("OCR_SERVICE_REQUIRED", raising=False)

    result = await OCRClient().ocr_image(str(image_path))

    assert result["status"] == "disabled"
    assert result["blocks"] == []


@pytest.mark.asyncio
async def test_default_ocr_service_url_is_not_disabled_when_required(monkeypatch):
    monkeypatch.delenv("OCR_SERVICE_URL", raising=False)
    monkeypatch.setenv("OCR_SERVICE_REQUIRED", "true")

    assert OCRClient()._is_optional_default_disabled() is False
