import pytest

from backend.app.services.conversation.pipeline_meeting import _decompose_agenda


@pytest.mark.asyncio
async def test_basic_decomposition():
    async def fake_generate(messages, model=None):
        return '["research autonomic nerve", "create IG posts", "find images"]'

    result = await _decompose_agenda(
        "Research autonomic nerve studies and create IG posts with images",
        model_name="gemini-2.5-pro",
        llm_generate_fn=fake_generate,
    )
    assert len(result) == 3


@pytest.mark.asyncio
async def test_without_generation_callback_returns_raw_message():
    result = await _decompose_agenda(
        "Do three different tasks for me please now",
        model_name="claude-3",
    )
    assert result == ["Do three different tasks for me please now"]


@pytest.mark.asyncio
async def test_fallback_on_short_input():
    result = await _decompose_agenda("hello")
    assert result == ["hello"]


@pytest.mark.asyncio
async def test_fallback_on_provider_error():
    async def boom(messages, model=None):
        raise RuntimeError("boom")

    result = await _decompose_agenda(
        "Some complex task that should fallback gracefully",
        model_name="test-model",
        llm_generate_fn=boom,
    )
    assert len(result) == 1


@pytest.mark.asyncio
async def test_json_code_block_stripping():
    async def fake_generate(messages, model=None):
        return '```json\n["task A", "task B"]\n```'

    result = await _decompose_agenda(
        "Plan two different things for my project",
        model_name="gemini-pro",
        llm_generate_fn=fake_generate,
    )
    assert len(result) == 2


@pytest.mark.asyncio
async def test_executor_runtime_without_generation_callback_returns_raw_message():
    result = await _decompose_agenda(
        "Research autonomic nervous system studies and create IG posts",
        model_name="gemini-2.5-pro",
        executor_runtime="gemini_cli",
    )

    assert result == [
        "Research autonomic nervous system studies and create IG posts"
    ]
