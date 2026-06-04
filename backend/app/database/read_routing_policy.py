"""Allowlist policy for explicit PostgreSQL read-only routing."""

from __future__ import annotations

from typing import Iterable


READONLY_SMOKE_ROUTE_ID = "postgres_ha_readiness_report.readonly_probe"

BASE_READONLY_ROUTE_IDS = frozenset({READONLY_SMOKE_ROUTE_ID})

FORBIDDEN_ROUTE_IDS = frozenset(
    {
        "task.claim",
        "runner.heartbeat",
        "migration.apply",
        "capability_pack.install",
        "queue.admission",
        "job_status.mutate",
    }
)

FORBIDDEN_ROUTE_PREFIXES = (
    "task.",
    "runner.",
    "migration.",
    "capability_pack.",
    "queue.",
    "lock.",
    "advisory_lock.",
)


def _normalize_route_id(route_id: str) -> str:
    return str(route_id or "").strip()


def build_readonly_route_ids(
    additional_route_ids: Iterable[str] | None = None,
) -> frozenset[str]:
    """Build the explicit read-only route allowlist for a rollout batch."""

    route_ids = set(BASE_READONLY_ROUTE_IDS)
    for route_id in additional_route_ids or ():
        normalized = _normalize_route_id(route_id)
        if normalized:
            route_ids.add(normalized)
    return frozenset(route_ids)


def is_readonly_route_allowed(
    route_id: str,
    *,
    additional_route_ids: Iterable[str] | None = None,
) -> bool:
    """Return whether a route may use the read-only PostgreSQL DSN."""

    normalized = _normalize_route_id(route_id)
    if not normalized:
        return False
    if normalized in FORBIDDEN_ROUTE_IDS:
        return False
    if normalized.startswith(FORBIDDEN_ROUTE_PREFIXES):
        return False
    return normalized in build_readonly_route_ids(additional_route_ids)


def require_readonly_route_allowed(
    route_id: str,
    *,
    additional_route_ids: Iterable[str] | None = None,
) -> str:
    """Return the normalized route id or raise when read-only routing is blocked."""

    normalized = _normalize_route_id(route_id)
    if not is_readonly_route_allowed(
        normalized,
        additional_route_ids=additional_route_ids,
    ):
        raise ValueError(
            f"Read-only PostgreSQL routing is not allowed for route: "
            f"{normalized or '<empty>'}"
        )
    return normalized
