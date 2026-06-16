"""Runtime dispatch safety-gate services."""

from .feature_gate import (
    RUNTIME_DISPATCH_ENABLED_ENV,
    get_runtime_dispatch_feature_gate,
    is_runtime_dispatch_enabled,
)

__all__ = [
    "RUNTIME_DISPATCH_ENABLED_ENV",
    "get_runtime_dispatch_feature_gate",
    "is_runtime_dispatch_enabled",
]
