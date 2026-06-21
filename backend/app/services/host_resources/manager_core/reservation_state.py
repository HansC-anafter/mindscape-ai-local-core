"""Pure reservation state helpers for the host resource manager."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def parse_datetime(value: Any) -> datetime | None:
    """Parse a value into a timezone-aware UTC datetime."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def reservation_is_active(
    reservation: dict[str, Any],
    *,
    now: datetime | None = None,
) -> bool:
    """Return whether a route reservation should count as active."""
    if reservation.get("state") not in {"reserved_waiting", "permitted"}:
        return False
    expires_at = parse_datetime(reservation.get("expires_at"))
    if expires_at and expires_at <= (now or datetime.now(timezone.utc)):
        return False
    return True


def reservation_matches_state_filter(
    reservation: dict[str, Any],
    state_filter: str | None,
) -> bool:
    """Return whether a reservation matches the route-reservation state filter."""
    normalized = str(state_filter or "").strip().lower()
    if not normalized or normalized in {"all", "any"}:
        return True
    if normalized == "active":
        return reservation_is_active(reservation)
    if normalized in {"history", "inactive", "closed"}:
        return not reservation_is_active(reservation)
    return str(reservation.get("state") or "").strip().lower() == normalized


def clamped_reservation_limit(limit: int | None, *, default: int = 100) -> int:
    """Clamp route reservation list limits to the public range."""
    try:
        parsed = int(limit or default)
    except Exception:
        parsed = default
    return max(1, min(parsed, 200))


def reservation_sort_key(reservation: dict[str, Any]) -> datetime:
    """Return the reservation created-at sort key."""
    return parse_datetime(reservation.get("created_at")) or datetime.min.replace(
        tzinfo=timezone.utc
    )


def ttl_seconds_from_payload(
    payload: dict[str, Any],
    *,
    default_ttl: int,
) -> int:
    """Return the bounded TTL from a reservation payload."""
    raw = payload.get("ttl_seconds") if isinstance(payload, dict) else None
    try:
        ttl_seconds = int(raw or default_ttl)
    except Exception:
        ttl_seconds = default_ttl
    return max(60, ttl_seconds)


def normalized_route_request(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize the route request embedded in a reservation payload."""
    if not isinstance(payload, dict):
        return {}
    raw_route_request = payload.get("route_request")
    route_request = (
        dict(raw_route_request) if isinstance(raw_route_request, dict) else dict(payload)
    )
    lane_id = route_request.get("target_lane") or route_request.get("lane_id")
    if lane_id:
        route_request["target_lane"] = str(lane_id)
    return route_request


def normalize_runner_claim_gate(raw: Any, *, source: str) -> dict[str, Any]:
    """Normalize runner claim gate state from cache or memory."""
    if not isinstance(raw, dict):
        return {
            "state": "open",
            "reason": None,
            "source": "default",
            "persisted": False,
        }
    state = str(raw.get("state") or "open").strip().lower()
    if state != "paused":
        state = "open"
    gate = dict(raw)
    gate["state"] = state
    gate["source"] = source
    gate["persisted"] = source == "redis"
    return gate
