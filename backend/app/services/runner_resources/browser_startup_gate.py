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
DEFAULT_BROWSER_STARTUP_MAX_PARALLEL = 7
MAX_BROWSER_STARTUP_MAX_PARALLEL = 7
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
    slot_count: int
    slot_index: int | None
    lease_key: str | None


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


def resolve_browser_startup_slot_count(
    requirements: Any,
    node_snapshot: Mapping[str, Any],
    *,
    environ: Mapping[str, str] | None = None,
) -> int:
    """Resolve bounded VM-wide startup slots from measured byte headroom.

    The node budget reserves measured steady-state bytes for the complete task
    lifetime. These short-lived slots independently guard the transient startup
    peak and prevent a same-second launch stampede; they must not collapse every
    independently reserved browser task into one global serial lane.
    """
    source = environ if environ is not None else os.environ
    configured = _positive_int(
        source.get("LOCAL_CORE_RUNNER_BROWSER_STARTUP_MAX_PARALLEL")
    )
    max_parallel = max(
        1,
        min(
            configured or DEFAULT_BROWSER_STARTUP_MAX_PARALLEL,
            MAX_BROWSER_STARTUP_MAX_PARALLEL,
        ),
    )
    request = resolve_browser_startup_request_bytes(requirements, node_snapshot)
    if request is None:
        return 1
    requested_bytes, _request_source = request
    available_bytes = _positive_int(node_snapshot.get("available_bytes"))
    if requested_bytes <= 0 or available_bytes < requested_bytes:
        return 0
    return max(1, min(max_parallel, available_bytes // requested_bytes))


def browser_startup_slot_lease_key(slot_index: int) -> str:
    normalized_index = max(0, int(slot_index))
    if normalized_index == 0:
        # Preserve the legacy key as slot zero so mixed-version blue/green
        # promotion continues to observe the old global spacing lease.
        return BROWSER_STARTUP_LEASE_KEY
    return build_resource_lease_key(
        "browser_startup",
        f"docker_vm_slot_{normalized_index + 1}",
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
    slot_count = resolve_browser_startup_slot_count(
        requirements,
        node_snapshot,
    )
    if requested_bytes > 0 and available_bytes < requested_bytes:
        return BrowserStartupDecision(
            False,
            "browser_startup_headroom_unavailable",
            requested_bytes,
            request_source,
            spacing_seconds,
            0,
            None,
            None,
        )
    # Larger startup requests can use only the low-index prefix of this
    # nested slot set, while smaller requests can also use higher indexes.
    # Prefer the highest eligible index so small requests do not starve large
    # requests by consuming their scarce shared prefix first.
    for slot_index in reversed(range(slot_count)):
        lease_key = browser_startup_slot_lease_key(slot_index)
        acquired = await lease_store.acquire(
            lease_key,
            owner_id,
            spacing_seconds,
        )
        if acquired:
            return BrowserStartupDecision(
                True,
                None,
                requested_bytes,
                request_source,
                spacing_seconds,
                slot_count,
                slot_index,
                lease_key,
            )
    return BrowserStartupDecision(
        False,
        "browser_startup_spacing_active",
        requested_bytes,
        request_source,
        spacing_seconds,
        slot_count,
        None,
        None,
    )


__all__ = [
    "BROWSER_STARTUP_LEASE_KEY",
    "BrowserStartupDecision",
    "acquire_browser_startup_gate",
    "browser_startup_slot_lease_key",
    "resolve_browser_startup_request_bytes",
    "resolve_browser_startup_slot_count",
    "resolve_browser_startup_spacing_seconds",
]
