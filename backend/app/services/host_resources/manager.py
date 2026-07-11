"""Host resource manager state and cached snapshot access."""

from __future__ import annotations

import asyncio
import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.app.services.cache.redis_cache import get_cache_service

from .host_bridge import HostBridgeError, call_host_resource_probe
from .lane_registry import load_lane_registry
from .manager_core import (
    clamped_reservation_limit as _clamped_reservation_limit,
    normalize_runner_claim_gate as _normalize_runner_claim_gate,
    normalized_route_request as _normalized_route_request,
    parse_datetime as _parse_datetime,
    reservation_is_active as _reservation_is_active,
    reservation_matches_state_filter as _reservation_matches_state_filter,
    reservation_sort_key as _reservation_sort_key,
    ttl_seconds_from_payload as _core_ttl_seconds_from_payload,
)
from .samplers import degraded_snapshot, snapshot_from_probe
from .runner_claim_gate_facade import (
    RUNNER_CLAIM_GATE_KEY,
    get_claim_gate_state,
    pause_claim_gate_state,
    resume_claim_gate_state,
)


logger = logging.getLogger(__name__)

SNAPSHOT_TTL_SECONDS = 5
STATE_TTL_SECONDS = int(os.getenv("LOCAL_CORE_HOST_RESOURCE_STATE_TTL_SECONDS", "3600"))
PAUSED_LANES_KEY = "mindscape:host_resources:paused_lanes"
ROUTE_RESERVATIONS_KEY = "mindscape:host_resources:route_reservations"
NOTIFICATIONS_KEY = "mindscape:host_resources:notifications"

_cached_snapshot: dict[str, Any] | None = None
_cached_at: datetime | None = None
_refresh_lock: asyncio.Lock | None = None
_paused_lanes: set[str] = set()
_route_reservations: dict[str, dict[str, Any]] = {}
_notification_state: dict[str, dict[str, Any]] = {}
_runner_claim_gate_state: dict[str, Any] | None = None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().isoformat()


def _route_reservation_store_enabled() -> bool:
    raw = os.getenv("LOCAL_CORE_HOST_RESOURCE_DB_LEDGER_ENABLED", "true")
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def _get_route_reservation_store() -> Any | None:
    if not _route_reservation_store_enabled():
        return None
    try:
        from .reservation_store import HostResourceReservationStore

        return HostResourceReservationStore()
    except Exception as exc:
        logger.debug("Host resource reservation store unavailable: %s", exc)
        return None


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


def _ttl_seconds_from_payload(payload: dict[str, Any]) -> int:
    return _core_ttl_seconds_from_payload(
        payload,
        default_ttl=STATE_TTL_SECONDS,
    )


def _route_projection_map() -> dict[str, dict[str, Any]]:
    persisted = _read_json_map(ROUTE_RESERVATIONS_KEY)
    for reservation_id, reservation in persisted.items():
        if isinstance(reservation_id, str) and isinstance(reservation, dict):
            _route_reservations[reservation_id] = reservation
    return {
        reservation_id: reservation
        for reservation_id, reservation in _route_reservations.items()
        if isinstance(reservation_id, str) and isinstance(reservation, dict)
    }


def _write_route_projection(reservation: dict[str, Any]) -> None:
    reservation_id = str(reservation.get("reservation_id") or "")
    if not reservation_id:
        return
    _route_reservations[reservation_id] = reservation
    persisted = _read_json_map(ROUTE_RESERVATIONS_KEY)
    persisted[reservation_id] = reservation
    _write_json_map(ROUTE_RESERVATIONS_KEY, persisted)


def _list_projection_reservations() -> list[dict[str, Any]]:
    return sorted(
        _route_projection_map().values(),
        key=_reservation_sort_key,
        reverse=True,
    )


def _append_reservation_event(
    event_type: str,
    *,
    reservation: dict[str, Any] | None = None,
    reservation_id: str | None = None,
    payload: dict[str, Any] | None = None,
    source: str = "host_resource_manager",
) -> bool:
    store = _get_route_reservation_store()
    if not store:
        return False
    route_request = reservation.get("route_request") if isinstance(reservation, dict) else {}
    if not isinstance(route_request, dict):
        route_request = {}
    try:
        store.append_event(
            event_type,
            reservation_id=reservation_id or str((reservation or {}).get("reservation_id") or ""),
            payload=payload if isinstance(payload, dict) else (reservation or {}),
            source=source,
            actor=str(route_request.get("requested_by") or ""),
            lane_id=str(route_request.get("target_lane") or ""),
        )
        return True
    except Exception as exc:
        logger.debug("Failed to append host resource event %s: %s", event_type, exc)
        return False


def _save_reservation_to_ledger(reservation: dict[str, Any]) -> bool:
    store = _get_route_reservation_store()
    if not store:
        return False
    try:
        store.save_reservation(reservation)
        return True
    except Exception as exc:
        logger.debug("Failed to save host resource reservation ledger row: %s", exc)
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


def _get_refresh_lock() -> asyncio.Lock:
    global _refresh_lock
    if _refresh_lock is None:
        _refresh_lock = asyncio.Lock()
    return _refresh_lock


def get_cached_snapshot_or_degraded() -> dict[str, Any]:
    if _cached_snapshot is not None:
        return _cached_snapshot
    return degraded_snapshot("host_resource_snapshot_unavailable")


