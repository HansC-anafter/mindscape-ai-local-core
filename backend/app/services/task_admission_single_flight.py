"""Single-flight admission policy for playbook-scoped concurrency keys."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from sqlalchemy import text

from backend.app.models.workspace import Task

logger = logging.getLogger(__name__)

SINGLE_FLIGHT_ADMISSION_POLICY = "single_flight_admission"
RUNNER_TASK_TYPES = ("playbook_execution", "tool_execution")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
        return value if value > 0 else default
    except Exception:
        return default


def single_flight_defer_seconds() -> int:
    return _env_int("LOCAL_CORE_TASK_ADMISSION_SINGLE_FLIGHT_DEFER_SECONDS", 60)


def _row_value(row: Any, key: str, default: Any = None) -> Any:
    if row is None:
        return default
    mapping = getattr(row, "_mapping", None)
    if mapping is not None and key in mapping:
        return mapping[key]
    if hasattr(row, key):
        return getattr(row, key)
    return default


def _normalized_string(value: Any) -> Optional[str]:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    if value is None or isinstance(value, (dict, list, tuple, set)):
        return None
    stripped = str(value).strip()
    return stripped or None


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


@dataclass(frozen=True)
class SingleFlightAdmissionDecision:
    allow: bool
    blocked_payload: Optional[Dict[str, Any]] = None
    next_eligible_at: Optional[datetime] = None


def _single_flight_enabled(task: Task, ctx: Dict[str, Any]) -> bool:
    if task.task_type not in RUNNER_TASK_TYPES:
        return False
    concurrency_key = _normalized_string(getattr(task, "concurrency_key", None))
    if not concurrency_key:
        return False
    concurrency = ctx.get("concurrency")
    if not isinstance(concurrency, dict):
        return False
    if _normalized_string(concurrency.get("lock_scope")) != "playbook":
        return False
    max_parallel = _coerce_int(concurrency.get("max_parallel"), 1)
    return max_parallel <= 1


def evaluate_single_flight_admission(
    tasks_store: Any,
    task: Task,
    *,
    queue_shard: str,
    policy: Dict[str, str],
    phase: str,
    now: Optional[datetime] = None,
) -> SingleFlightAdmissionDecision:
    """Return a deferred decision when the same playbook key is already active."""

    ctx = dict(task.execution_context) if isinstance(task.execution_context, dict) else {}
    if not _single_flight_enabled(task, ctx):
        return SingleFlightAdmissionDecision(allow=True)

    effective_now = now or _utc_now()
    concurrency_key = str(task.concurrency_key).strip()
    task_id = str(getattr(task, "id", "") or "")
    query = text(
        """
        SELECT id, status, frontier_state
        FROM tasks
        WHERE concurrency_key = :concurrency_key
          AND id <> :task_id
          AND task_type IN (:task_type_pb, :task_type_tool)
          AND (
            (
              status = :running_status
              AND COALESCE(frontier_state, :running_frontier_state) = :running_frontier_state
            )
            OR (
              status = :pending_status
              AND frontier_state IN (:ready_frontier_state, :running_frontier_state)
              AND (blocked_reason IS NULL OR blocked_reason = :unblocked_reason)
              AND next_eligible_at <= :now
            )
          )
        ORDER BY
          CASE WHEN status = :running_status THEN 0 ELSE 1 END,
          created_at ASC,
          id ASC
        LIMIT 1
        """
    )
    params = {
        "concurrency_key": concurrency_key,
        "task_id": task_id,
        "task_type_pb": RUNNER_TASK_TYPES[0],
        "task_type_tool": RUNNER_TASK_TYPES[1],
        "pending_status": "pending",
        "running_status": "running",
        "ready_frontier_state": "ready",
        "running_frontier_state": "running",
        "unblocked_reason": "",
        "now": effective_now,
    }
    try:
        with tasks_store.get_connection() as conn:
            conflict = conn.execute(query, params).fetchone()
    except Exception as exc:
        logger.warning(
            "Single-flight admission query failed for key=%s shard=%s: %s",
            concurrency_key,
            queue_shard,
            exc,
        )
        return SingleFlightAdmissionDecision(allow=True)

    if conflict is None:
        return SingleFlightAdmissionDecision(allow=True)

    defer_until = effective_now + timedelta(seconds=single_flight_defer_seconds())
    blocked_payload = {
        "policy": SINGLE_FLIGHT_ADMISSION_POLICY,
        "phase": phase,
        "reason": "active_window",
        "queue_partition": queue_shard,
        "queue_shard": queue_shard,
        "mode": policy.get("mode"),
        "visibility": policy.get("visibility"),
        "producer_kind": policy.get("producer_kind"),
        "concurrency_key": concurrency_key,
        "conflict_task_id": _row_value(conflict, "id"),
        "conflict_status": _row_value(conflict, "status"),
        "conflict_frontier_state": _row_value(conflict, "frontier_state"),
        "evaluated_at": effective_now.isoformat(),
        "defer_until": defer_until.isoformat(),
    }
    return SingleFlightAdmissionDecision(
        allow=False,
        blocked_payload=blocked_payload,
        next_eligible_at=defer_until,
    )
