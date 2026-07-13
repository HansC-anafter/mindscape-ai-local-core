"""VM-wide browser cold-start headroom and spacing admission."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Mapping

from .lease_keys import build_resource_lease_key
from .leases import ResourceLeaseStore

DEFAULT_BROWSER_STARTUP_SPACING_SECONDS = 30
MIN_BROWSER_STARTUP_SPACING_SECONDS = 5
MAX_BROWSER_STARTUP_SPACING_SECONDS = 300
BROWSER_STARTUP_LEASE_KEY = build_resource_lease_key(
    "browser_startup",
    "docker_vm",
)


@dataclass(frozen=True)
class BrowserStartupDecision:
    allow: bool
    reason: str | None
    requested_bytes: int
    request_source: str | None
    spacing_seconds: int


def _positive_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def resolve_browser_startup_request_bytes(
    requirements: Any,
    node_snapshot: Mapping[str, Any],
) -> tuple[int, str] | None:
    explicit_mb = _positive_int(
        getattr(requirements, "browser_startup_memory_mb", 0)
    )
    if explicit_mb > 0:
        return explicit_mb * 1024 * 1024, "playbook_startup_profile"
    return None


def resolve_browser_startup_spacing_seconds(
    requirements: Any,
    *,
    environ: Mapping[str, str] | None = None,
) -> int:
    explicit = _positive_int(
        getattr(requirements, "browser_startup_spacing_seconds", 0)
    )
    source = environ if environ is not None else os.environ
    configured = _positive_int(
        source.get("LOCAL_CORE_RUNNER_BROWSER_STARTUP_SPACING_SECONDS")
    )
    value = explicit or configured or DEFAULT_BROWSER_STARTUP_SPACING_SECONDS
    return max(
        MIN_BROWSER_STARTUP_SPACING_SECONDS,
        min(value, MAX_BROWSER_STARTUP_SPACING_SECONDS),
    )


async def acquire_browser_startup_gate(
    *,
    requirements: Any,
    node_snapshot: Mapping[str, Any],
    lease_store: ResourceLeaseStore,
    owner_id: str,
) -> BrowserStartupDecision:
    spacing_seconds = resolve_browser_startup_spacing_seconds(requirements)
    request = resolve_browser_startup_request_bytes(requirements, node_snapshot)
    requested_bytes, request_source = (
        request if request is not None else (0, "unmeasured_spacing_only")
    )
    available_bytes = _positive_int(node_snapshot.get("available_bytes"))
    if requested_bytes > 0 and available_bytes < requested_bytes:
        return BrowserStartupDecision(
            False,
            "browser_startup_headroom_unavailable",
            requested_bytes,
            request_source,
            spacing_seconds,
        )
    acquired = await lease_store.acquire(
        BROWSER_STARTUP_LEASE_KEY,
        owner_id,
        spacing_seconds,
    )
    if not acquired:
        return BrowserStartupDecision(
            False,
            "browser_startup_spacing_active",
            requested_bytes,
            request_source,
            spacing_seconds,
        )
    return BrowserStartupDecision(
        True,
        None,
        requested_bytes,
        request_source,
        spacing_seconds,
    )


__all__ = [
    "BROWSER_STARTUP_LEASE_KEY",
    "BrowserStartupDecision",
    "acquire_browser_startup_gate",
    "resolve_browser_startup_request_bytes",
    "resolve_browser_startup_spacing_seconds",
]
