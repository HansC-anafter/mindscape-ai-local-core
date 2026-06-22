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


def _runtime_affinity_from_context(ctx: dict[str, Any]) -> dict[str, Any]:
    raw = ctx.get("runtime_affinity")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        return {"runtime_id": raw.strip()}
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
    runtime_affinity = _runtime_affinity_from_context(ctx)
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
    resource_flavor = (
        route_request.get("resource_flavor")
        or ctx.get("resource_flavor")
        or runtime_affinity.get("resource_flavor")
        or _resource_flavor_from_runtime_affinity(runtime_affinity)
    )
    return {
        "lane_id": str(lane_id).strip() if lane_id else None,
        "resource_groups": sorted(resource_groups),
        "priority_class": priority_class,
        "resource_flavor": str(resource_flavor).strip() if resource_flavor else None,
        "pack_id": str(getattr(task, "pack_id", None) or ctx.get("pack_id") or ctx.get("playbook_code") or "").strip() or None,
        "playbook_code": str(ctx.get("playbook_code") or getattr(task, "pack_id", None) or "").strip() or None,
    }


def _resource_flavor_from_runtime_affinity(runtime_affinity: dict[str, Any]) -> str | None:
    runtime_id = str(runtime_affinity.get("runtime_id") or "").strip()
    transport = str(runtime_affinity.get("transport") or "").strip()
    site_key = str(runtime_affinity.get("site_key") or "").strip()
    if not runtime_id:
        return None
    if runtime_id.lower() in {"local", "docker_local", "host"}:
        return "local.host"
    if transport and transport not in {"local", "docker_local"}:
        return f"external.{transport}.{runtime_id}"
    if site_key:
        return f"vm.{site_key}.{runtime_id}"
    return f"local.{runtime_id}"


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


def _route_request_from_reservation(reservation: dict[str, Any]) -> dict[str, Any]:
    route_request = reservation.get("route_request")
    if isinstance(route_request, dict):
        return route_request
    return {}


def route_identity_matches_reservation_scope(
    identity: dict[str, Any],
    reservation: dict[str, Any],
) -> bool:
    if not isinstance(identity, dict) or not isinstance(reservation, dict):
        return False

    route_request = _route_request_from_reservation(reservation)
    lane_id = str(identity.get("lane_id") or identity.get("target_lane") or "").strip()
    groups = set(_string_list(identity.get("resource_groups")))
    resource_flavor = str(identity.get("resource_flavor") or "").strip()
    target_lane = str(route_request.get("target_lane") or "").strip()
    reservation_groups = set(_string_list(route_request.get("resource_groups")))
    reservation_flavor = str(route_request.get("resource_flavor") or "").strip()

    lane_matches = bool(target_lane and lane_id == target_lane)
    group_matches = bool(groups and reservation_groups and groups.intersection(reservation_groups))
    flavor_matches = bool(resource_flavor and reservation_flavor and resource_flavor == reservation_flavor)
    if reservation_flavor and resource_flavor and not flavor_matches:
        return False
    return lane_matches or group_matches or flavor_matches


def drain_after_current_reservations_for_candidates(
    candidates: list[dict[str, Any]],
    active_reservations: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    drain_reservations = drain_after_current_reservations(active_reservations)
    scoped: list[dict[str, Any]] = []
    for reservation in drain_reservations:
        for candidate in candidates:
            identity = candidate.get("route_identity") if isinstance(candidate, dict) else None
            if isinstance(identity, dict) and route_identity_matches_reservation_scope(identity, reservation):
                scoped.append(reservation)
                break
    return scoped


def evaluate_route_candidate(
    task: Any,
    *,
    active_reservations: list[dict[str, Any]] | None = None,
) -> RouteGateDecision:
    identity = task_route_identity(task)
    return evaluate_route_identity_candidate(
        identity,
        active_reservations=active_reservations,
    )


def evaluate_route_identity_candidate(
    identity: dict[str, Any],
    *,
    active_reservations: list[dict[str, Any]] | None = None,
) -> RouteGateDecision:
    lane_id = identity.get("lane_id")
    groups = set(identity.get("resource_groups") or [])
    priority_class = str(identity.get("priority_class") or "default")
    resource_flavor = str(identity.get("resource_flavor") or "").strip()
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
        if not isinstance(reservation, dict):
            continue
        route_request = _route_request_from_reservation(reservation)
        target_lane = str(route_request.get("target_lane") or "").strip()
        reservation_groups = set(_string_list(route_request.get("resource_groups")))
        reservation_flavor = str(route_request.get("resource_flavor") or "").strip()
        lane_matches = bool(target_lane and lane_id == target_lane)
        group_matches = bool(groups and reservation_groups and groups.intersection(reservation_groups))
        flavor_matches = bool(resource_flavor and reservation_flavor and resource_flavor == reservation_flavor)
        if reservation_flavor and resource_flavor and not flavor_matches:
            continue
        if not lane_matches and not group_matches and not flavor_matches:
            continue
        score = base_score + (1000 if lane_matches else 500) + (250 if flavor_matches else 0)
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
                "flavor_matches": flavor_matches,
            },
        )
    return best


def select_candidate_policy(
    candidates: list[dict[str, Any]],
    *,
    active_reservations: list[dict[str, Any]] | None = None,
    reserved_share_pack_ids: list[str] | None = None,
    active_pack_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Select one candidate through the single route-gate policy entrypoint."""

    reservations = (
        active_reservations
        if active_reservations is not None
        else get_active_route_reservations()
    )
    best_route: tuple[int, dict[str, Any], RouteGateDecision] | None = None
    for candidate in candidates:
        identity = candidate.get("route_identity")
        if not isinstance(identity, dict):
            continue
        decision = evaluate_route_identity_candidate(
            identity,
            active_reservations=reservations,
        )
        if not decision.permit:
            continue
        if best_route is None or decision.score > best_route[0]:
            best_route = (decision.score, candidate, decision)
    if best_route is not None:
        _, candidate, decision = best_route
        return {
            "selected": candidate,
            "reason": "route_reservation",
            "decision": decision,
            "drain_wait": False,
        }

    scoped_drain_reservations = drain_after_current_reservations_for_candidates(
        candidates,
        reservations,
    )
    if scoped_drain_reservations:
        return {
            "selected": None,
            "reason": "drain_after_current_wait",
            "decision": None,
            "drain_wait": True,
            "reservations": scoped_drain_reservations,
        }

    preferred = {str(pack_id) for pack_id in (reserved_share_pack_ids or []) if str(pack_id).strip()}
    if preferred:
        for candidate in candidates:
            if str(candidate.get("pack_id") or "") in preferred:
                return {
                    "selected": candidate,
                    "reason": "reserved_share",
                    "decision": None,
                    "drain_wait": False,
                }

    active = {str(pack_id) for pack_id in (active_pack_ids or set()) if str(pack_id).strip()}
    if active:
        for candidate in candidates:
            pack_id = str(candidate.get("pack_id") or "")
            if pack_id and pack_id not in active:
                return {
                    "selected": candidate,
                    "reason": "playbook_diversity",
                    "decision": None,
                    "drain_wait": False,
                }

    return {
        "selected": None,
        "reason": "fifo_fallback",
        "decision": None,
        "drain_wait": False,
    }
