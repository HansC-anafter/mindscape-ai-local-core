import base64
from unittest.mock import patch

import pytest

from backend.app.system_capabilities.core_llm.services.multimodal import (
    _route_cloud_llm,
)


@pytest.mark.asyncio
async def test_route_cloud_llm_anthropic_payload() -> None:
    """Anthropic routing must use image blocks, not image_url blocks."""
    b64_img = base64.b64encode(b"dummy_image_data").decode()
    images = [{"shortcode": "test_img_1", "base64_jpeg": b64_img}]

    with patch("backend.app.shared.llm_utils.call_llm") as mock_call_llm, patch(
        "backend.app.services.system_settings_store.SystemSettingsStore"
    ), patch(
        "backend.app.system_capabilities.core_llm.services.multimodal.os.getenv"
    ):
        mock_call_llm.return_value = {"text": "A description", "usage": {}}

        result = await _route_cloud_llm(
            images,
            "Describe this image",
            "claude-3-5-sonnet-20240620",
            "anthropic",
            0.4,
            "test_ws_123",
        )

    assert result["status"] == "success"

    call_kwargs = mock_call_llm.call_args[1]
    messages = call_kwargs["messages"]
    assert len(messages) == 1

    user_message = messages[0]
    assert user_message["role"] == "user"

    content = user_message["content"]
    assert len(content) == 2
    assert content[0]["type"] == "text"
    assert content[0]["text"] == "Describe this image"
    assert content[1]["type"] == "image"
    assert content[1]["source"]["type"] == "base64"
    assert content[1]["source"]["data"] == b64_img


@pytest.mark.asyncio
async def test_route_cloud_llm_openai_payload() -> None:
    """OpenAI routing must use image_url blocks."""
    b64_img = base64.b64encode(b"dummy_image_data").decode()
    images = [{"shortcode": "test_img_1", "base64_jpeg": b64_img}]

    with patch("backend.app.shared.llm_utils.call_llm") as mock_call_llm, patch(
        "backend.app.services.system_settings_store.SystemSettingsStore"
    ), patch(
        "backend.app.system_capabilities.core_llm.services.multimodal.os.getenv"
    ):
        mock_call_llm.return_value = {"text": "A description", "usage": {}}

        result = await _route_cloud_llm(
            images,
            "Describe this image",
            "gpt-4o",
            "openai",
            0.4,
            "test_ws_123",
        )

    assert result["status"] == "success"

    call_kwargs = mock_call_llm.call_args[1]
    messages = call_kwargs["messages"]
    content = messages[0]["content"]
    assert content[1]["type"] == "image_url"
    assert "url" in content[1]["image_url"]
    assert b64_img in content[1]["image_url"]["url"]


@pytest.mark.asyncio
async def test_route_cloud_llm_passes_max_tokens_and_marks_capture_unsupported() -> None:
    b64_img = base64.b64encode(b"dummy_image_data").decode()
    images = [{"shortcode": "test_img_1", "base64_jpeg": b64_img}]

    with patch("backend.app.shared.llm_utils.call_llm") as mock_call_llm, patch(
        "backend.app.services.system_settings_store.SystemSettingsStore"
    ), patch(
        "backend.app.system_capabilities.core_llm.services.multimodal.os.getenv"
    ):
        mock_call_llm.return_value = {"text": "A description", "usage": {}}

        result = await _route_cloud_llm(
            images,
            "Describe this image",
            "gpt-4o",
            "openai",
            0.4,
            "test_ws_123",
            max_tokens=2048,
            reasoning_trace_mode="capture",
        )

    assert result["status"] == "success"
    assert result["_telemetry"]["reasoning_trace_mode"] == "capture_unsupported_provider"
    call_kwargs = mock_call_llm.call_args[1]
    assert call_kwargs["max_tokens"] == 2048
