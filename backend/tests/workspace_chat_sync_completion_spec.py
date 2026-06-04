import asyncio

import pytest

from backend.features.workspace.chat.sync_completion import (
    SYNC_CHAT_TIMEOUT_ERROR_CODE,
    resolve_sync_display_thread_id,
    run_sync_chat_with_timeout,
)


@pytest.mark.asyncio
async def test_sync_chat_completion_returns_completed_result():
    async def complete_immediately():
        return {"status": "completed"}

    result = await run_sync_chat_with_timeout(
        complete_immediately(),
        timeout_seconds=1.0,
    )

    assert result.completed is True
    assert result.timed_out is False
    assert result.value == {"status": "completed"}
    assert result.error_code is None


@pytest.mark.asyncio
async def test_sync_chat_completion_times_out_and_cancels_awaitable():
    cancelled = False

    async def slow_operation():
        nonlocal cancelled
        try:
            await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            cancelled = True
            raise

    result = await run_sync_chat_with_timeout(
        slow_operation(),
        timeout_seconds=0.01,
    )

    assert result.completed is False
    assert result.timed_out is True
    assert result.error_code == SYNC_CHAT_TIMEOUT_ERROR_CODE
    assert "exceeded 0.01 seconds" in (result.error_message or "")
    assert cancelled is True


@pytest.mark.asyncio
async def test_sync_display_thread_id_uses_explicit_request_thread():
    class Request:
        thread_id = "thread-explicit"

    resolved = await resolve_sync_display_thread_id(
        request=Request(),
        workspace_id="workspace-1",
        store=object(),
    )

    assert resolved == "thread-explicit"


@pytest.mark.asyncio
async def test_sync_display_thread_id_uses_default_thread_when_request_has_none():
    class Request:
        thread_id = None

    class Thread:
        id = "thread-default"

    class ConversationThreads:
        def get_default_thread(self, workspace_id):
            assert workspace_id == "workspace-1"
            return Thread()

    class Store:
        conversation_threads = ConversationThreads()

    resolved = await resolve_sync_display_thread_id(
        request=Request(),
        workspace_id="workspace-1",
        store=Store(),
    )

    assert resolved == "thread-default"
