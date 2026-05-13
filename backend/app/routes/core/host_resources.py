"""Host resource dashboard and admission preview API."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Body, Query

from backend.app.services.host_resources.advisor import build_admission_preview
from backend.app.services.host_resources.manager import (
    cancel_route_reservation,
    create_route_reservation,
    get_host_resource_snapshot,
    list_host_resource_lanes,
    list_route_reservations,
    pause_lane,
    resume_lane,
    update_notification,
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
async def get_route_reservations() -> dict[str, Any]:
    return {"reservations": list_route_reservations()}


@router.post("/route-reservations")
async def post_route_reservation(
    payload: Optional[dict[str, Any]] = Body(default=None),
) -> dict[str, Any]:
    return create_route_reservation(payload or {})


@router.delete("/route-reservations/{reservation_id}")
async def delete_route_reservation(reservation_id: str) -> dict[str, Any]:
    return cancel_route_reservation(reservation_id)


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
