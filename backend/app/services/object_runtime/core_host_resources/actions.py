"""Non-mutating actions for core host resource objects."""

from __future__ import annotations

from typing import Any

from backend.app.services.object_runtime.core_host_resources.catalog import (
    HOST_RESOURCE_LANE_KIND,
    OWNER_PACK,
)
from backend.app.services.object_runtime.core_host_resources.records import text_value


def _role_target_lane(role_assignments: Any) -> str | None:
    for assignment in list(role_assignments or []):
        if not isinstance(assignment, dict):
            continue
        ref = assignment.get("ref")
        if not isinstance(ref, dict):
            continue
        if (
            ref.get("owner_pack") == OWNER_PACK
            and ref.get("object_kind") == HOST_RESOURCE_LANE_KIND
        ):
            return text_value(ref.get("object_id"))
    return None


def plan_preview_route_intent(
    *,
    workspace_id: str,
    role_assignments: list[dict[str, Any]] | None = None,
    request_context: dict[str, Any] | None = None,
    **_: Any,
) -> dict[str, Any]:
    lane_id = _role_target_lane(role_assignments)
    route_request = dict((request_context or {}).get("route_request") or {})
    if lane_id:
        route_request["target_lane"] = lane_id
    route_request.setdefault("workspace_id", workspace_id)
    route_request.setdefault("requested_by", "aol_host_resource_lane_object")
    return {
        "status": "planned",
        "action": "preview_route_intent",
        "route_request": route_request,
        "request_context": {"resource_mutation": "none"},
    }


async def execute_preview_route_intent(
    *,
    workspace_id: str,
    request_plan: dict[str, Any] | None = None,
    **_: Any,
) -> dict[str, Any]:
    from backend.app.services.host_resources.route_intents import (
        build_route_intent_preview,
    )

    plan = request_plan or {}
    route_request = dict(plan.get("route_request") or {})
    route_request.setdefault("workspace_id", workspace_id)
    preview = await build_route_intent_preview(
        {"route_request": route_request, "include_candidates": False},
        auth_context=None,
    )
    return {
        "status": "succeeded",
        "resource_mutation": "none",
        "route_intent_preview": preview,
    }


__all__ = [
    "plan_preview_route_intent",
    "execute_preview_route_intent",
]
