"""Bounded completion helpers for synchronous workspace chat requests."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Optional


DEFAULT_SYNC_COMPLETION_TIMEOUT_SECONDS = 120.0
SYNC_CHAT_TIMEOUT_ERROR_CODE = "workspace_chat_sync_timeout"


@dataclass(frozen=True)
class SyncChatCompletionResult:
    completed: bool
    timed_out: bool
    value: Any = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None


async def run_sync_chat_with_timeout(
    awaitable: Awaitable[Any],
    *,
    timeout_seconds: float = DEFAULT_SYNC_COMPLETION_TIMEOUT_SECONDS,
) -> SyncChatCompletionResult:
    """Run a synchronous chat awaitable with a hard backend wait bound."""
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")

    try:
        value = await asyncio.wait_for(awaitable, timeout=timeout_seconds)
    except asyncio.TimeoutError:
        timeout_label = f"{timeout_seconds:g}"
        return SyncChatCompletionResult(
            completed=False,
            timed_out=True,
            error_code=SYNC_CHAT_TIMEOUT_ERROR_CODE,
            error_message=(
                "Workspace chat sync completion exceeded "
                f"{timeout_label} seconds."
            ),
        )

    return SyncChatCompletionResult(
        completed=True,
        timed_out=False,
        value=value,
    )


async def resolve_sync_display_thread_id(
    *,
    request: Any,
    workspace_id: str,
    store: Any,
) -> str:
    """Resolve the thread used for synchronous display event fetches."""
    requested_thread_id = str(getattr(request, "thread_id", "") or "").strip()
    if requested_thread_id:
        return requested_thread_id

    from .streaming.chat_session_setup import get_or_create_default_thread

    return await asyncio.to_thread(get_or_create_default_thread, workspace_id, store)
