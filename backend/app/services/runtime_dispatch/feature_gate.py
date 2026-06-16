"""Feature gate helpers for runtime dispatch."""

from __future__ import annotations

import os
from typing import Callable

RUNTIME_DISPATCH_ENABLED_ENV = "RUNTIME_DISPATCH_ENABLED"
_TRUE_VALUES = {"1", "true", "yes", "on", "enabled"}


def is_runtime_dispatch_enabled(
    getenv: Callable[[str, str | None], str | None] = os.getenv,
) -> bool:
    raw = getenv(RUNTIME_DISPATCH_ENABLED_ENV, None)
    if raw is None:
        return False
    return raw.strip().lower() in _TRUE_VALUES


def get_runtime_dispatch_feature_gate() -> dict[str, object]:
    enabled = is_runtime_dispatch_enabled()
    return {
        "enabled": enabled,
        "env_var": RUNTIME_DISPATCH_ENABLED_ENV,
        "default_enabled": False,
        "reason": None if enabled else "runtime_dispatch_disabled",
    }
