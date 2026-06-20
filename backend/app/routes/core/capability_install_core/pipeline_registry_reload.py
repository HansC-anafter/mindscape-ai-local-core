"""Capability registry reload helpers for install pipeline."""

from __future__ import annotations

from typing import Awaitable, Callable, TypeVar


T = TypeVar("T")
RunInThreadpool = Callable[..., Awaitable[T]]


async def reload_capability_registry_modules(
    *,
    run_in_threadpool_func: RunInThreadpool,
) -> None:
    """Reload both supported capability registry module identities."""
    from app.services.capability_registry import load_capabilities as load_app_capabilities

    await run_in_threadpool_func(load_app_capabilities, reset=True)

    try:
        from backend.app.services.capability_registry import (
            load_capabilities as load_backend_capabilities,
        )
    except Exception:
        return

    if load_backend_capabilities is not load_app_capabilities:
        await run_in_threadpool_func(load_backend_capabilities, reset=True)
