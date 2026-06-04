"""Workspace allocation ledger for host resource lanes."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import text

from backend.app.services.stores.postgres_base import PostgresStoreBase


ENABLED_STATES = {"enabled"}


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


def _clean_state(value: Any) -> str:
    normalized = (_clean_string(value) or "enabled").lower()
    return normalized if normalized in {"enabled", "paused", "disabled"} else "enabled"


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _allocation_lane_id(queue_shard: str | None, task_family: str | None) -> str | None:
    normalized_queue_shard = _clean_string(queue_shard)
    normalized_task_family = _clean_string(task_family)
    if not normalized_queue_shard or not normalized_task_family:
        return None
    return f"quota:{normalized_queue_shard}:{normalized_task_family}"


class HostResourceWorkspaceAllocationStore(PostgresStoreBase):
    def _row_to_allocation(self, row: Any) -> dict[str, Any]:
        mapping = dict(row._mapping) if hasattr(row, "_mapping") else dict(row)
        return {
            "allocation_id": mapping.get("allocation_id"),
            "workspace_id": mapping.get("workspace_id"),
            "lane_id": mapping.get("lane_id"),
            "label": mapping.get("label"),
            "max_worker_target": mapping.get("max_worker_target"),
            "max_concurrency": mapping.get("max_concurrency"),
            "queue_shard": mapping.get("queue_shard"),
            "task_family": mapping.get("task_family"),
            "max_parallel_task_claims": mapping.get("max_parallel_task_claims"),
            "share_policy": mapping.get("share_policy"),
            "priority_ceiling": mapping.get("priority_ceiling"),
            "blueprint_id": mapping.get("blueprint_id"),
            "blueprint_entry_id": mapping.get("blueprint_entry_id"),
            "applied_at": self.to_isoformat(mapping.get("applied_at")),
            "state": mapping.get("state"),
            "metadata": self.deserialize_json(mapping.get("metadata"), default={}),
            "created_by": mapping.get("created_by"),
            "updated_by": mapping.get("updated_by"),
            "created_at": self.to_isoformat(mapping.get("created_at")),
            "updated_at": self.to_isoformat(mapping.get("updated_at")),
        }

    def list_allocations(
        self,
        *,
        workspace_id: str | None = None,
        lane_id: str | None = None,
        queue_shard: str | None = None,
        task_family: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: dict[str, Any] = {"limit": max(1, min(int(limit or 100), 500))}
        if _clean_string(workspace_id):
            clauses.append("workspace_id = :workspace_id")
            params["workspace_id"] = _clean_string(workspace_id)
        if _clean_string(lane_id):
            clauses.append("lane_id = :lane_id")
            params["lane_id"] = _clean_string(lane_id)
        if _clean_string(queue_shard):
            clauses.append("queue_shard = :queue_shard")
            params["queue_shard"] = _clean_string(queue_shard)
        if _clean_string(task_family):
            clauses.append("task_family = :task_family")
            params["task_family"] = _clean_string(task_family)
        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.get_connection() as conn:
            rows = conn.execute(
                text(
                    f"""
                    SELECT *
                    FROM host_resource_workspace_allocations
                    {where_sql}
                    ORDER BY updated_at DESC, allocation_id
                    LIMIT :limit
                    """
                ),
                params,
            ).fetchall()
        return [self._row_to_allocation(row) for row in rows]

    def get_allocation(self, allocation_id: str) -> dict[str, Any] | None:
        normalized_id = _clean_string(allocation_id)
        if not normalized_id:
            return None
        with self.get_connection() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT *
                    FROM host_resource_workspace_allocations
                    WHERE allocation_id = :allocation_id
                    """
                ),
                {"allocation_id": normalized_id},
            ).fetchone()
        return self._row_to_allocation(row) if row else None

    def find_allocation_for_lane(
        self,
        *,
        workspace_id: str,
        lane_id: str,
        allocation_id: str | None = None,
    ) -> dict[str, Any] | None:
        normalized_workspace_id = _clean_string(workspace_id)
        normalized_lane_id = _clean_string(lane_id)
        normalized_allocation_id = _clean_string(allocation_id)
        if not normalized_workspace_id or not normalized_lane_id:
            return None
        clauses = [
            "workspace_id = :workspace_id",
            "lane_id = :lane_id",
        ]
        params: dict[str, Any] = {
            "workspace_id": normalized_workspace_id,
            "lane_id": normalized_lane_id,
        }
        if normalized_allocation_id:
            clauses.append("allocation_id = :allocation_id")
            params["allocation_id"] = normalized_allocation_id
        with self.get_connection() as conn:
            row = conn.execute(
                text(
                    f"""
                    SELECT *
                    FROM host_resource_workspace_allocations
                    WHERE {' AND '.join(clauses)}
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """
                ),
                params,
            ).fetchone()
        return self._row_to_allocation(row) if row else None

    def find_allocation_for_task_family(
        self,
        *,
        workspace_id: str,
        queue_shard: str,
        task_family: str,
    ) -> dict[str, Any] | None:
        normalized_workspace_id = _clean_string(workspace_id)
        normalized_queue_shard = _clean_string(queue_shard)
        normalized_task_family = _clean_string(task_family)
        if not normalized_workspace_id or not normalized_queue_shard or not normalized_task_family:
            return None
        with self.get_connection() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT *
                    FROM host_resource_workspace_allocations
                    WHERE workspace_id = :workspace_id
                      AND queue_shard = :queue_shard
                      AND task_family = :task_family
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """
                ),
                {
                    "workspace_id": normalized_workspace_id,
                    "queue_shard": normalized_queue_shard,
                    "task_family": normalized_task_family,
                },
            ).fetchone()
        return self._row_to_allocation(row) if row else None

    def upsert_allocation(
        self,
        payload: dict[str, Any],
        *,
        allocation_id: str | None = None,
        actor_id: str | None = None,
    ) -> dict[str, Any]:
        normalized_workspace_id = _clean_string(payload.get("workspace_id"))
        normalized_queue_shard = _clean_string(payload.get("queue_shard"))
        normalized_task_family = _clean_string(payload.get("task_family"))
        normalized_lane_id = (
            _clean_string(payload.get("lane_id"))
            or _allocation_lane_id(normalized_queue_shard, normalized_task_family)
        )
        if not normalized_workspace_id or not normalized_lane_id:
            raise ValueError("workspace_id_and_lane_id_required")
        normalized_allocation_id = (
            _clean_string(allocation_id)
            or _clean_string(payload.get("allocation_id"))
            or f"hra_{uuid.uuid4().hex}"
        )
        max_worker_target = max(
            0,
            _clean_int(payload.get("max_worker_target"), default=0),
        )
        max_concurrency = max(
            1,
            _clean_int(payload.get("max_concurrency"), default=1),
        )
        max_parallel_task_claims = max(
            1,
            _clean_int(
                payload.get("max_parallel_task_claims"),
                default=max(max_worker_target, max_concurrency, 1),
            ),
        )
        if payload.get("max_parallel_task_claims") is not None:
            max_worker_target = max_parallel_task_claims
            max_concurrency = max_parallel_task_claims
        metadata = _dict(payload.get("metadata"))
        params = {
            "allocation_id": normalized_allocation_id,
            "workspace_id": normalized_workspace_id,
            "lane_id": normalized_lane_id,
            "label": _clean_string(payload.get("label")) or normalized_lane_id,
            "max_worker_target": max_worker_target,
            "max_concurrency": max_concurrency,
            "queue_shard": normalized_queue_shard,
            "task_family": normalized_task_family,
            "max_parallel_task_claims": max_parallel_task_claims,
            "share_policy": _clean_string(payload.get("share_policy")) or "shared_pool",
            "priority_ceiling": _clean_string(payload.get("priority_ceiling")) or "normal",
            "blueprint_id": _clean_string(payload.get("blueprint_id")),
            "blueprint_entry_id": _clean_string(payload.get("blueprint_entry_id")),
            "state": _clean_state(payload.get("state")),
            "metadata": self.serialize_json(metadata),
            "actor_id": _clean_string(actor_id),
        }
        conflict_sql = (
            """
                    ON CONFLICT (workspace_id, queue_shard, task_family)
                    WHERE queue_shard IS NOT NULL AND task_family IS NOT NULL
                    DO UPDATE SET
                        lane_id = EXCLUDED.lane_id,
                        label = EXCLUDED.label,
                        max_worker_target = EXCLUDED.max_worker_target,
                        max_concurrency = EXCLUDED.max_concurrency,
                        queue_shard = EXCLUDED.queue_shard,
                        task_family = EXCLUDED.task_family,
                        max_parallel_task_claims = EXCLUDED.max_parallel_task_claims,
                        share_policy = EXCLUDED.share_policy,
                        priority_ceiling = EXCLUDED.priority_ceiling,
                        blueprint_id = EXCLUDED.blueprint_id,
                        blueprint_entry_id = EXCLUDED.blueprint_entry_id,
                        applied_at = NOW(),
                        state = EXCLUDED.state,
                        metadata = EXCLUDED.metadata,
                        updated_by = EXCLUDED.updated_by,
                        updated_at = NOW()
            """
            if normalized_queue_shard and normalized_task_family
            else """
                    ON CONFLICT (workspace_id, lane_id) DO UPDATE SET
                        label = EXCLUDED.label,
                        max_worker_target = EXCLUDED.max_worker_target,
                        max_concurrency = EXCLUDED.max_concurrency,
                        queue_shard = EXCLUDED.queue_shard,
                        task_family = EXCLUDED.task_family,
                        max_parallel_task_claims = EXCLUDED.max_parallel_task_claims,
                        share_policy = EXCLUDED.share_policy,
                        priority_ceiling = EXCLUDED.priority_ceiling,
                        blueprint_id = EXCLUDED.blueprint_id,
                        blueprint_entry_id = EXCLUDED.blueprint_entry_id,
                        applied_at = NOW(),
                        state = EXCLUDED.state,
                        metadata = EXCLUDED.metadata,
                        updated_by = EXCLUDED.updated_by,
                        updated_at = NOW()
            """
        )
        with self.transaction() as conn:
            row = conn.execute(
                text(
                    f"""
                    INSERT INTO host_resource_workspace_allocations (
                        allocation_id,
                        workspace_id,
                        lane_id,
                        label,
                        max_worker_target,
                        max_concurrency,
                        queue_shard,
                        task_family,
                        max_parallel_task_claims,
                        share_policy,
                        priority_ceiling,
                        blueprint_id,
                        blueprint_entry_id,
                        applied_at,
                        state,
                        metadata,
                        created_by,
                        updated_by
                    ) VALUES (
                        :allocation_id,
                        :workspace_id,
                        :lane_id,
                        :label,
                        :max_worker_target,
                        :max_concurrency,
                        :queue_shard,
                        :task_family,
                        :max_parallel_task_claims,
                        :share_policy,
                        :priority_ceiling,
                        :blueprint_id,
                        :blueprint_entry_id,
                        NOW(),
                        :state,
                        CAST(:metadata AS jsonb),
                        :actor_id,
                        :actor_id
                    )
                    {conflict_sql}
                    RETURNING *
                    """
                ),
                params,
            ).fetchone()
        return self._row_to_allocation(row)


def resolve_workspace_allocation_for_lane(
    *,
    workspace_id: str,
    lane_id: str,
    allocation_id: str | None = None,
) -> dict[str, Any] | None:
    return HostResourceWorkspaceAllocationStore("core").find_allocation_for_lane(
        workspace_id=workspace_id,
        lane_id=lane_id,
        allocation_id=allocation_id,
    )


def workspace_allocation_decision(
    *,
    workspace_id: str | None,
    lane_id: str | None,
    allocation_id: str | None = None,
) -> dict[str, Any]:
    if not _clean_string(workspace_id):
        return {"accepted": False, "reason": "workspace_id_required"}
    if not _clean_string(lane_id):
        return {"accepted": False, "reason": "target_lane_required"}
    allocation = resolve_workspace_allocation_for_lane(
        workspace_id=str(workspace_id),
        lane_id=str(lane_id),
        allocation_id=allocation_id,
    )
    if not allocation:
        return {
            "accepted": False,
            "reason": "workspace_allocation_required",
            "workspace_id": workspace_id,
            "lane_id": lane_id,
            "allocation_id": allocation_id,
        }
    if allocation.get("state") not in ENABLED_STATES:
        return {
            "accepted": False,
            "reason": "workspace_allocation_disabled",
            "allocation": allocation,
        }
    if int(allocation.get("max_worker_target") or 0) <= 0:
        return {
            "accepted": False,
            "reason": "workspace_allocation_quota_zero",
            "allocation": allocation,
        }
    return {
        "accepted": True,
        "reason": "workspace_allocation_available",
        "allocation": allocation,
    }
