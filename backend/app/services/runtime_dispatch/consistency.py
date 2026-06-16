"""Consistency contracts for future runtime dispatch apply execution."""

from __future__ import annotations

from typing import Any

from .tokens import build_apply_idempotency_key


def required_apply_event_contract(
    *,
    plan_id: str,
    apply_token: str,
    task_ids: list[str],
) -> dict[str, Any]:
    idempotency_key = build_apply_idempotency_key(plan_id, apply_token)
    return {
        "db_source_of_truth": True,
        "task_event_type": "task.route_changed",
        "outbox_event_type": "runtime_dispatch.redis_projection_requested",
        "idempotency_key": idempotency_key,
        "task_ids": sorted(task_ids),
        "ordering": [
            "bounded_db_route_update",
            "append_task_route_changed_event",
            "append_redis_projection_requested_outbox",
            "bounded_redis_projection_update",
        ],
    }


def build_apply_projection_result(
    *,
    plan_id: str,
    apply_token: str,
    updated_task_ids: list[str],
    skipped_task_ids: list[str] | None = None,
    redis_failed_task_ids: list[str] | None = None,
) -> dict[str, Any]:
    failed = sorted(set(redis_failed_task_ids or []))
    updated = sorted(set(updated_task_ids))
    skipped = sorted(set(skipped_task_ids or []))
    return {
        "accepted": True,
        "state": "partial_success" if failed else "applied",
        "plan_id": plan_id,
        "idempotency_key": build_apply_idempotency_key(plan_id, apply_token),
        "updated_task_ids": updated,
        "skipped_task_ids": skipped,
        "redis_partial_failure": bool(failed),
        "redis_failed_task_ids": failed,
        "repair_required": bool(failed),
        "repair_scope": {
            "plan_id": plan_id,
            "task_ids": failed,
        }
        if failed
        else None,
    }
