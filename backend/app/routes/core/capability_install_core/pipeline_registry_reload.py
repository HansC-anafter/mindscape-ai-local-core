"""Capability registry reload helpers for install pipeline."""

from __future__ import annotations

from typing import Awaitable, Callable, TypeVar


T = TypeVar("T")
RunInThreadpool = Callable[..., Awaitable[T]]


async def reload_capability_registry_modules(
    *,
    capability_code: str,
    run_in_threadpool_func: RunInThreadpool,
) -> None:
    """Reload one installed capability in the canonical shared registry."""
    from app.services.capability_registry import reload_capability

    loaded = await run_in_threadpool_func(reload_capability, capability_code)
    if not loaded:
        raise ValueError(f"capability_manifest_not_found:{capability_code}")
