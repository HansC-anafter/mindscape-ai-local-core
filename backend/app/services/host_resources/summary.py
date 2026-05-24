"""Compact host resource summary for low-cost UI surfaces."""

from __future__ import annotations

from typing import Any, Mapping

from .control_plane_pressure import build_control_plane_pressure


DASHBOARD_HREF = "/settings?tab=runtime&section=host-resources"
BUSY_LANE_STATES = {"busy", "running"}
BLOCKED_LANE_STATES = {"blocked", "paused", "disabled", "unavailable"}


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_number(value: Any) -> float | int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return value
    try:
        parsed = float(value)
    except Exception:
        return None
    if parsed.is_integer():
        return int(parsed)
    return parsed


def _as_int(value: Any, default: int = 0) -> int:
    number = _as_number(value)
    return int(number) if number is not None else default


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _pressure_state(*, degraded: bool, free_percent: Any) -> str:
    free = _as_number(free_percent)
    if degraded:
        return "critical"
    if free is None:
        return "unknown"
    if free < 15:
        return "critical"
    if free < 30:
        return "watch"
    return "ok"


def _consumer_memory_mb(consumer: Mapping[str, Any]) -> float:
    value = _as_number(consumer.get("memory_mb"))
    return float(value) if value is not None else 0.0


def _build_heavy_consumers(consumers: list[Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for consumer in consumers:
        if not isinstance(consumer, Mapping):
            continue
        memory_mb = _as_number(consumer.get("memory_mb")) or 0
        consumer_id = _string_or_none(consumer.get("consumer_id")) or _string_or_none(consumer.get("id")) or "unknown"
        normalized.append(
            {
                "consumer_id": consumer_id,
                "label": _string_or_none(consumer.get("label")) or consumer_id,
                "memory_mb": memory_mb,
                "memory_source": _string_or_none(consumer.get("memory_source")),
            }
        )
    normalized.sort(key=_consumer_memory_mb, reverse=True)
    return normalized[:3]


def _build_primary_blockers(lanes: list[Any]) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    for lane in lanes:
        if not isinstance(lane, Mapping):
            continue
        state = _string_or_none(lane.get("state")) or "unknown"
        if state not in BLOCKED_LANE_STATES:
            continue
        lane_id = _string_or_none(lane.get("lane_id")) or _string_or_none(lane.get("id")) or "unknown"
        blockers.append(
            {
                "lane_id": lane_id,
                "label": _string_or_none(lane.get("label")) or lane_id,
                "state": state,
                "reason": _string_or_none(lane.get("reason")) or _string_or_none(lane.get("degraded_reason")),
            }
        )
    return blockers[:3]


def _build_route_controls(active_reservations: list[Any]) -> dict[str, Any]:
    controls = {
        "active": 0,
        "draining": 0,
        "targets": [],
    }
    targets: list[str] = []
    for reservation in active_reservations:
        if not isinstance(reservation, Mapping):
            continue
        controls["active"] += 1
        route_request = _as_mapping(reservation.get("route_request"))
        drain_policy = _string_or_none(route_request.get("drain_policy")) or _string_or_none(reservation.get("drain_policy"))
        if drain_policy == "drain_after_current":
            controls["draining"] += 1
        target_lane = _string_or_none(route_request.get("target_lane"))
        if target_lane and target_lane not in targets:
            targets.append(target_lane)
    controls["targets"] = targets[:3]
    return controls


def _build_alerts(
    *,
    pressure_state: str,
    blocked_lanes: int,
    route_controls: Mapping[str, Any],
    control_plane_pressure: Mapping[str, Any],
) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    if pressure_state == "critical":
        alerts.append(
            {
                "alert_id": "memory_pressure_critical",
                "severity": "critical",
                "message": "Host memory pressure is critical",
                "action_href": DASHBOARD_HREF,
            }
        )
    elif pressure_state == "watch":
        alerts.append(
            {
                "alert_id": "memory_pressure_watch",
                "severity": "warning",
                "message": "Host memory headroom is low",
                "action_href": DASHBOARD_HREF,
            }
        )
    if blocked_lanes > 0:
        alerts.append(
            {
                "alert_id": "host_resource_lanes_blocked",
                "severity": "warning",
                "message": f"{blocked_lanes} host resource lane(s) blocked",
                "action_href": DASHBOARD_HREF,
            }
        )
    draining = _as_int(route_controls.get("draining")) if isinstance(route_controls, Mapping) else 0
    if draining > 0:
        alerts.append(
            {
                "alert_id": "route_drain_active",
                "severity": "info",
                "message": f"{draining} route reservation(s) draining",
                "action_href": DASHBOARD_HREF,
            }
        )
    if control_plane_pressure.get("state") in {"watch", "critical"}:
        alerts.append(
            {
                "alert_id": "control_plane_pressure",
                "severity": "critical" if control_plane_pressure.get("state") == "critical" else "warning",
                "message": "Control plane resource pressure is elevated",
                "action_href": DASHBOARD_HREF,
            }
        )
    return alerts[:3]


def build_host_resource_summary(
    snapshot: Mapping[str, Any],
    *,
    active_reservations: list[Any] | None = None,
) -> dict[str, Any]:
    """Return a stable low-cost summary from a full host resource snapshot."""

    safe_snapshot = _as_mapping(snapshot)
    host = _as_mapping(safe_snapshot.get("host"))
    memory_pressure = _as_mapping(host.get("memory_pressure"))
    capacity = _as_mapping(safe_snapshot.get("capacity"))
    consumers = _as_list(safe_snapshot.get("consumers"))
    lanes = _as_list(safe_snapshot.get("lanes"))
    degraded = bool(safe_snapshot.get("degraded"))
    free_percent = _as_number(memory_pressure.get("free_percent"))
    lane_states = [
        _string_or_none(lane.get("state")) if isinstance(lane, Mapping) else None
        for lane in lanes
    ]
    pressure_state = _pressure_state(degraded=degraded, free_percent=free_percent)
    blocked_lanes = sum(1 for state in lane_states if state in BLOCKED_LANE_STATES)
    route_controls = _build_route_controls(active_reservations or [])
    control_plane_pressure = build_control_plane_pressure(consumers)

    return {
        "captured_at": _string_or_none(safe_snapshot.get("captured_at")),
        "degraded": degraded,
        "pressure_state": pressure_state,
        "free_percent": free_percent,
        "headroom_mb": _as_int(capacity.get("memory_mb")),
        "reserved_mb": _as_int(capacity.get("reserved_memory_mb")),
        "lanes": {
            "busy": sum(1 for state in lane_states if state in BUSY_LANE_STATES),
            "blocked": blocked_lanes,
            "total": len(lanes),
        },
        "heavy_consumers": _build_heavy_consumers(consumers),
        "primary_blockers": _build_primary_blockers(lanes),
        "route_controls": route_controls,
        "control_plane_pressure": control_plane_pressure,
        "alerts": _build_alerts(
            pressure_state=pressure_state,
            blocked_lanes=blocked_lanes,
            route_controls=route_controls,
            control_plane_pressure=control_plane_pressure,
        ),
        "dashboard_href": DASHBOARD_HREF,
    }
