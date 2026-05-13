"""Host resource manager state and cached snapshot access."""

from __future__ import annotations

import uuid
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.app.services.cache.redis_cache import get_cache_service

from .host_bridge import HostBridgeError, call_host_resource_probe
from .lane_registry import load_lane_registry
from .samplers import degraded_snapshot, snapshot_from_probe


SNAPSHOT_TTL_SECONDS = 5
STATE_TTL_SECONDS = int(os.getenv("LOCAL_CORE_HOST_RESOURCE_STATE_TTL_SECONDS", "3600"))
PAUSED_LANES_KEY = "mindscape:host_resources:paused_lanes"
ROUTE_RESERVATIONS_KEY = "mindscape:host_resources:route_reservations"
NOTIFICATIONS_KEY = "mindscape:host_resources:notifications"
RUNNER_CLAIM_GATE_KEY = "mindscape:host_resources:runner_claim_gate"

_cached_snapshot: dict[str, Any] | None = None
_cached_at: datetime | None = None
_paused_lanes: set[str] = set()
_route_reservations: dict[str, dict[str, Any]] = {}
_notification_state: dict[str, dict[str, Any]] = {}
_runner_claim_gate_state: dict[str, Any] | None = None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().isoformat()


def _read_json_map(key: str) -> dict[str, Any]:
    try:
        value = get_cache_service().get_json(key)
    except Exception:
        value = None
    return value if isinstance(value, dict) else {}


def _write_json_map(key: str, value: dict[str, Any]) -> None:
    try:
        get_cache_service().set_json(key, value, ttl=STATE_TTL_SECONDS)
    except Exception:
        pass


def _read_json_list(key: str) -> list[str]:
    try:
        value = get_cache_service().get_json(key)
    except Exception:
        value = None
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _write_json_list(key: str, value: list[str]) -> None:
    try:
        get_cache_service().set_json(key, value, ttl=STATE_TTL_SECONDS)
    except Exception:
        pass


def _write_json_value(key: str, value: Any, *, ttl: int | None = None) -> bool:
    try:
        return bool(
            get_cache_service().set_json(
                key,
                value,
                ttl=ttl or STATE_TTL_SECONDS,
            )
        )
    except Exception:
        return False


def _delete_json_value(key: str) -> bool:
    try:
        return bool(get_cache_service().delete(key))
    except Exception:
        return False


def _current_paused_lanes() -> set[str]:
    persisted = set(_read_json_list(PAUSED_LANES_KEY))
    if persisted:
        _paused_lanes.update(persisted)
    return set(_paused_lanes)


def _snapshot_is_fresh() -> bool:
    if _cached_snapshot is None or _cached_at is None:
        return False
    return (_utc_now() - _cached_at) < timedelta(seconds=SNAPSHOT_TTL_SECONDS)


def get_cached_snapshot_or_degraded() -> dict[str, Any]:
    if _cached_snapshot is not None:
        return _cached_snapshot
    return degraded_snapshot("host_resource_snapshot_unavailable")


async def refresh_host_resource_snapshot() -> dict[str, Any]:
    global _cached_snapshot, _cached_at
    try:
        probe_payload = await call_host_resource_probe()
        snapshot = snapshot_from_probe(probe_payload, paused_lanes=_current_paused_lanes())
    except HostBridgeError as exc:
        snapshot = degraded_snapshot(str(exc))
    _cached_snapshot = snapshot
    _cached_at = _utc_now()
    return snapshot


async def get_host_resource_snapshot(*, refresh: bool = False) -> dict[str, Any]:
    if refresh or not _snapshot_is_fresh():
        return await refresh_host_resource_snapshot()
    return _cached_snapshot or degraded_snapshot("host_resource_snapshot_unavailable")


def list_host_resource_lanes() -> list[dict[str, Any]]:
    snapshot = get_cached_snapshot_or_degraded()
    lanes = snapshot.get("lanes")
    if isinstance(lanes, list):
        return [lane for lane in lanes if isinstance(lane, dict)]
    return list(load_lane_registry().values())


def pause_lane(lane_id: str) -> dict[str, Any]:
    _paused_lanes.add(lane_id)
    _write_json_list(PAUSED_LANES_KEY, sorted(_paused_lanes))
    if _cached_snapshot:
        for lane in _cached_snapshot.get("lanes", []):
            if isinstance(lane, dict) and lane.get("lane_id") == lane_id:
                lane["state"] = "paused"
    return {"lane_id": lane_id, "state": "paused"}


def resume_lane(lane_id: str) -> dict[str, Any]:
    _paused_lanes.discard(lane_id)
    _write_json_list(PAUSED_LANES_KEY, sorted(_paused_lanes))
    return {"lane_id": lane_id, "state": "resumed"}


def is_lane_paused(lane_id: str | None) -> bool:
    return bool(lane_id and lane_id in _current_paused_lanes())


