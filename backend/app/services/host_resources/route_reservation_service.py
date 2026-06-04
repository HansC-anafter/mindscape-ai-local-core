"""Governed route reservation service for host resources."""

from __future__ import annotations

from datetime import timedelta
from typing import Any
import uuid

from fastapi import HTTPException

from backend.app.dependencies.auth import AuthContext
from backend.app.services.resource_governance import (
    build_resource_governance_context,
    is_global_resource_admin,
    require_workspace_resource_access,
)

from . import manager as manager_module
from .workspace_allocations import workspace_allocation_decision


def _clean_string(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _payload_map(payload: dict[str, Any] | None) -> dict[str, Any]:
    return dict(payload) if isinstance(payload, dict) else {}


def _workspace_input(
    payload: dict[str, Any],
    route_request: dict[str, Any],
) -> tuple[str | None, str | None]:
    workspace_id = _clean_string(
        route_request.get("workspace_id")
        or payload.get("workspace_id")
    )
    allocation_id = _clean_string(
        route_request.get("workspace_allocation_id")
        or route_request.get("allocation_id")
        or payload.get("workspace_allocation_id")
        or payload.get("allocation_id")
    )
    return workspace_id, allocation_id


def _ensure_workspace_allocation(
    *,
    payload: dict[str, Any],
    route_request: dict[str, Any],
    auth_context: AuthContext | None,
) -> dict[str, Any]:
    workspace_id, allocation_id = _workspace_input(payload, route_request)
    target_lane = _clean_string(route_request.get("target_lane"))
    if auth_context is None:
        return {"accepted": True, "reason": "compatibility_no_auth_context"}

    governance_context = build_resource_governance_context(
        auth_context,
        workspace_id=workspace_id,
    )
    if governance_context.get("is_global_admin") and not workspace_id:
        return {
            "accepted": True,
            "reason": "global_admin_allocation_bypass",
            "governance_context": governance_context,
        }

    workspace_id = require_workspace_resource_access(auth_context, workspace_id)
    decision = workspace_allocation_decision(
        workspace_id=workspace_id,
        lane_id=target_lane,
        allocation_id=allocation_id,
    )
    if not decision.get("accepted"):
        raise HTTPException(status_code=403, detail=decision)
    allocation = decision.get("allocation") if isinstance(decision.get("allocation"), dict) else {}
    route_request["workspace_id"] = workspace_id
    route_request["workspace_allocation_id"] = allocation.get("allocation_id")
    return {
        **decision,
        "governance_context": governance_context,
    }


def create_route_reservation(
    payload: dict[str, Any] | None = None,
    *,
    auth_context: AuthContext | None = None,
) -> dict[str, Any]:
    normalized_payload = _payload_map(payload)
    route_request = manager_module._normalized_route_request(normalized_payload)
    allocation_decision = _ensure_workspace_allocation(
        payload=normalized_payload,
        route_request=route_request,
        auth_context=auth_context,
    )
    reservation_id = f"hostres_{uuid.uuid4().hex}"
    ttl_seconds = manager_module._ttl_seconds_from_payload(normalized_payload)
    created_at = manager_module._utc_now()
    reservation = {
        "reservation_id": reservation_id,
        "state": "reserved_waiting",
        "created_at": created_at.isoformat(),
        "updated_at": created_at.isoformat(),
        "expires_at": (created_at + timedelta(seconds=ttl_seconds)).isoformat(),
        "ttl_seconds": ttl_seconds,
        "route_request": route_request,
        "workspace_allocation_decision": allocation_decision,
    }
    ledger_persisted = manager_module._save_reservation_to_ledger(reservation)
    manager_module._append_reservation_event(
        "reservation_created",
        reservation=reservation,
        payload={"reservation": reservation},
    )
    reservation["ledger_persisted"] = ledger_persisted
    manager_module._write_route_projection(reservation)
    return reservation


def cancel_route_reservation(
    reservation_id: str,
    *,
    auth_context: AuthContext | None = None,
) -> dict[str, Any]:
    reservation = manager_module._route_reservations.get(reservation_id)
    if not reservation:
        persisted = manager_module._read_json_map(manager_module.ROUTE_RESERVATIONS_KEY)
        raw_reservation = persisted.get(reservation_id)
        if isinstance(raw_reservation, dict):
            reservation = raw_reservation
    if not reservation:
        store = manager_module._get_route_reservation_store()
        if store:
            try:
                reservation = store.cancel_reservation(reservation_id)
            except Exception as exc:
                manager_module.logger.debug(
                    "Failed to cancel durable host resource reservation: %s",
                    exc,
                )
                reservation = None
        if not reservation:
            return {"reservation_id": reservation_id, "state": "not_found"}

    if auth_context is not None:
        route_request = reservation.get("route_request") if isinstance(reservation, dict) else {}
        workspace_id = _clean_string(route_request.get("workspace_id"))
        if workspace_id:
            require_workspace_resource_access(auth_context, workspace_id)
        elif not is_global_resource_admin(auth_context):
            raise HTTPException(
                status_code=403,
                detail={"reason": "global_resource_admin_required"},
            )

    reservation = dict(reservation)
    cancelled_at = manager_module._utc_now_iso()
    reservation["state"] = "cancelled"
    reservation["cancelled_at"] = cancelled_at
    reservation["updated_at"] = cancelled_at
    ledger_persisted = False
    store = manager_module._get_route_reservation_store()
    if store:
        try:
            durable = store.cancel_reservation(reservation_id, cancelled_at=cancelled_at)
            if isinstance(durable, dict):
                reservation = {**reservation, **durable}
            ledger_persisted = bool(durable)
        except Exception as exc:
            manager_module.logger.debug(
                "Failed to update durable host resource cancellation: %s",
                exc,
            )
    manager_module._append_reservation_event(
        "reservation_cancelled",
        reservation=reservation,
        payload={"reservation_id": reservation_id},
    )
    reservation["ledger_persisted"] = ledger_persisted
    manager_module._write_route_projection(reservation)
    return reservation
