"""Generic task admission policy for producer-side backpressure."""

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from sqlalchemy import text

from app.models.workspace import Task
from backend.app.services.runner_topology import (
    DEFAULT_LOCAL_QUEUE_PARTITION,
    build_queue_partition_filter_clause,
    normalize_queue_partition,
    queue_partition_env_suffixes,
)

logger = logging.getLogger(__name__)

ADMISSION_DEFERRED_REASON = "admission_deferred"
_RUNNER_TASK_TYPES = ("playbook_execution", "tool_execution")


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


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def _normalize_queue_shard(value: Any) -> str:
    return normalize_queue_partition(value, fallback=DEFAULT_LOCAL_QUEUE_PARTITION)


def _coerce_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except Exception:
            return None
    return None


def _row_value(row: Any, key: str, default: Any = None) -> Any:
    if row is None:
        return default
    mapping = getattr(row, "_mapping", None)
    if mapping is not None and key in mapping:
        return mapping[key]
    if hasattr(row, key):
        return getattr(row, key)
    return default


@dataclass(frozen=True)
class AdmissionPressure:
    queue_shard: str
    pending_total: int
    running_total: int
    oldest_pending_at: Optional[datetime]

    @property
    def oldest_pending_age_seconds(self) -> int:
        if self.oldest_pending_at is None:
            return 0
        age = (_utc_now() - self.oldest_pending_at).total_seconds()
        return max(0, int(age))


@dataclass(frozen=True)
class AdmissionLimits:
    pending_limit: int
    oldest_pending_age_seconds: int
    defer_seconds: int


@dataclass(frozen=True)
class AdmissionDecision:
    allow: bool
    queue_shard: str
    execution_context: Optional[Dict[str, Any]] = None
    blocked_payload: Optional[Dict[str, Any]] = None
    next_eligible_at: Optional[datetime] = None