def _normalized_route_request(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    raw_route_request = payload.get("route_request")
    route_request = dict(raw_route_request) if isinstance(raw_route_request, dict) else dict(payload)
    lane_id = route_request.get("target_lane") or route_request.get("lane_id")
    if lane_id:
        route_request["target_lane"] = str(lane_id)
    return route_request


def create_route_reservation(payload: dict[str, Any]) -> dict[str, Any]:
    reservation_id = f"hostres_{uuid.uuid4().hex}"
    reservation = {
        "reservation_id": reservation_id,
        "state": "reserved_waiting",
        "created_at": _utc_now_iso(),
        "route_request": _normalized_route_request(payload),
    }
    _route_reservations[reservation_id] = reservation
    persisted = _read_json_map(ROUTE_RESERVATIONS_KEY)
    persisted[reservation_id] = reservation
    _write_json_map(ROUTE_RESERVATIONS_KEY, persisted)
    return reservation


def cancel_route_reservation(reservation_id: str) -> dict[str, Any]:
    reservation = _route_reservations.get(reservation_id)
    if not reservation:
        persisted = _read_json_map(ROUTE_RESERVATIONS_KEY)
        raw_reservation = persisted.get(reservation_id)
        if isinstance(raw_reservation, dict):
            reservation = raw_reservation
    if not reservation:
        return {"reservation_id": reservation_id, "state": "not_found"}
    reservation = dict(reservation)
    reservation["state"] = "cancelled"
    reservation["cancelled_at"] = _utc_now_iso()
    _route_reservations[reservation_id] = reservation
    persisted = _read_json_map(ROUTE_RESERVATIONS_KEY)
    persisted[reservation_id] = reservation
    _write_json_map(ROUTE_RESERVATIONS_KEY, persisted)
    return reservation


def list_route_reservations() -> list[dict[str, Any]]:
    persisted = _read_json_map(ROUTE_RESERVATIONS_KEY)
    for reservation_id, reservation in persisted.items():
        if isinstance(reservation_id, str) and isinstance(reservation, dict):
            _route_reservations[reservation_id] = reservation
    return list(_route_reservations.values())


def list_active_route_reservations() -> list[dict[str, Any]]:
    return [
        reservation
        for reservation in list_route_reservations()
        if isinstance(reservation, dict)
        and reservation.get("state") in {"reserved_waiting", "permitted"}
    ]


def update_notification(notification_id: str, state: str, *, snooze_seconds: int | None = None) -> dict[str, Any]:
    updated = {
        "notification_id": notification_id,
        "state": state,
        "updated_at": _utc_now_iso(),
    }
    if snooze_seconds is not None:
        updated["snooze_seconds"] = max(1, int(snooze_seconds))
    _notification_state[notification_id] = updated
    persisted = _read_json_map(NOTIFICATIONS_KEY)
    persisted[notification_id] = updated
    _write_json_map(NOTIFICATIONS_KEY, persisted)
    return updated


def _normalize_runner_claim_gate(raw: Any, *, source: str) -> dict[str, Any]:
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


def get_runner_claim_gate() -> dict[str, Any]:
    global _runner_claim_gate_state
    persisted = _read_json_map(RUNNER_CLAIM_GATE_KEY)
    if persisted:
        _runner_claim_gate_state = _normalize_runner_claim_gate(
            persisted,
            source="redis",
        )
        return dict(_runner_claim_gate_state)
    _runner_claim_gate_state = None
    return _normalize_runner_claim_gate(None, source="default")


def pause_runner_claim_gate(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    global _runner_claim_gate_state
    payload = payload if isinstance(payload, dict) else {}
    try:
        ttl_seconds = int(payload.get("ttl_seconds") or STATE_TTL_SECONDS)
    except Exception:
        ttl_seconds = STATE_TTL_SECONDS
    ttl_seconds = max(60, ttl_seconds)
    gate = {
        "state": "paused",
        "reason": str(payload.get("reason") or "maintenance"),
        "requested_by": str(payload.get("requested_by") or "local_runtime"),
        "paused_at": _utc_now_iso(),
        "ttl_seconds": ttl_seconds,
    }
    persisted = _write_json_value(
        RUNNER_CLAIM_GATE_KEY,
        gate,
        ttl=ttl_seconds,
    )
    _runner_claim_gate_state = dict(gate)
    result = _normalize_runner_claim_gate(
        gate,
        source="redis" if persisted else "memory",
    )
    result["persisted"] = persisted
    return result


def resume_runner_claim_gate() -> dict[str, Any]:
    global _runner_claim_gate_state
    _runner_claim_gate_state = {
        "state": "open",
        "reason": None,
        "resumed_at": _utc_now_iso(),
    }
    persisted = _delete_json_value(RUNNER_CLAIM_GATE_KEY)
    result = _normalize_runner_claim_gate(_runner_claim_gate_state, source="memory")
    result["persisted"] = persisted
    return result
