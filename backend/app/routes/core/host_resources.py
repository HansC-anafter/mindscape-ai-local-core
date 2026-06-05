"""Host resource dashboard and admission preview API."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from backend.app.dependencies.auth import AuthContext, get_current_user
from backend.app.services.host_resources.route_reservation_service import (
    cancel_route_reservation,
    create_route_reservation,
)
from backend.app.services.host_resources.manager import (
    clear_host_resource_snapshot_cache,
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
from backend.app.services.host_resources.runner_claim_modes import (
    attach_runner_claim_controls,
    set_runner_claim_mode_sync,
)
from backend.app.services.host_resources.runner_spillover_control import (
    runner_spillover_action,
    runner_spillover_status,
)
from backend.app.services.host_resources.route_intents import build_route_intent_preview
from backend.app.services.host_resources.runtime_adapter_catalog import list_runtime_adapters
from backend.app.services.host_resources.schema_readiness import (
    check_host_resource_schema_readiness,
)
from backend.app.services.host_resources.summary import build_host_resource_summary
from backend.app.services.host_resources.worker_targets import set_lane_worker_target
from backend.app.services.host_resources.allocation_blueprints import (
    apply_allocation_blueprint_to_workspace,
    build_workspace_allocation_effective_matrix,
    get_allocation_blueprint,
    list_allocation_blueprints,
)
from backend.app.services.host_resources.workspace_allocations import (
    HostResourceWorkspaceAllocationStore,
    workspace_allocation_decision,
)
from backend.app.services.runner_resources import list_active_runner_resource_heartbeats
from backend.app.services.stores.redis.runner_queue_store import RedisRunnerQueueStore
from backend.app.services.resource_governance import (
    build_resource_governance_context,
    is_global_resource_admin,
    require_global_resource_admin,
    require_workspace_resource_access,
)


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


@router.get("/adapter-catalog")
async def get_adapter_catalog() -> dict[str, Any]:
    return {"adapters": list_runtime_adapters()}


@router.get("/lanes")
async def get_lanes() -> dict[str, Any]:
    return {"lanes": list_host_resource_lanes()}


@router.get("/runners")
async def get_runners(
    current_user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    require_global_resource_admin(current_user)
    redis_queue = RedisRunnerQueueStore()
    heartbeats = await list_active_runner_resource_heartbeats(redis_queue)
    runners = await attach_runner_claim_controls(redis_queue, heartbeats)
    runners.sort(key=lambda item: str(item.get("runner_id") or ""))
    return {
        "runners": runners,
        "count": len(runners),
        "governance_context": build_resource_governance_context(current_user),
    }


@router.put("/runners/{runner_id:path}/claim-mode")
async def put_runner_claim_mode(
    runner_id: str,
    payload: dict[str, Any] = Body(default_factory=dict),
    current_user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    require_global_resource_admin(current_user)
    try:
        control = set_runner_claim_mode_sync(
            runner_id,
            str((payload or {}).get("mode") or "active"),
            reason=(payload or {}).get("reason"),
            updated_by=current_user.user_id,
            ttl_seconds=(payload or {}).get("ttl_seconds"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "runner_id": runner_id,
        "claim_control": control.to_dict(),
        "governance_context": build_resource_governance_context(current_user),
    }


@router.get("/runner-spillover")
async def get_runner_spillover(
    current_user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    require_global_resource_admin(current_user)
    return {
        **await runner_spillover_status(),
        "governance_context": build_resource_governance_context(current_user),
    }


@router.post("/runner-spillover")
async def post_runner_spillover(
    payload: dict[str, Any] = Body(default_factory=dict),
    current_user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    require_global_resource_admin(current_user)
    try:
        result = await runner_spillover_action(payload or {})
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        **result,
        "governance_context": build_resource_governance_context(current_user),
    }


@router.post("/lanes")
async def create_lane(
    payload: dict[str, Any] = Body(default_factory=dict),
    current_user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    require_global_resource_admin(current_user)
    try:
        lane = create_dynamic_lane(payload)
    except ValueError as exc:
        reason = str(exc)
        if reason == "duplicate_lane_id":
            raise HTTPException(status_code=409, detail=reason) from exc
        raise HTTPException(status_code=422, detail=reason) from exc
    clear_host_resource_snapshot_cache()
    return {"lane": lane}


@router.patch("/lanes/{lane_id:path}")
async def patch_lane(
    lane_id: str,
    payload: dict[str, Any] = Body(default_factory=dict),
    current_user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    require_global_resource_admin(current_user)
    try:
        lane = update_dynamic_lane(lane_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not lane:
        raise HTTPException(status_code=404, detail="dynamic_lane_not_found")
    clear_host_resource_snapshot_cache()
    return {"lane": lane}


@router.post("/lanes/{lane_id:path}/worker-target")
async def post_lane_worker_target(
    lane_id: str,
    payload: dict[str, Any] = Body(default_factory=dict),
    current_user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    desired_worker_count = int((payload or {}).get("desired_worker_count") or 0)
    return await set_lane_worker_target(
        lane_id,
        desired_worker_count,
        auth_context=current_user,
        workspace_id=(payload or {}).get("workspace_id"),
        allocation_id=(payload or {}).get("workspace_allocation_id")
        or (payload or {}).get("allocation_id"),
    )


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
async def pause_host_lane(
    lane_id: str,
    current_user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    require_global_resource_admin(current_user)
    return pause_lane(lane_id)


@router.post("/lanes/{lane_id:path}/resume")
async def resume_host_lane(
    lane_id: str,
    current_user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    require_global_resource_admin(current_user)
    return resume_lane(lane_id)


@router.get("/workspace-allocations")
async def get_workspace_allocations(
    workspace_id: Optional[str] = Query(None),
    lane_id: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    current_user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    context = build_resource_governance_context(
        current_user,
        workspace_id=workspace_id,
    )
    scoped_workspace_id = workspace_id
    if not is_global_resource_admin(current_user):
        scoped_workspace_id = context.get("workspace_id")
    elif workspace_id:
        scoped_workspace_id = require_workspace_resource_access(current_user, workspace_id)
    allocations = HostResourceWorkspaceAllocationStore("core").list_allocations(
        workspace_id=scoped_workspace_id,
        lane_id=lane_id,
        limit=limit,
    )
    effective = None
    if scoped_workspace_id:
        effective = build_workspace_allocation_effective_matrix(
            workspace_id=scoped_workspace_id,
        )
    return {
        "allocations": allocations,
        "effective": effective,
        "governance_context": context,
    }


@router.get("/allocation-blueprints")
async def get_allocation_blueprints(
    current_user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    require_global_resource_admin(current_user)
    return list_allocation_blueprints()


@router.get("/allocation-blueprints/{blueprint_id}")
async def get_allocation_blueprint_by_id(
    blueprint_id: str,
    current_user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    require_global_resource_admin(current_user)
    blueprint = get_allocation_blueprint(blueprint_id)
    if not blueprint:
        raise HTTPException(status_code=404, detail="allocation_blueprint_not_found")
    return {"blueprint": blueprint}


@router.post("/allocation-blueprints/{blueprint_id}/apply")
async def post_apply_allocation_blueprint(
    blueprint_id: str,
    payload: dict[str, Any] = Body(default_factory=dict),
    current_user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    workspace_id = require_workspace_resource_access(
        current_user,
        payload.get("workspace_id"),
    )
    try:
        result = apply_allocation_blueprint_to_workspace(
            workspace_id=workspace_id,
            blueprint_id=blueprint_id,
            actor_id=current_user.user_id,
        )
    except ValueError as exc:
        reason = str(exc)
        if reason == "allocation_blueprint_not_found":
            raise HTTPException(status_code=404, detail=reason) from exc
        raise HTTPException(status_code=422, detail=reason) from exc
    return {
        **result,
        "effective": build_workspace_allocation_effective_matrix(
            workspace_id=workspace_id,
        ),
        "governance_context": build_resource_governance_context(
            current_user,
            workspace_id=workspace_id,
        ),
    }


@router.put("/workspace-allocations/{allocation_id}")
async def put_workspace_allocation(
    allocation_id: str,
    payload: dict[str, Any] = Body(default_factory=dict),
    current_user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    workspace_id = payload.get("workspace_id")
    require_global_resource_admin(current_user)
    require_workspace_resource_access(current_user, workspace_id)
    allocation = HostResourceWorkspaceAllocationStore("core").upsert_allocation(
        payload,
        allocation_id=allocation_id,
        actor_id=current_user.user_id,
    )
    return {"allocation": allocation}


@router.post("/workspace-allocations/preview")
async def post_workspace_allocation_preview(
    payload: dict[str, Any] = Body(default_factory=dict),
    current_user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    workspace_id = require_workspace_resource_access(
        current_user,
        payload.get("workspace_id"),
    )
    decision = workspace_allocation_decision(
        workspace_id=workspace_id,
        lane_id=payload.get("lane_id"),
        allocation_id=payload.get("workspace_allocation_id") or payload.get("allocation_id"),
    )
    return {
        "workspace_allocation_decision": decision,
        "governance_context": build_resource_governance_context(
            current_user,
            workspace_id=workspace_id,
        ),
    }


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
    current_user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    return await build_route_intent_preview(payload or {}, auth_context=current_user)


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
    current_user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    return create_route_reservation(payload or {}, auth_context=current_user)


@router.delete("/route-reservations/{reservation_id}")
async def delete_route_reservation(
    reservation_id: str,
    current_user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    return cancel_route_reservation(reservation_id, auth_context=current_user)


@router.get("/runner-claim-gate")
async def get_runner_claim_gate_state() -> dict[str, Any]:
    return get_runner_claim_gate()


@router.post("/runner-claim-gate/pause")
async def pause_runner_claims(
    payload: Optional[dict[str, Any]] = Body(default=None),
    current_user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    require_global_resource_admin(current_user)
    return pause_runner_claim_gate(payload or {})


@router.post("/runner-claim-gate/resume")
async def resume_runner_claims(
    current_user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    require_global_resource_admin(current_user)
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
