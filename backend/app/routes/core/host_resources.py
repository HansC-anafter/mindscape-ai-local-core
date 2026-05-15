"""Host resource dashboard and admission preview API."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Body, Query

from backend.app.services.host_resources.advisor import build_admission_preview
from backend.app.services.host_resources.manager import (
    cancel_route_reservation,
    create_route_reservation,
    get_host_resource_snapshot,
    get_runner_claim_gate,
    list_host_resource_lanes,
    list_route_reservation_events,
    list_route_reservations,
    pause_lane,
    pause_runner_claim_gate,
    resume_lane,
    resume_runner_claim_gate,
    update_notification,
)
from backend.app.services.host_resources.queue_preview import (
    build_route_reservation_candidate_previews,
)


router = APIRouter(prefix="/api/v1/host-resources", tags=["host-resources"])


@router.get("/snapshot")
async def get_snapshot(refresh: bool = Query(False)) -> dict[str, Any]:
    return await get_host_resource_snapshot(refresh=refresh)


@router.get("/lanes")
async def get_lanes() -> dict[str, Any]:
    return {"lanes": list_host_resource_lanes()}


@router.get("/admission-preview")
async def get_admission_preview(
    lane_id: Optional[str] = Query(None),
    memory_mb: Optional[int] = Query(None),
    cpu_weight: Optional[int] = Query(None),
    refresh: bool = Query(False),
) -> dict[str, Any]:
    return await build_admission_preview(
        lane_id=lane_id,
        memory_mb=memory_mb,
        cpu_weight=cpu_weight,
        refresh=refresh,
    )


@router.post("/lanes/{lane_id:path}/pause")
async def pause_host_lane(lane_id: str) -> dict[str, Any]:
    return pause_lane(lane_id)


@router.post("/lanes/{lane_id:path}/resume")
async def resume_host_lane(lane_id: str) -> dict[str, Any]:
    return resume_lane(lane_id)


@router.get("/route-reservations")
async def get_route_reservations(
    include_candidates: bool = Query(False),
    include_durable: bool = Query(True),
    state: Optional[str] = Query(None),
    scan_limit: int = Query(25, ge=1, le=200),
    limit: int = Query(100, ge=1, le=200),
) -> dict[str, Any]:
    reservations = list_route_reservations(
        include_durable=include_durable,
        state=state,
        limit=limit,
    )
    if not include_candidates:
        return {"reservations": reservations}
    previews = await build_route_reservation_candidate_previews(
        reservations,
        scan_limit=scan_limit,
    )
    return {
        "reservations": [
            {
                **reservation,
                "candidate_preview": previews.get(str(reservation.get("reservation_id") or "")),
            }
            for reservation in reservations
        ]
    }


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
