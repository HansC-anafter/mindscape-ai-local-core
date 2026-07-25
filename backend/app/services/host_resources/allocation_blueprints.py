"""Workspace host resource allocation blueprint service."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

from backend.app.services.host_resources.queue_utilization import (
    get_latest_queue_utilization_snapshot,
)
from backend.app.services.host_resources.workspace_allocations import (
    HostResourceWorkspaceAllocationStore,
)
from backend.app.services.stores.postgres_base import PostgresStoreBase


DEFAULT_ALLOCATION_BLUEPRINT_ID = "local-core-workspace-default"


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


class HostResourceAllocationBlueprintStore(PostgresStoreBase):
    """Postgres store for allocation blueprints and applications."""

    def _row_to_blueprint(self, row: Any) -> dict[str, Any]:
        mapping = dict(row._mapping) if hasattr(row, "_mapping") else dict(row)
        return {
            "blueprint_id": mapping.get("blueprint_id"),
            "label": mapping.get("label"),
            "scope": mapping.get("scope"),
            "state": mapping.get("state"),
            "metadata": self.deserialize_json(mapping.get("metadata"), default={}),
            "created_at": self.to_isoformat(mapping.get("created_at")),
            "updated_at": self.to_isoformat(mapping.get("updated_at")),
        }

    def _row_to_entry(self, row: Any) -> dict[str, Any]:
        mapping = dict(row._mapping) if hasattr(row, "_mapping") else dict(row)
        return {
            "blueprint_entry_id": mapping.get("blueprint_entry_id"),
            "blueprint_id": mapping.get("blueprint_id"),
            "queue_shard": mapping.get("queue_shard"),
            "task_family": mapping.get("task_family"),
            "label": mapping.get("label"),
            "max_parallel_task_claims": mapping.get("max_parallel_task_claims"),
            "share_policy": mapping.get("share_policy"),
            "priority_ceiling": mapping.get("priority_ceiling"),
            "task_selectors": self.deserialize_json(
                mapping.get("task_selectors"),
                default=[],
            ),
            "metadata": self.deserialize_json(mapping.get("metadata"), default={}),
            "created_at": self.to_isoformat(mapping.get("created_at")),
            "updated_at": self.to_isoformat(mapping.get("updated_at")),
        }

    def _row_to_application(self, row: Any) -> dict[str, Any]:
        mapping = dict(row._mapping) if hasattr(row, "_mapping") else dict(row)
        return {
            "application_id": mapping.get("application_id"),
            "workspace_id": mapping.get("workspace_id"),
            "blueprint_id": mapping.get("blueprint_id"),
            "state": mapping.get("state"),
            "applied_by": mapping.get("applied_by"),
            "applied_at": self.to_isoformat(mapping.get("applied_at")),
            "metadata": self.deserialize_json(mapping.get("metadata"), default={}),
        }

    def list_blueprints(self, *, include_disabled: bool = False) -> list[dict[str, Any]]:
        clauses = [] if include_disabled else ["state = 'enabled'"]
        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.get_connection() as conn:
            rows = conn.execute(
                text(
                    f"""
                    SELECT *
                    FROM host_resource_allocation_blueprints
                    {where_sql}
                    ORDER BY scope, label, blueprint_id
                    """
                )
            ).fetchall()
        return [self._row_to_blueprint(row) for row in rows]

    def get_blueprint(self, blueprint_id: str) -> dict[str, Any] | None:
        normalized_blueprint_id = _clean_string(blueprint_id)
        if not normalized_blueprint_id:
            return None
        with self.get_connection() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT *
                    FROM host_resource_allocation_blueprints
                    WHERE blueprint_id = :blueprint_id
                    """
                ),
                {"blueprint_id": normalized_blueprint_id},
            ).fetchone()
        return self._row_to_blueprint(row) if row else None

    def list_entries(self, blueprint_id: str) -> list[dict[str, Any]]:
        normalized_blueprint_id = _clean_string(blueprint_id)
        if not normalized_blueprint_id:
            return []
        with self.get_connection() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT *
                    FROM host_resource_allocation_blueprint_entries
                    WHERE blueprint_id = :blueprint_id
                    ORDER BY queue_shard, task_family
                    """
                ),
                {"blueprint_id": normalized_blueprint_id},
            ).fetchall()
        return [self._row_to_entry(row) for row in rows]

    def list_applications(self, *, workspace_id: str) -> list[dict[str, Any]]:
        normalized_workspace_id = _clean_string(workspace_id)
        if not normalized_workspace_id:
            return []
        with self.get_connection() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT *
                    FROM host_resource_workspace_allocation_applications
                    WHERE workspace_id = :workspace_id
                    ORDER BY applied_at DESC, blueprint_id
                    """
                ),
                {"workspace_id": normalized_workspace_id},
            ).fetchall()
        return [self._row_to_application(row) for row in rows]

    def record_application(
        self,
        *,
        workspace_id: str,
        blueprint_id: str,
        actor_id: str | None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_workspace_id = _clean_string(workspace_id)
        normalized_blueprint_id = _clean_string(blueprint_id)
        if not normalized_workspace_id or not normalized_blueprint_id:
            raise ValueError("workspace_id_and_blueprint_id_required")
        application_id = (
            f"hrwaa_{normalized_workspace_id.replace('-', '')}_{normalized_blueprint_id}"
        )
        with self.transaction() as conn:
            row = conn.execute(
                text(
                    """
                    INSERT INTO host_resource_workspace_allocation_applications (
                        application_id,
                        workspace_id,
                        blueprint_id,
                        state,
                        applied_by,
                        applied_at,
                        metadata
                    ) VALUES (
                        :application_id,
                        :workspace_id,
                        :blueprint_id,
                        'applied',
                        :actor_id,
                        NOW(),
                        CAST(:metadata AS jsonb)
                    )
                    ON CONFLICT (workspace_id, blueprint_id) DO UPDATE SET
                        state = EXCLUDED.state,
                        applied_by = EXCLUDED.applied_by,
                        applied_at = EXCLUDED.applied_at,
                        metadata = EXCLUDED.metadata
                    RETURNING *
                    """
                ),
                {
                    "application_id": application_id,
                    "workspace_id": normalized_workspace_id,
                    "blueprint_id": normalized_blueprint_id,
                    "actor_id": _clean_string(actor_id),
                    "metadata": self.serialize_json(metadata or {}),
                },
            ).fetchone()
        return self._row_to_application(row)


def list_allocation_blueprints() -> dict[str, Any]:
    store = HostResourceAllocationBlueprintStore("core")
    blueprints = store.list_blueprints()
    return {"blueprints": blueprints}


def get_allocation_blueprint(blueprint_id: str) -> dict[str, Any] | None:
    store = HostResourceAllocationBlueprintStore("core")
    blueprint = store.get_blueprint(blueprint_id)
    if not blueprint:
        return None
    return {
        **blueprint,
        "entries": store.list_entries(str(blueprint.get("blueprint_id") or "")),
    }


def _resolve_blueprint_entry_allocation_payload(
    *,
    workspace_id: str,
    blueprint_id: str,
    entry: dict[str, Any],
    existing_allocation: dict[str, Any] | None,
) -> dict[str, Any]:
    blueprint_claims = _clean_int(
        entry.get("max_parallel_task_claims"),
        default=1,
    )
    existing_metadata = (
        dict(existing_allocation.get("metadata") or {})
        if isinstance(existing_allocation, dict)
        and isinstance(existing_allocation.get("metadata"), dict)
        else {}
    )
    operator_override = existing_metadata.get("operator_override")
    has_operator_override = isinstance(operator_override, dict) and bool(
        operator_override
    )
    effective_claims = (
        _clean_int(
            existing_allocation.get("max_parallel_task_claims"),
            default=blueprint_claims,
        )
        if has_operator_override and isinstance(existing_allocation, dict)
        else blueprint_claims
    )
    metadata: dict[str, Any] = {
        "source": "allocation_blueprint",
        "task_selectors": entry.get("task_selectors") or [],
        "resource_semantics": "shared_pool_admission_quota",
        "blueprint_max_parallel_task_claims": blueprint_claims,
    }
    if has_operator_override:
        metadata["operator_override"] = dict(operator_override)
        metadata["blueprint_apply_preserved_operator_override"] = True
    return {
        "workspace_id": workspace_id,
        "queue_shard": entry.get("queue_shard"),
        "task_family": entry.get("task_family"),
        "label": entry.get("label"),
        "max_parallel_task_claims": effective_claims,
        "share_policy": entry.get("share_policy") or "shared_pool",
        "priority_ceiling": entry.get("priority_ceiling") or "normal",
        "blueprint_id": blueprint_id,
        "blueprint_entry_id": entry.get("blueprint_entry_id"),
        "state": "enabled",
        "metadata": metadata,
    }


def apply_allocation_blueprint_to_workspace(
    *,
    workspace_id: str,
    blueprint_id: str = DEFAULT_ALLOCATION_BLUEPRINT_ID,
    actor_id: str | None = None,
) -> dict[str, Any]:
    normalized_workspace_id = _clean_string(workspace_id)
    normalized_blueprint_id = _clean_string(blueprint_id) or DEFAULT_ALLOCATION_BLUEPRINT_ID
    if not normalized_workspace_id:
        raise ValueError("workspace_id_required")

    blueprint_store = HostResourceAllocationBlueprintStore("core")
    blueprint = blueprint_store.get_blueprint(normalized_blueprint_id)
    if not blueprint:
        raise ValueError("allocation_blueprint_not_found")
    if blueprint.get("state") != "enabled":
        raise ValueError("allocation_blueprint_disabled")

    entries = blueprint_store.list_entries(normalized_blueprint_id)
    allocation_store = HostResourceWorkspaceAllocationStore("core")
    allocations: list[dict[str, Any]] = []
    for entry in entries:
        existing_allocation = allocation_store.find_allocation_for_task_family(
            workspace_id=normalized_workspace_id,
            queue_shard=_clean_string(entry.get("queue_shard")) or "",
            task_family=_clean_string(entry.get("task_family")) or "",
        )
        allocation = allocation_store.upsert_allocation(
            _resolve_blueprint_entry_allocation_payload(
                workspace_id=normalized_workspace_id,
                blueprint_id=normalized_blueprint_id,
                entry=entry,
                existing_allocation=existing_allocation,
            ),
            actor_id=actor_id,
        )
        allocations.append(allocation)

    application = blueprint_store.record_application(
        workspace_id=normalized_workspace_id,
        blueprint_id=normalized_blueprint_id,
        actor_id=actor_id,
        metadata={"source": "allocation_blueprint_apply"},
    )
    return {
        "blueprint": {
            **blueprint,
            "entries": entries,
        },
        "application": application,
        "allocations": allocations,
    }


def apply_default_host_resource_blueprint_to_workspace(
    *,
    workspace_id: str,
    owner_user_id: str | None = None,
    actor_id: str | None = None,
) -> dict[str, Any]:
    return apply_allocation_blueprint_to_workspace(
        workspace_id=workspace_id,
        blueprint_id=DEFAULT_ALLOCATION_BLUEPRINT_ID,
        actor_id=actor_id or owner_user_id,
    )


def _queue_snapshot_row(snapshot: dict[str, Any], queue_shard: str) -> dict[str, Any]:
    depths = snapshot.get("queue_depths")
    if not isinstance(depths, dict):
        depths = {}
    capacities = snapshot.get("capacity_by_queue_shard")
    if not isinstance(capacities, dict):
        capacities = {}
    return {
        "queue_depth": depths.get(queue_shard) if isinstance(depths.get(queue_shard), dict) else {},
        "capacity": (
            capacities.get(queue_shard)
            if isinstance(capacities.get(queue_shard), dict)
            else {}
        ),
    }


def build_workspace_allocation_effective_matrix(
    *,
    workspace_id: str,
) -> dict[str, Any]:
    normalized_workspace_id = _clean_string(workspace_id)
    if not normalized_workspace_id:
        raise ValueError("workspace_id_required")
    allocation_store = HostResourceWorkspaceAllocationStore("core")
    blueprint_store = HostResourceAllocationBlueprintStore("core")
    allocations = allocation_store.list_allocations(
        workspace_id=normalized_workspace_id,
        limit=500,
    )
    applications = blueprint_store.list_applications(workspace_id=normalized_workspace_id)
    snapshot = get_latest_queue_utilization_snapshot()

    matrix: list[dict[str, Any]] = []
    for allocation in allocations:
        queue_shard = str(allocation.get("queue_shard") or "").strip()
        if not queue_shard:
            continue
        snapshot_row = _queue_snapshot_row(snapshot, queue_shard)
        queue_depth = snapshot_row["queue_depth"]
        capacity = snapshot_row["capacity"]
        matrix.append(
            {
                "allocation_id": allocation.get("allocation_id"),
                "workspace_id": allocation.get("workspace_id"),
                "queue_shard": queue_shard,
                "task_family": allocation.get("task_family"),
                "label": allocation.get("label"),
                "max_parallel_task_claims": allocation.get(
                    "max_parallel_task_claims"
                ),
                "share_policy": allocation.get("share_policy"),
                "priority_ceiling": allocation.get("priority_ceiling"),
                "state": allocation.get("state"),
                "blueprint_id": allocation.get("blueprint_id"),
                "applied_at": allocation.get("applied_at"),
                "pending": _clean_int(queue_depth.get("pending"), default=0),
                "processing": _clean_int(queue_depth.get("processing"), default=0),
                "global_max_inflight": _clean_int(
                    capacity.get("max_inflight_total"),
                    default=0,
                ),
                "global_available_slots": _clean_int(
                    capacity.get("available_slots_total"),
                    default=0,
                ),
            }
        )

    return {
        "workspace_id": normalized_workspace_id,
        "applications": applications,
        "effective_matrix": sorted(
            matrix,
            key=lambda row: (
                str(row.get("queue_shard") or ""),
                str(row.get("task_family") or ""),
            ),
        ),
        "queue_snapshot": {
            "source": snapshot.get("source"),
            "captured_at": snapshot.get("captured_at"),
            "degraded": snapshot.get("degraded"),
            "errors": snapshot.get("errors") or [],
        },
    }
