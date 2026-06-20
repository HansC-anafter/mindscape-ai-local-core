import asyncio
import json

from backend.features.workspace.chat.streaming.llm_streaming import stream_openai_response
from backend.features.workspace.chat.streaming.provider_streaming import (
    extract_sse_chunk_content,
)


class FakeStreamingProvider:
    async def chat_completion_stream(self, *, messages, model, temperature, max_tokens):
        assert messages == [{"role": "user", "content": "hello"}]
        assert model == "gpt-test"
        assert temperature == 0.7
        assert max_tokens > 0
        yield "Hel"
        yield "lo"


class UnsupportedProvider:
    pass


async def _collect_events(provider):
    return [
        event
        async for event in stream_openai_response(
            provider,
            [{"role": "user", "content": "hello"}],
            "gpt-test",
        )
    ]


def _decode_event(event: str):
    assert event.startswith("data: ")
    return json.loads(event[6:].strip())


def test_openai_provider_streaming_wrapper_yields_chunk_events():
    events = asyncio.run(_collect_events(FakeStreamingProvider()))

    assert [_decode_event(event)["content"] for event in events] == ["Hel", "lo"]
    assert [extract_sse_chunk_content(event) for event in events] == ["Hel", "lo"]


def test_openai_provider_streaming_wrapper_reports_missing_stream_support():
    events = asyncio.run(_collect_events(UnsupportedProvider()))

    assert len(events) == 1
    payload = _decode_event(events[0])
    assert payload == {
        "type": "error",
        "message": "Selected registry provider does not support chat_completion_stream",
    }
    assert extract_sse_chunk_content(events[0]) is None


def test_extract_sse_chunk_content_ignores_non_chunk_events():
    assert extract_sse_chunk_content("not-sse") is None
    assert extract_sse_chunk_content("data: {bad json}\n\n") is None
    assert extract_sse_chunk_content('data: {"type": "complete"}\n\n') is None
