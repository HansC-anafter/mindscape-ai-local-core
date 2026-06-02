"""Host resource dashboard and admission preview API."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Body, HTTPException, Query

from backend.app.services.host_resources.manager import (
    cancel_route_reservation,
    create_route_reservation,
    get_cached_snapshot_or_degraded,
    get_host_resource_snapshot,
    get_runner_claim_gate,
    list_host_resource_lanes,
    list_active_route_reservations,
    list_route_reservation_events,
    list_route_reservations,
    pause_lane,
    pause_runner_claim_gate,
    resume_lane,
    resume_runner_claim_gate,
    update_notification,
)
from backend.app.services.host_resources.dynamic_lane_store import (
    create_dynamic_lane,
    update_dynamic_lane,
)
from backend.app.services.host_resources.queue_utilization import (
    build_live_queue_utilization,
    get_latest_queue_utilization_snapshot,
)
from backend.app.services.host_resources.route_intents import build_route_intent_preview
from backend.app.services.host_resources.schema_readiness import (
    check_host_resource_schema_readiness,
)
from backend.app.services.host_resources.summary import build_host_resource_summary
from backend.app.services.host_resources.worker_targets import set_lane_worker_target


router = APIRouter(prefix="/api/v1/host-resources", tags=["host-resources"])


@router.get("/snapshot")
async def get_snapshot(refresh: bool = Query(False)) -> dict[str, Any]:
    return await get_host_resource_snapshot(refresh=refresh)


@router.get("/summary")
async def get_summary(
    refresh: bool = Query(False),
    allow_stale: bool = Query(False),
) -> dict[str, Any]:
    snapshot = (
        await get_host_resource_snapshot(refresh=refresh)
        if refresh or not allow_stale
        else get_cached_snapshot_or_degraded()
    )
    return build_host_resource_summary(
        snapshot,
        active_reservations=list_active_route_reservations(),
    )


@router.get("/schema-readiness")
async def get_schema_readiness() -> dict[str, Any]:
    return check_host_resource_schema_readiness()


@router.get("/queue-utilization")
async def get_queue_utilization(live: bool = Query(False)) -> dict[str, Any]:
    if live:
        return await build_live_queue_utilization()
    return get_latest_queue_utilization_snapshot()


@router.get("/lanes")
async def get_lanes() -> dict[str, Any]:
    return {"lanes": list_host_resource_lanes()}


@router.post("/lanes")
async def create_lane(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    try:
        lane = create_dynamic_lane(payload)
    except ValueError as exc:
        reason = str(exc)
        if reason == "duplicate_lane_id":
            raise HTTPException(status_code=409, detail=reason) from exc
        raise HTTPException(status_code=422, detail=reason) from exc
    return {"lane": lane}


@router.patch("/lanes/{lane_id:path}")
async def patch_lane(
    lane_id: str,
    payload: dict[str, Any] = Body(default_factory=dict),
) -> dict[str, Any]:
    try:
        lane = update_dynamic_lane(lane_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not lane:
        raise HTTPException(status_code=404, detail="dynamic_lane_not_found")
    return {"lane": lane}


@router.post("/lanes/{lane_id:path}/worker-target")
async def post_lane_worker_target(
    lane_id: str,
    payload: dict[str, Any] = Body(default_factory=dict),
) -> dict[str, Any]:
    desired_worker_count = int((payload or {}).get("desired_worker_count") or 0)
    return await set_lane_worker_target(lane_id, desired_worker_count)


@router.get("/admission-preview")
async def get_admission_preview(
    lane_id: Optional[str] = Query(None),
    memory_mb: Optional[int] = Query(None),
    cpu_weight: Optional[int] = Query(None),
    refresh: bool = Query(False),
) -> dict[str, Any]:
    raise HTTPException(
        status_code=410,
        detail={
            "replacement": "/api/v1/host-resources/route-intents/preview",
            "reason": "admission_preview_replaced_by_route_intent_preview",
        },
    )


@router.post("/lanes/{lane_id:path}/pause")
async def pause_host_lane(lane_id: str) -> dict[str, Any]:
    return pause_lane(lane_id)


@router.post("/lanes/{lane_id:path}/resume")
async def resume_host_lane(lane_id: str) -> dict[str, Any]:
    return resume_lane(lane_id)


@router.get("/route-reservations")
async def get_route_reservations(
    include_durable: bool = Query(True),
    state: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=200),
) -> dict[str, Any]:
    reservations = list_route_reservations(
        include_durable=include_durable,
        state=state,
        limit=limit,
    )
    return {"reservations": reservations}


@router.post("/route-intents/preview")
async def post_route_intent_preview(
    payload: Optional[dict[str, Any]] = Body(default=None),
) -> dict[str, Any]:
    return await build_route_intent_preview(payload or {})


@router.get("/route-reservations/events")
async def get_route_reservation_events(
    reservation_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    return {
        "events": list_route_reservation_events(
            reservation_id=reservation_id,
            limit=limit,
        )
    }


@router.post("/route-reservations")
async def post_route_reservation(
    payload: Optional[dict[str, Any]] = Body(default=None),
) -> dict[str, Any]:
    return create_route_reservation(payload or {})


@router.delete("/route-reservations/{reservation_id}")
async def delete_route_reservation(reservation_id: str) -> dict[str, Any]:
    return cancel_route_reservation(reservation_id)


@router.get("/runner-claim-gate")
async def get_runner_claim_gate_state() -> dict[str, Any]:
    return get_runner_claim_gate()


@router.post("/runner-claim-gate/pause")
async def pause_runner_claims(
    payload: Optional[dict[str, Any]] = Body(default=None),
) -> dict[str, Any]:
    return pause_runner_claim_gate(payload or {})


@router.post("/runner-claim-gate/resume")
async def resume_runner_claims() -> dict[str, Any]:
    return resume_runner_claim_gate()


@router.post("/notifications/{notification_id}/ack")
async def ack_notification(notification_id: str) -> dict[str, Any]:
    return update_notification(notification_id, "acknowledged")


@router.post("/notifications/{notification_id}/snooze")
async def snooze_notification(
    notification_id: str,
    payload: Optional[dict[str, Any]] = Body(default=None),
) -> dict[str, Any]:
    raw_seconds = payload.get("snooze_seconds") if isinstance(payload, dict) else None
    try:
        snooze_seconds = int(raw_seconds or 3600)
    except Exception:
        snooze_seconds = 3600
    return update_notification(notification_id, "snoozed", snooze_seconds=snooze_seconds)
