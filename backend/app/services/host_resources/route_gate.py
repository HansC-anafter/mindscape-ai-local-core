"""Route-aware host resource candidate selection."""

from __future__ import annotations

from typing import Any

from .contracts import RouteGateDecision
from .manager import list_active_route_reservations


PRIORITY_SCORES = {
    "interactive_critical": 400,
    "interactive_high": 300,
    "interactive": 200,
    "default": 100,
    "background": 10,
}


def _task_context(task: Any) -> dict[str, Any]:
    ctx = getattr(task, "execution_context", None)
    return ctx if isinstance(ctx, dict) else {}


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _route_request_from_context(ctx: dict[str, Any]) -> dict[str, Any]:
    route_request = ctx.get("route_request")
    if isinstance(route_request, dict):
        return route_request
    host_resource = ctx.get("host_resource")
    if isinstance(host_resource, dict) and isinstance(host_resource.get("route_request"), dict):
        return host_resource["route_request"]
    return {}


def _resource_requirements_from_context(ctx: dict[str, Any]) -> dict[str, Any]:
    raw = ctx.get("runner_resource_requirements")
    if isinstance(raw, dict):
        return raw
    raw = ctx.get("resource_requirements")
    if isinstance(raw, dict):
        return raw
    raw = ctx.get("resource_admission")
    if isinstance(raw, dict) and isinstance(raw.get("requirements"), dict):
        return raw["requirements"]
    return {}


def task_route_identity(task: Any) -> dict[str, Any]:
    ctx = _task_context(task)
    route_request = _route_request_from_context(ctx)
    requirements = _resource_requirements_from_context(ctx)
    lane_id = (
        route_request.get("target_lane")
        or ctx.get("host_resource_lane_id")
        or ctx.get("runtime_lane_id")
        or ctx.get("lane_id")
        or requirements.get("vision_lane")
        or requirements.get("llm_lane")
    )
    resource_groups = set(_string_list(route_request.get("resource_groups")))
    resource_groups.update(_string_list(requirements.get("exclusive_groups")))
    if requirements.get("vision_lane"):
        resource_groups.add(str(requirements["vision_lane"]))
    if requirements.get("llm_lane"):
        resource_groups.add(str(requirements["llm_lane"]))
    priority_class = str(route_request.get("priority_class") or ctx.get("priority_class") or "default")
    return {
        "lane_id": str(lane_id).strip() if lane_id else None,
        "resource_groups": sorted(resource_groups),
        "priority_class": priority_class,
    }


def get_active_route_reservations() -> list[dict[str, Any]]:
    return list_active_route_reservations()


def has_active_route_controls(
    active_reservations: list[dict[str, Any]] | None = None,
) -> bool:
    reservations = (
        active_reservations
        if active_reservations is not None
        else get_active_route_reservations()
    )
    return bool(reservations)


def drain_after_current_reservations(
    active_reservations: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    reservations = (
        active_reservations
        if active_reservations is not None
        else get_active_route_reservations()
    )
    drain_reservations: list[dict[str, Any]] = []
    for reservation in reservations:
        if not isinstance(reservation, dict):
            continue
        route_request = reservation.get("route_request")
        if not isinstance(route_request, dict):
            route_request = {}
        drain_policy = str(
            route_request.get("drain_policy")
            or reservation.get("drain_policy")
            or ""
        ).strip().lower()
        if drain_policy == "drain_after_current":
            drain_reservations.append(reservation)
    return drain_reservations


def has_drain_after_current_controls(
    active_reservations: list[dict[str, Any]] | None = None,
) -> bool:
    return bool(drain_after_current_reservations(active_reservations))


def evaluate_route_candidate(
    task: Any,
    *,
    active_reservations: list[dict[str, Any]] | None = None,
) -> RouteGateDecision:
    identity = task_route_identity(task)
    lane_id = identity.get("lane_id")
    groups = set(identity.get("resource_groups") or [])
    priority_class = str(identity.get("priority_class") or "default")
    base_score = PRIORITY_SCORES.get(priority_class, PRIORITY_SCORES["default"])
    reservations = (
        active_reservations
        if active_reservations is not None
        else get_active_route_reservations()
    )

    best = RouteGateDecision(
        permit=False,
        score=base_score,
        reason="no_matching_route_reservation",
        target_lane=lane_id,
        payload={"route_identity": identity},
    )
    for reservation in reservations:
        route_request = reservation.get("route_request") if isinstance(reservation, dict) else {}
        if not isinstance(route_request, dict):
            continue
        target_lane = str(route_request.get("target_lane") or "").strip()
        reservation_groups = set(_string_list(route_request.get("resource_groups")))
        lane_matches = bool(target_lane and lane_id == target_lane)
        group_matches = bool(groups and reservation_groups and groups.intersection(reservation_groups))
        if not lane_matches and not group_matches:
            continue
        score = base_score + (1000 if lane_matches else 500)
        if score <= best.score and best.permit:
            continue
        best = RouteGateDecision(
            permit=True,
            score=score,
            reservation_id=str(reservation.get("reservation_id") or ""),
            target_lane=target_lane or lane_id,
            payload={
                "route_identity": identity,
                "reservation": reservation,
                "lane_matches": lane_matches,
                "group_matches": group_matches,
            },
        )
    return best
