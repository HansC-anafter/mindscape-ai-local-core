"""Record builders for core host resource objects."""

from __future__ import annotations

import copy
from typing import Any

from backend.app.models.object_runtime import ObjectInstanceRecord, ObjectRef
from backend.app.services.object_runtime.core_host_resources.catalog import (
    HOST_RESOURCE_LANE_KIND,
    OWNER_PACK,
    RESOURCE_BUDGET_POLICY_KIND,
    ROUTE_RESERVATION_KIND,
    WORKSPACE_RESOURCE_ALLOCATION_KIND,
    list_budget_policies,
)


def text_value(value: Any) -> str:
    return str(value or "").strip()


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [text for text in (text_value(item) for item in value) if text]


def _metadata(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _object_ref(*, workspace_id: str, object_kind: str, object_id: str) -> ObjectRef:
    return ObjectRef(
        uri=f"mindscape://{OWNER_PACK}/{object_kind}/{object_id}",
        owner_pack=OWNER_PACK,
        object_kind=object_kind,
        object_id=object_id,
        workspace_id=workspace_id,
    )


def _record(
    *,
    workspace_id: str,
    object_kind: str,
    object_id: str,
    title: str,
    subtitle: str | None = None,
    summary_text: str | None = None,
    labels: list[str] | None = None,
    mention_tokens: list[str] | None = None,
    search_parts: list[str] | None = None,
    affordance_verbs: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    updated_at: str | None = None,
) -> ObjectInstanceRecord:
    mention_text = " ".join(mention_tokens or [])
    search_text = " ".join(part for part in (search_parts or []) if part)
    return ObjectInstanceRecord(
        ref=_object_ref(
            workspace_id=workspace_id,
            object_kind=object_kind,
            object_id=object_id,
        ),
        title=title,
        subtitle=subtitle,
        summary_text=summary_text,
        labels=sorted({label for label in labels or [] if label}),
        mention_tokens=mention_tokens or [],
        mention_text=mention_text,
        search_text=search_text,
        affordance_verbs=affordance_verbs or [],
        metadata=metadata or {},
        updated_at=updated_at,
    )


def _bounded_limit(
    limit: int | None,
    *,
    default: int = 100,
    maximum: int = 100,
) -> int:
    try:
        raw = int(limit or default)
    except Exception:
        raw = default
    return max(1, min(raw, maximum))


def _filter_ids(
    records: list[ObjectInstanceRecord],
    object_ids: list[str] | None,
) -> list[ObjectInstanceRecord]:
    requested = {
        text_value(object_id)
        for object_id in list(object_ids or [])
        if text_value(object_id)
    }
    if not requested:
        return records
    return [record for record in records if record.ref.object_id in requested]


def lane_records(
    *,
    workspace_id: str,
    object_ids: list[str] | None = None,
    limit: int | None = None,
) -> list[ObjectInstanceRecord]:
    from backend.app.services.host_resources.manager import list_host_resource_lanes

    records: list[ObjectInstanceRecord] = []
    for lane in list_host_resource_lanes():
        if not isinstance(lane, dict):
            continue
        lane_id = text_value(lane.get("lane_id"))
        if not lane_id:
            continue
        requirements = _metadata(lane.get("requirements"))
        label = text_value(lane.get("label")) or lane_id
        kind = text_value(lane.get("kind")) or "lane"
        state = text_value(lane.get("state")) or "available"
        resource_flavor = text_value(
            lane.get("resource_flavor") or requirements.get("resource_flavor")
        )
        groups = _string_list(requirements.get("exclusive_groups"))
        summary = f"{label} is a {kind} host resource lane with state {state}."
        records.append(
            _record(
                workspace_id=workspace_id,
                object_kind=HOST_RESOURCE_LANE_KIND,
                object_id=lane_id,
                title=label,
                subtitle=f"{kind} lane",
                summary_text=summary,
                labels=[kind, state, resource_flavor, *groups],
                mention_tokens=[lane_id, label, kind, resource_flavor, *groups],
                search_parts=[
                    lane_id,
                    label,
                    kind,
                    state,
                    resource_flavor,
                    " ".join(groups),
                ],
                affordance_verbs=["preview_route_intent"],
                metadata={
                    "lane": lane,
                    "requirements": requirements,
                    "resource_groups": groups,
                    "read_source": "host_resource_lane_registry_and_cached_snapshot",
                },
            )
        )
    return _filter_ids(records[: _bounded_limit(limit)], object_ids)


def sync_host_resource_lane_index(
    *,
    workspace_id: str,
    object_ids: list[str] | None = None,
    limit: int = 100,
    **_: Any,
) -> dict[str, Any]:
    return {
        "source": "local_core.host_resource_lane",
        "records": lane_records(
            workspace_id=workspace_id,
            object_ids=object_ids,
            limit=limit,
        ),
    }


def budget_policy_records(
    *,
    workspace_id: str,
    object_ids: list[str] | None = None,
    limit: int | None = None,
) -> list[ObjectInstanceRecord]:
    records = [
        _record(
            workspace_id=workspace_id,
            object_kind=RESOURCE_BUDGET_POLICY_KIND,
            object_id=text_value(policy.get("policy_id")),
            title=text_value(policy.get("label")),
            subtitle="resource budget policy",
            summary_text=text_value(policy.get("description")),
            labels=[
                "resource_budget_policy",
                "route_reservation_required"
                if policy.get("requires_route_reservation")
                else "route_reservation_optional",
            ],
            mention_tokens=[
                text_value(policy.get("policy_id")),
                text_value(policy.get("label")),
                text_value(policy.get("description")),
            ],
            search_parts=[
                text_value(policy.get("policy_id")),
                text_value(policy.get("label")),
                text_value(policy.get("description")),
            ],
            metadata={"policy": copy.deepcopy(policy)},
        )
        for policy in list_budget_policies()
        if text_value(policy.get("policy_id"))
    ]
    return _filter_ids(records[: _bounded_limit(limit, maximum=25)], object_ids)


def sync_resource_budget_policy_index(
    *,
    workspace_id: str,
    object_ids: list[str] | None = None,
    limit: int = 25,
    **_: Any,
) -> dict[str, Any]:
    return {
        "source": "local_core.resource_budget_policy",
        "records": budget_policy_records(
            workspace_id=workspace_id,
            object_ids=object_ids,
            limit=limit,
        ),
    }


def allocation_records(
    *,
    workspace_id: str,
    object_ids: list[str] | None = None,
    limit: int | None = None,
) -> list[ObjectInstanceRecord]:
    try:
        from backend.app.services.host_resources.workspace_allocations import (
            HostResourceWorkspaceAllocationStore,
        )

        allocations = HostResourceWorkspaceAllocationStore("core").list_allocations(
            workspace_id=workspace_id,
            limit=_bounded_limit(limit, default=25, maximum=50),
        )
    except Exception:
        allocations = []
    records: list[ObjectInstanceRecord] = []
    for allocation in allocations:
        allocation_id = text_value(allocation.get("allocation_id"))
        if not allocation_id:
            continue
        lane_id = text_value(allocation.get("lane_id"))
        state = text_value(allocation.get("state")) or "enabled"
        label = text_value(allocation.get("label")) or allocation_id
        summary = (
            f"Workspace allocation {allocation_id} for lane {lane_id}"
            if lane_id
            else f"Workspace allocation {allocation_id}"
        )
        records.append(
            _record(
                workspace_id=workspace_id,
                object_kind=WORKSPACE_RESOURCE_ALLOCATION_KIND,
                object_id=allocation_id,
                title=label,
                subtitle=f"allocation for {lane_id}" if lane_id else "workspace allocation",
                summary_text=summary,
                labels=["workspace_resource_allocation", state, lane_id],
                mention_tokens=[allocation_id, lane_id, label, state],
                search_parts=[allocation_id, lane_id, label, state],
                metadata={"allocation": allocation},
                updated_at=text_value(allocation.get("updated_at")) or None,
            )
        )
    return _filter_ids(records, object_ids)


def sync_workspace_resource_allocation_index(
    *,
    workspace_id: str,
    object_ids: list[str] | None = None,
    limit: int = 25,
    **_: Any,
) -> dict[str, Any]:
    return {
        "source": "local_core.workspace_resource_allocation",
        "records": allocation_records(
            workspace_id=workspace_id,
            object_ids=object_ids,
            limit=limit,
        ),
    }


def route_reservation_records(
    *,
    workspace_id: str,
    object_ids: list[str] | None = None,
    limit: int | None = None,
) -> list[ObjectInstanceRecord]:
    from backend.app.services.host_resources.manager import list_active_route_reservations

    records: list[ObjectInstanceRecord] = []
    for reservation in list_active_route_reservations():
        if not isinstance(reservation, dict):
            continue
        reservation_id = text_value(reservation.get("reservation_id"))
        if not reservation_id:
            continue
        route_request = _metadata(reservation.get("route_request"))
        reservation_workspace_id = text_value(route_request.get("workspace_id"))
        if reservation_workspace_id and reservation_workspace_id != workspace_id:
            continue
        target_lane = text_value(route_request.get("target_lane"))
        state = text_value(reservation.get("state")) or "reserved_waiting"
        records.append(
            _record(
                workspace_id=workspace_id,
                object_kind=ROUTE_RESERVATION_KIND,
                object_id=reservation_id,
                title=f"Route reservation {reservation_id}",
                subtitle=f"{state} for {target_lane}" if target_lane else state,
                summary_text=(
                    f"Active route reservation for {target_lane}."
                    if target_lane
                    else "Active route reservation."
                ),
                labels=["route_reservation", state, target_lane],
                mention_tokens=[reservation_id, target_lane, state],
                search_parts=[reservation_id, target_lane, state],
                metadata={"reservation": reservation, "route_request": route_request},
                updated_at=text_value(reservation.get("updated_at")) or None,
            )
        )
    limited = records[: _bounded_limit(limit, default=50, maximum=100)]
    return _filter_ids(limited, object_ids)


def sync_route_reservation_index(
    *,
    workspace_id: str,
    object_ids: list[str] | None = None,
    limit: int = 50,
    **_: Any,
) -> dict[str, Any]:
    return {
        "source": "local_core.route_reservation",
        "records": route_reservation_records(
            workspace_id=workspace_id,
            object_ids=object_ids,
            limit=limit,
        ),
    }


__all__ = [
    "text_value",
    "lane_records",
    "sync_host_resource_lane_index",
    "budget_policy_records",
    "sync_resource_budget_policy_index",
    "allocation_records",
    "sync_workspace_resource_allocation_index",
    "route_reservation_records",
    "sync_route_reservation_index",
]
