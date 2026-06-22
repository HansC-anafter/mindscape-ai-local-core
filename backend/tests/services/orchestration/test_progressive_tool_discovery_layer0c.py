from unittest.mock import AsyncMock, patch

import pytest

from backend.tests.services.orchestration.progressive_tool_discovery_test_support import (
    make_engine_stub,
)


@pytest.mark.asyncio
async def test_decomposes_single_item_agenda():
    engine = make_engine_stub(agenda=["single item"])

    with patch(
        "backend.app.services.conversation.pipeline_meeting._decompose_agenda",
        new_callable=AsyncMock,
        return_value=["sub A", "sub B", "sub C"],
    ) as mock_decompose:
        result = await engine._ensure_agenda_decomposed(
            "A message long enough to decompose into sub-tasks"
        )

    assert result is True
    assert engine.session.agenda == ["sub A", "sub B", "sub C"]
    engine.session_store.update.assert_called_once_with(engine.session)
    _, kwargs = mock_decompose.call_args
    assert kwargs["model_name"] == "test-model"
    assert kwargs["executor_runtime"] is None


@pytest.mark.asyncio
async def test_skips_multi_item_agenda():
    engine = make_engine_stub(agenda=["item 1", "item 2", "item 3"])

    result = await engine._ensure_agenda_decomposed(
        "Some long message that would normally trigger decomposition"
    )

    assert result is False
    assert engine.session.agenda == ["item 1", "item 2", "item 3"]
    engine.session_store.update.assert_not_called()


@pytest.mark.asyncio
async def test_skips_short_message():
    engine = make_engine_stub(agenda=["single"])

    result = await engine._ensure_agenda_decomposed("hi")

    assert result is False
    engine.session_store.update.assert_not_called()


@pytest.mark.asyncio
async def test_passes_model_name():
    engine = make_engine_stub(
        agenda=["single"],
        model_name="gemini-2.5-pro",
    )

    with patch(
        "backend.app.services.conversation.pipeline_meeting._decompose_agenda",
        new_callable=AsyncMock,
        return_value=["x", "y"],
    ) as mock_decompose:
        await engine._ensure_agenda_decomposed(
            "A sufficiently long message for decomposition"
        )

    mock_decompose.assert_awaited_once()
    _, kwargs = mock_decompose.call_args
    assert kwargs["model_name"] == "gemini-2.5-pro"


@pytest.mark.asyncio
async def test_passes_executor_runtime():
    engine = make_engine_stub(
        agenda=["single"],
        model_name="gemini-2.5-pro",
        executor_runtime="gemini_cli",
    )

    with patch(
        "backend.app.services.conversation.pipeline_meeting._decompose_agenda",
        new_callable=AsyncMock,
        return_value=["x", "y"],
    ) as mock_decompose:
        await engine._ensure_agenda_decomposed(
            "A sufficiently long message for decomposition"
        )

    _, kwargs = mock_decompose.call_args
    assert kwargs["executor_runtime"] == "gemini_cli"


@pytest.mark.asyncio
async def test_passes_meeting_generate_fn():
    engine = make_engine_stub(
        agenda=["single"],
        model_name="gpt-5.4",
        executor_runtime="codex_cli",
    )
    engine._generate_text = AsyncMock(return_value='["x", "y"]')

    with patch(
        "backend.app.services.conversation.pipeline_meeting._decompose_agenda",
        new_callable=AsyncMock,
        return_value=["x", "y"],
    ) as mock_decompose:
        await engine._ensure_agenda_decomposed(
            "A sufficiently long message for decomposition"
        )

    _, kwargs = mock_decompose.call_args
    assert kwargs["llm_generate_fn"] is engine._generate_text


@pytest.mark.asyncio
async def test_fallback_single_item_returns_false():
    engine = make_engine_stub(agenda=["single item"])

    with patch(
        "backend.app.services.conversation.pipeline_meeting._decompose_agenda",
        new_callable=AsyncMock,
        return_value=["single item"],
    ):
        result = await engine._ensure_agenda_decomposed(
            "A message that decompose fails to split"
        )

    assert result is False
    engine.session_store.update.assert_not_called()