def clear_host_resource_snapshot_cache() -> None:
    global _cached_snapshot, _cached_at
    _cached_snapshot = None
    _cached_at = None


async def refresh_host_resource_snapshot() -> dict[str, Any]:
    global _cached_snapshot, _cached_at
    async with _get_refresh_lock():
        if _snapshot_is_fresh():
            return _cached_snapshot or degraded_snapshot("host_resource_snapshot_unavailable")
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
    registry = load_lane_registry()
    snapshot = _cached_snapshot if isinstance(_cached_snapshot, dict) else {}
    lanes = snapshot.get("lanes")
    if isinstance(lanes, list):
        merged = dict(registry)
        for lane in lanes:
            if not isinstance(lane, dict):
                continue
            lane_id = lane.get("lane_id")
            if isinstance(lane_id, str) and lane_id.strip():
                merged[lane_id] = {**merged.get(lane_id, {}), **lane}
        return list(merged.values())
    return list(registry.values())


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


def create_route_reservation(payload: dict[str, Any]) -> dict[str, Any]:
    from .route_reservation_service import create_route_reservation as create

    return create(payload)


def cancel_route_reservation(reservation_id: str) -> dict[str, Any]:
    from .route_reservation_service import cancel_route_reservation as cancel

    return cancel(reservation_id)


def rehydrate_route_reservation_projection() -> list[dict[str, Any]]:
    store = _get_route_reservation_store()
    if not store:
        return []
    try:
        active_reservations = store.list_active_reservations(limit=100)
    except Exception as exc:
        logger.debug("Failed to rehydrate host resource reservation projection: %s", exc)
        return []
    if not active_reservations:
        return []
    persisted = _read_json_map(ROUTE_RESERVATIONS_KEY)
    for reservation in active_reservations:
        reservation_id = str(reservation.get("reservation_id") or "")
        if not reservation_id:
            continue
        _route_reservations[reservation_id] = reservation
        persisted[reservation_id] = reservation
    _write_json_map(ROUTE_RESERVATIONS_KEY, persisted)
    return active_reservations


def list_route_reservation_events(
    *,
    reservation_id: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    store = _get_route_reservation_store()
    if not store:
        return []
    try:
        return store.list_events(
            reservation_id=reservation_id,
            limit=max(1, min(int(limit or 50), 200)),
        )
    except Exception as exc:
        logger.debug("Failed to list host resource reservation events: %s", exc)
        return []


def list_route_reservations(
    *,
    include_durable: bool = True,
    state: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    clamped_limit = _clamped_reservation_limit(limit)
    reservations_by_id = {
        str(reservation.get("reservation_id") or ""): dict(reservation)
        for reservation in _list_projection_reservations()
        if str(reservation.get("reservation_id") or "")
    }
    if include_durable:
        store = _get_route_reservation_store()
        if store:
            try:
                fetch_limit = max(100, clamped_limit)
                expired = store.expire_stale_reservations(limit=fetch_limit)
                for reservation in expired:
                    _append_reservation_event(
                        "reservation_expired",
                        reservation=reservation,
                        payload={"reservation_id": reservation.get("reservation_id")},
                    )
                durable_reservations = store.list_reservations(limit=fetch_limit)
            except Exception as exc:
                logger.debug("Failed to list durable host resource reservations: %s", exc)
                durable_reservations = []
            for reservation in durable_reservations:
                reservation_id = str(reservation.get("reservation_id") or "")
                if reservation_id:
                    reservations_by_id[reservation_id] = reservation
                    _route_reservations[reservation_id] = reservation
            active_durable = [
                reservation
                for reservation in durable_reservations
                if isinstance(reservation, dict) and _reservation_is_active(reservation)
            ]
            if active_durable:
                persisted = _read_json_map(ROUTE_RESERVATIONS_KEY)
                for reservation in active_durable:
                    reservation_id = str(reservation.get("reservation_id") or "")
                    if reservation_id:
                        persisted[reservation_id] = reservation
                _write_json_map(ROUTE_RESERVATIONS_KEY, persisted)
    filtered = [
        reservation
        for reservation in reservations_by_id.values()
        if _reservation_matches_state_filter(reservation, state)
    ]
    return sorted(
        filtered,
        key=_reservation_sort_key,
        reverse=True,
    )[:clamped_limit]


def list_active_route_reservations() -> list[dict[str, Any]]:
    return [
        reservation
        for reservation in _list_projection_reservations()
        if isinstance(reservation, dict) and _reservation_is_active(reservation)
    ]


def update_notification(
    notification_id: str,
    state: str,
    *,
    snooze_seconds: int | None = None,
) -> dict[str, Any]:
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


def get_runner_claim_gate() -> dict[str, Any]:
    global _runner_claim_gate_state
    _runner_claim_gate_state, result = get_claim_gate_state(get_cache_service())
    return result


def pause_runner_claim_gate(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    global _runner_claim_gate_state
    _runner_claim_gate_state, result = pause_claim_gate_state(
        get_cache_service(),
        payload,
        default_ttl_seconds=STATE_TTL_SECONDS,
    )
    return result


def resume_runner_claim_gate() -> dict[str, Any]:
    global _runner_claim_gate_state
    _runner_claim_gate_state, result = resume_claim_gate_state(
        get_cache_service()
    )
    return result
