"""Shared invalidation for installed capability metadata route caches."""

from __future__ import annotations

import importlib
import logging
from types import ModuleType
from typing import Callable

logger = logging.getLogger(__name__)

_CACHE_STATE_MODULES = (
    "app.routes.core.capability_packs_core.cache_state",
    "backend.app.routes.core.capability_packs_core.cache_state",
)


def _resolve_cache_clearers() -> list[Callable[[], None]]:
    clearers: list[Callable[[], None]] = []
    seen: set[int] = set()
    for module_name in _CACHE_STATE_MODULES:
        try:
            module: ModuleType = importlib.import_module(module_name)
        except Exception:
            logger.debug("Installed capability cache module unavailable: %s", module_name)
            continue
        clearer = getattr(module, "clear_installed_capability_route_cache", None)
        if not callable(clearer):
            continue
        marker = id(clearer)
        if marker in seen:
            continue
        seen.add(marker)
        clearers.append(clearer)
    return clearers


def clear_installed_capability_metadata_caches(
    *,
    reason: str,
    capability_code: str | None = None,
) -> int:
    """Clear all process-local installed capability metadata caches."""

    cleared = 0
    for clearer in _resolve_cache_clearers():
        clearer()
        cleared += 1
    logger.info(
        "Cleared installed capability metadata caches: capability=%s reason=%s modules=%d",
        capability_code or "*",
        reason,
        cleared,
    )
    return cleared