class TaskAdmissionService:
    """Evaluate generic producer-side admission for auto-triggered tasks."""

    def evaluate_on_create(self, tasks_store: Any, task: Task) -> AdmissionDecision:
        return self._evaluate(tasks_store, task, phase="create")

    def evaluate_on_release(self, tasks_store: Any, task: Task) -> AdmissionDecision:
        return self._evaluate(tasks_store, task, phase="release")

    def _evaluate(
        self,
        tasks_store: Any,
        task: Task,
        *,
        phase: str,
    ) -> AdmissionDecision:
        ctx = dict(task.execution_context) if isinstance(task.execution_context, dict) else {}
        queue_shard = _normalize_queue_shard(
            getattr(task, "queue_shard", None)
            or ctx.get("queue_partition")
            or ctx.get("queue_shard")
        )
        policy = self._extract_policy(task, ctx)

        if not _env_bool("LOCAL_CORE_TASK_ADMISSION_ENABLED", True):
            return AdmissionDecision(
                allow=True,
                queue_shard=queue_shard,
                execution_context=self._clear_admission_context(ctx),
            )

        if policy["mode"] != "auto":
            return AdmissionDecision(
                allow=True,
                queue_shard=queue_shard,
                execution_context=self._clear_admission_context(ctx),
            )

        pressure = self._load_queue_pressure(tasks_store, queue_shard)
        limits = self._resolve_limits(queue_shard, policy["visibility"])

        should_defer = False
        defer_reason = None
        if pressure.pending_total >= limits.pending_limit:
            should_defer = True
            defer_reason = "pending_limit"
        elif (
            limits.oldest_pending_age_seconds > 0
            and pressure.oldest_pending_age_seconds >= limits.oldest_pending_age_seconds
        ):
            should_defer = True
            defer_reason = "oldest_pending_age"

        if not should_defer:
            return AdmissionDecision(
                allow=True,
                queue_shard=queue_shard,
                execution_context=self._clear_admission_context(ctx),
            )

        defer_until = _utc_now() + timedelta(seconds=limits.defer_seconds)
        blocked_payload = {
            "policy": ADMISSION_DEFERRED_REASON,
            "phase": phase,
            "reason": defer_reason,
            "queue_partition": queue_shard,
            "queue_shard": queue_shard,
            "mode": policy["mode"],
            "visibility": policy["visibility"],
            "producer_kind": policy["producer_kind"],
            "evaluated_at": _utc_now().isoformat(),
            "defer_until": defer_until.isoformat(),
            "pressure": {
                "pending_total": pressure.pending_total,
                "running_total": pressure.running_total,
                "oldest_pending_age_seconds": pressure.oldest_pending_age_seconds,
            },
            "limits": {
                "pending_limit": limits.pending_limit,
                "oldest_pending_age_seconds": limits.oldest_pending_age_seconds,
                "defer_seconds": limits.defer_seconds,
            },
        }
        execution_context = self._build_deferred_context(ctx, blocked_payload, defer_until)
        return AdmissionDecision(
            allow=False,
            queue_shard=queue_shard,
            execution_context=execution_context,
            blocked_payload=blocked_payload,
            next_eligible_at=defer_until,
        )

    def _extract_policy(self, task: Task, ctx: Dict[str, Any]) -> Dict[str, str]:
        raw = ctx.get("admission_policy") if isinstance(ctx.get("admission_policy"), dict) else {}
        mode = str(raw.get("mode") or "").strip().lower()
        if not mode:
            mode = "auto" if ctx.get("auto_triggered") else "manual"

        visibility = str(raw.get("visibility") or "").strip().lower()
        if not visibility:
            visibility = "background" if mode == "auto" else "manual"

        producer_kind = str(raw.get("producer_kind") or "").strip().lower()
        if not producer_kind:
            producer_kind = "auto" if mode == "auto" else "manual"

        return {
            "mode": mode,
            "visibility": visibility,
            "producer_kind": producer_kind,
        }

    def _resolve_limits(self, queue_shard: str, visibility: str) -> AdmissionLimits:
        base_pending_limit = self._resolve_partition_env_limit(
            queue_shard=queue_shard,
            field_suffix="PENDING_LIMIT",
            fallback_env="LOCAL_CORE_TASK_ADMISSION_PENDING_LIMIT",
            default=256,
        )
        base_oldest_age_limit = self._resolve_partition_env_limit(
            queue_shard=queue_shard,
            field_suffix="OLDEST_PENDING_AGE_SECONDS",
            fallback_env="LOCAL_CORE_TASK_ADMISSION_OLDEST_PENDING_AGE_SECONDS",
            default=300,
        )
        base_defer_seconds = self._resolve_partition_env_limit(
            queue_shard=queue_shard,
            field_suffix="DEFER_SECONDS",
            fallback_env="LOCAL_CORE_TASK_ADMISSION_DEFER_SECONDS",
            default=30,
        )

        if visibility == "visible":
            pending_multiplier = _env_int(
                "LOCAL_CORE_TASK_ADMISSION_VISIBLE_PENDING_LIMIT_MULTIPLIER", 2
            )
            age_multiplier = _env_int(
                "LOCAL_CORE_TASK_ADMISSION_VISIBLE_OLDEST_PENDING_AGE_MULTIPLIER", 2
            )
            defer_seconds = _env_int(
                "LOCAL_CORE_TASK_ADMISSION_VISIBLE_DEFER_SECONDS",
                max(5, base_defer_seconds // 2),
            )
        else:
            pending_multiplier = _env_int(
                "LOCAL_CORE_TASK_ADMISSION_BACKGROUND_PENDING_LIMIT_MULTIPLIER", 1
            )
            age_multiplier = _env_int(
                "LOCAL_CORE_TASK_ADMISSION_BACKGROUND_OLDEST_PENDING_AGE_MULTIPLIER", 1
            )
            defer_seconds = base_defer_seconds

        return AdmissionLimits(
            pending_limit=max(1, base_pending_limit * max(1, pending_multiplier)),
            oldest_pending_age_seconds=max(
                1, base_oldest_age_limit * max(1, age_multiplier)
            ),
            defer_seconds=max(1, defer_seconds),
        )

    def _load_queue_pressure(self, tasks_store: Any, queue_shard: str) -> AdmissionPressure:
        queue_clause, queue_params = build_queue_partition_filter_clause(
            "queue_shard",
            queue_shard,
            param_prefix="queue_partition",
        )
        query = text(
            f"""
            SELECT
                COUNT(*) FILTER (
                    WHERE status = 'pending'
                      AND COALESCE(blocked_reason, '') = :unblocked_reason
                      AND COALESCE(next_eligible_at, created_at) <= :now
                      AND COALESCE(frontier_state, :legacy_ready_state) IN (
                        :ready_frontier_state,
                        :legacy_ready_state
                      )
                ) AS pending_total,
                COUNT(*) FILTER (
                    WHERE status = 'running'
                ) AS running_total,
                MIN(COALESCE(frontier_enqueued_at, next_eligible_at, created_at)) FILTER (
                    WHERE status = 'pending'
                      AND COALESCE(blocked_reason, '') = :unblocked_reason
                      AND COALESCE(next_eligible_at, created_at) <= :now
                      AND COALESCE(frontier_state, :legacy_ready_state) IN (
                        :ready_frontier_state,
                        :legacy_ready_state
                      )
                ) AS oldest_pending_at
            FROM tasks
            WHERE task_type IN (:task_type_pb, :task_type_tool)
              AND status IN (:pending_status, :running_status)
              AND {queue_clause}
            """
        )
        params = {
            "task_type_pb": _RUNNER_TASK_TYPES[0],
            "task_type_tool": _RUNNER_TASK_TYPES[1],
            "pending_status": "pending",
            "running_status": "running",
            "now": _utc_now(),
            "ready_frontier_state": "ready",
            "legacy_ready_state": "",
            "unblocked_reason": "",
        }
        params.update(queue_params)
        try:
            with tasks_store.get_connection() as conn:
                row = conn.execute(query, params).fetchone()
        except Exception as exc:
            logger.warning(
                "Task admission pressure query failed for shard=%s: %s",
                queue_shard,
                exc,
            )
            return AdmissionPressure(
                queue_shard=queue_shard,
                pending_total=0,
                running_total=0,
                oldest_pending_at=None,
            )

        return AdmissionPressure(
            queue_shard=queue_shard,
            pending_total=int(_row_value(row, "pending_total", 0) or 0),
            running_total=int(_row_value(row, "running_total", 0) or 0),
            oldest_pending_at=_coerce_datetime(_row_value(row, "oldest_pending_at")),
        )

    def _resolve_partition_env_limit(
        self,
        *,
        queue_shard: str,
        field_suffix: str,
        fallback_env: str,
        default: int,
    ) -> int:
        for shard_key in queue_partition_env_suffixes(queue_shard):
            env_name = f"LOCAL_CORE_TASK_ADMISSION_{shard_key}_{field_suffix}"
            raw = os.getenv(env_name)
            if raw is None:
                continue
            try:
                value = int(raw)
                if value > 0:
                    return value
            except Exception:
                continue
        return _env_int(fallback_env, default)

    def _build_deferred_context(
        self,
        ctx: Dict[str, Any],
        blocked_payload: Dict[str, Any],
        defer_until: datetime,
    ) -> Dict[str, Any]:
        ctx2 = dict(ctx)
        ctx2["resume_after"] = defer_until.isoformat()
        ctx2["admission"] = {
            "state": "deferred",
            "reason": blocked_payload.get("reason"),
            "queue_partition": blocked_payload.get("queue_partition"),
            "queue_shard": blocked_payload.get("queue_shard"),
            "visibility": blocked_payload.get("visibility"),
            "producer_kind": blocked_payload.get("producer_kind"),
            "defer_until": blocked_payload.get("defer_until"),
            "evaluated_at": blocked_payload.get("evaluated_at"),
        }
        return ctx2

    def _clear_admission_context(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        if not ctx:
            return {}
        ctx2 = dict(ctx)
        admission_ctx = ctx2.get("admission")
        if isinstance(admission_ctx, dict) and admission_ctx.get("state") == "deferred":
            ctx2.pop("resume_after", None)
        ctx2.pop("admission", None)
        return ctx2


TASK_ADMISSION_SERVICE = TaskAdmissionService()
