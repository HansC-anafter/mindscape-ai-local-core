"""
Mindscape Cloud Integration endpoint resolver.

Provides a neutral resolver layer so call sites do not hardcode legacy env names.
"""

from __future__ import annotations

import os
from typing import Optional


_API_BASE_ENV_KEYS: tuple[str, ...] = (
    "MINDSCAPE_CLOUD_INTEGRATION_API_BASE",
    "MINDSCAPE_CLOUD_GENERATION_API_BASE",  # transitional alias
    "CLOUD_PROVIDER_API_BASE",
    "SITE_HUB_API_BASE",  # legacy alias
)


def get_cloud_integration_api_base() -> Optional[str]:
    """
    Resolve cloud-integration API base URL from supported aliases.
    Returns None when not configured.
    """
    for key in _API_BASE_ENV_KEYS:
        value = os.getenv(key)
        if value:
            return value.rstrip("/")
    return None


def is_cloud_mode_enabled() -> bool:
    """Cloud mode is enabled when a cloud-integration API base is configured."""
    return bool(get_cloud_integration_api_base())
