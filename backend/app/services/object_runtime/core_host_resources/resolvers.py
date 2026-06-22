"""Resolvers for core host resource object summaries and actions."""

from __future__ import annotations

from typing import Any

from backend.app.models.object_runtime import ObjectInstanceRecord
from backend.app.services.object_runtime.core_host_resources.catalog import (
    HOST_RESOURCE_LANE_KIND,
)
from backend.app.services.object_runtime.core_host_resources.records import (
    allocation_records,
    budget_policy_records,
    lane_records,
    route_reservation_records,
)


def _summary_from_records(
    *,
    records: list[ObjectInstanceRecord],
    object_id: str,
) -> dict[str, Any]:
    for record in records:
        if record.ref.object_id == object_id:
            return record.model_dump(exclude_none=True)
    return {}


def resolve_host_resource_lane_summary(
    *,
    workspace_id: str,
    object_id: str,
    **_: Any,
) -> dict[str, Any]:
    return _summary_from_records(
        records=lane_records(workspace_id=workspace_id, object_ids=[object_id], limit=1),
        object_id=object_id,
    )


def resolve_resource_budget_policy_summary(
    *,
    workspace_id: str,
    object_id: str,
    **_: Any,
) -> dict[str, Any]:
    return _summary_from_records(
        records=budget_policy_records(
            workspace_id=workspace_id,
            object_ids=[object_id],
            limit=1,
        ),
        object_id=object_id,
    )


def resolve_workspace_resource_allocation_summary(
    *,
    workspace_id: str,
    object_id: str,
    **_: Any,
) -> dict[str, Any]:
    return _summary_from_records(
        records=allocation_records(
            workspace_id=workspace_id,
            object_ids=[object_id],
            limit=1,
        ),
        object_id=object_id,
    )


def resolve_route_reservation_summary(
    *,
    workspace_id: str,
    object_id: str,
    **_: Any,
) -> dict[str, Any]:
    return _summary_from_records(
        records=route_reservation_records(
            workspace_id=workspace_id,
            object_ids=[object_id],
            limit=1,
        ),
        object_id=object_id,
    )


def resolve_host_resource_lane_actions(*, object_id: str, **_: Any) -> dict[str, Any]:
    return {
        "actions": [
            {
                "action_code": "preview_route_intent",
                "label": "Preview route intent",
                "description": "Preview route admission without mutating worker or pool state.",
                "verb": "preview_route_intent",
                "mode": "read_only",
                "requires_review": False,
                "target_kind": HOST_RESOURCE_LANE_KIND,
            }
        ]
    }


__all__ = [
    "resolve_host_resource_lane_summary",
    "resolve_resource_budget_policy_summary",
    "resolve_workspace_resource_allocation_summary",
    "resolve_route_reservation_summary",
    "resolve_host_resource_lane_actions",
]
