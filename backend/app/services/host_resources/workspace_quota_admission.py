"""Workspace quota admission for shared host resource pools."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text

from backend.app.services.host_resources.workspace_allocations import (
    HostResourceWorkspaceAllocationStore,
)
from backend.app.services.stores.postgres_base import PostgresStoreBase


WORKSPACE_QUOTA_EXHAUSTED_REASON = "workspace_allocation_quota_exhausted"
WORKSPACE_ALLOCATION_REQUIRED_REASON = "workspace_allocation_required"
WORKSPACE_ALLOCATION_DISABLED_REASON = "workspace_allocation_disabled"


@dataclass(frozen=True)
class WorkspaceQuotaAdmissionDecision:
    allow: bool
    reason: str
    allocation: dict[str, Any] | None = None
    active_count: int = 0
    max_parallel_task_claims: int = 0
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "allow": self.allow,
            "reason": self.reason,
            "allocation": self.allocation,
            "active_count": self.active_count,
            "max_parallel_task_claims": self.max_parallel_task_claims,
            "payload": self.payload,
        }


def _clean_string(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _clean_int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _task_context(task: Any) -> dict[str, Any]:
    context = getattr(task, "execution_context", None)
    return context if isinstance(context, dict) else {}


def _task_identity(task: Any) -> dict[str, str | None]:
    context = _task_context(task)
    return {
        "task_id": _clean_string(getattr(task, "id", None) or context.get("task_id")),
        "workspace_id": _clean_string(
            getattr(task, "workspace_id", None) or context.get("workspace_id")
        ),
        "queue_shard": _clean_string(
            getattr(task, "queue_shard", None) or context.get("queue_shard")
        ),
        "pack_id": _clean_string(
            getattr(task, "pack_id", None)
            or context.get("pack_id")
            or context.get("playbook_code")
        ),
        "playbook_code": _clean_string(context.get("playbook_code")),
        "task_type": _clean_string(
            getattr(task, "task_type", None) or context.get("task_type")
        ),
    }


def _selectors_for_allocation(allocation: dict[str, Any]) -> list[str]:
    metadata = allocation.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    selectors = metadata.get("task_selectors")
    if not isinstance(selectors, list):
        selectors = []
    return [
        normalized
        for normalized in (_clean_string(selector) for selector in selectors)
        if normalized
    ]


def _allocation_matches_task(
    allocation: dict[str, Any],
    *,
    pack_id: str | None,
    playbook_code: str | None,
    task_type: str | None,
) -> bool:
    selectors = _selectors_for_allocation(allocation)
    if not selectors:
        return True
    candidates = {
        value
        for value in (
            _clean_string(pack_id),
            _clean_string(playbook_code),
            _clean_string(task_type),
        )
        if value
    }
    return bool(candidates.intersection(selectors))


class WorkspaceQuotaUsageStore(PostgresStoreBase):
    def count_active_tasks(
        self,
        *,
        workspace_id: str,
        queue_shard: str,
        selectors: list[str],
    ) -> int:
        selector_clauses: list[str] = []
        params: dict[str, Any] = {
            "workspace_id": workspace_id,
            "queue_shard": queue_shard,
            "running_status": "running",
        }
        if selectors:
            selector_params = {}
            placeholders = []
            for index, selector in enumerate(selectors):
                key = f"selector_{index}"
                selector_params[key] = selector
                placeholders.append(f":{key}")
            params.update(selector_params)
            selector_list = ", ".join(placeholders)
            selector_clauses.append(
                f"""
                (
                    pack_id IN ({selector_list})
                    OR execution_context->>'playbook_code' IN ({selector_list})
                    OR task_type IN ({selector_list})
                )
                """
            )
        selector_sql = (
            f"AND {' AND '.join(selector_clauses)}" if selector_clauses else ""
        )
        with self.get_connection() as conn:
            value = conn.execute(
                text(
                    f"""
                    SELECT COUNT(*)::int
                    FROM tasks
                    WHERE workspace_id = :workspace_id
                      AND queue_shard = :queue_shard
                      AND status = :running_status
                      {selector_sql}
                    """
                ),
                params,
            ).scalar()
        return _clean_int(value, default=0)


def decide_workspace_quota_admission_for_task(
    task: Any,
    *,
    allocation_store: HostResourceWorkspaceAllocationStore | None = None,
    usage_store: WorkspaceQuotaUsageStore | None = None,
) -> WorkspaceQuotaAdmissionDecision:
    identity = _task_identity(task)
    workspace_id = identity.get("workspace_id")
    queue_shard = identity.get("queue_shard")
    if not workspace_id or not queue_shard:
        return WorkspaceQuotaAdmissionDecision(
            allow=True,
            reason="workspace_quota_identity_not_available",
            payload=identity,
        )

    store = allocation_store or HostResourceWorkspaceAllocationStore("core")
    allocations = store.list_allocations(
        workspace_id=workspace_id,
        queue_shard=queue_shard,
        limit=50,
    )
    matching_allocations = [
        allocation
        for allocation in allocations
        if _allocation_matches_task(
            allocation,
            pack_id=identity.get("pack_id"),
            playbook_code=identity.get("playbook_code"),
            task_type=identity.get("task_type"),
        )
    ]
    if not matching_allocations:
        return WorkspaceQuotaAdmissionDecision(
            allow=False,
            reason=WORKSPACE_ALLOCATION_REQUIRED_REASON,
            payload=identity,
        )

    allocation = matching_allocations[0]
    if allocation.get("state") != "enabled":
        return WorkspaceQuotaAdmissionDecision(
            allow=False,
            reason=WORKSPACE_ALLOCATION_DISABLED_REASON,
            allocation=allocation,
            payload=identity,
        )

    max_parallel_task_claims = max(
        1,
        _clean_int(allocation.get("max_parallel_task_claims"), default=1),
    )
    selectors = _selectors_for_allocation(allocation)
    active_count = (usage_store or WorkspaceQuotaUsageStore("core")).count_active_tasks(
        workspace_id=workspace_id,
        queue_shard=queue_shard,
        selectors=selectors,
    )
    if active_count >= max_parallel_task_claims:
        return WorkspaceQuotaAdmissionDecision(
            allow=False,
            reason=WORKSPACE_QUOTA_EXHAUSTED_REASON,
            allocation=allocation,
            active_count=active_count,
            max_parallel_task_claims=max_parallel_task_claims,
            payload=identity,
        )
    return WorkspaceQuotaAdmissionDecision(
        allow=True,
        reason="workspace_allocation_available",
        allocation=allocation,
        active_count=active_count,
        max_parallel_task_claims=max_parallel_task_claims,
        payload=identity,
    )
