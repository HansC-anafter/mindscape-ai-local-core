"""TasksStore runner claim and workspace quota methods."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.models.workspace import TaskStatus

from ._base import _utc_now
from ._runner_helpers import (
    _WORKSPACE_QUOTA_RELEASE_REASONS,
    _build_claim_execution_context,
    _clean_int,
    _clean_string,
    _normalize_concurrency_keys,
    _running_concurrency_conflict_clause,
    _workspace_quota_allows_claim,
    _workspace_quota_selector_sql,
    _workspace_quota_task_selector_sql,
)


class TasksStoreRunnerClaimMixin:
    """Runner claim and quota release operations."""

    def has_running_concurrency_conflict(
        self,
        task_id: str,
        concurrency_keys: Optional[List[str]],
    ) -> bool:
        keys = _normalize_concurrency_keys(concurrency_keys)
        if not keys:
            return False

        clause, key_params = _running_concurrency_conflict_clause(keys)
        conflict_sql = clause.replace("AND NOT EXISTS", "SELECT EXISTS").strip()
        with self.get_connection() as conn:
            row = conn.execute(
                text(conflict_sql),
                {
                    "task_id": task_id,
                    "running_status": TaskStatus.RUNNING.value,
                    **key_params,
                },
            ).fetchone()
            return bool(row and row[0])

    def try_release_workspace_quota_task(
        self,
        task_id: str,
        *,
        workspace_id: str,
        queue_shard: str,
        selectors: List[str],
        task_selector: str,
        allocation_key: str,
        max_parallel_task_claims: int,
        blocked_reasons: Optional[List[str]] = None,
        execution_context: Optional[Dict[str, Any]] = None,
        now: Optional[datetime] = None,
    ) -> bool:
        now = now or _utc_now()
        max_parallel_task_claims = max(
            1,
            _clean_int(max_parallel_task_claims, default=1),
        )
        normalized_selectors = [
            selector
            for selector in (_clean_string(selector) for selector in selectors)
            if selector
        ]
        normalized_blocked_reasons = [
            reason
            for reason in (
                _clean_string(reason)
                for reason in (
                    blocked_reasons
                    if blocked_reasons is not None
                    else _WORKSPACE_QUOTA_RELEASE_REASONS
                )
            )
            if reason
        ]
        if not normalized_blocked_reasons:
            normalized_blocked_reasons = list(_WORKSPACE_QUOTA_RELEASE_REASONS)
        fairness_overflow_limit = max_parallel_task_claims + max(
            0,
            len(normalized_selectors) - 1,
        )
        task_selector = _clean_string(task_selector) or ""
        lock_key = _clean_string(allocation_key) or f"{workspace_id}:{queue_shard}"

        with self.transaction() as conn:
            if conn.dialect.name != "sqlite":
                conn.execute(
                    text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                    {"lock_key": lock_key},
                )

            params: Dict[str, Any] = {
                "workspace_id": workspace_id,
                "queue_shard": queue_shard,
                "running_status": TaskStatus.RUNNING.value,
                "pending_status": TaskStatus.PENDING.value,
                "ready_frontier_state": "ready",
                "task_selector": task_selector,
            }
            selector_sql = _workspace_quota_selector_sql(
                conn,
                selectors=normalized_selectors,
                params=params,
                key_prefix="selector",
            )
            task_selector_sql = (
                _workspace_quota_task_selector_sql(conn) if task_selector else ""
            )
            count_cast = "::int" if conn.dialect.name != "sqlite" else ""
            count_row = conn.execute(
                text(
                    f"""
                    SELECT
                        COUNT(*){count_cast} AS reserved_total,
                        SUM(
                            CASE
                                WHEN TRUE {task_selector_sql} THEN 1
                                ELSE 0
                            END
                        ){count_cast} AS reserved_same_selector
                    FROM tasks
                    WHERE workspace_id = :workspace_id
                      AND queue_shard = :queue_shard
                      AND (
                            status = :running_status
                            OR (
                                status = :pending_status
                                AND frontier_state = :ready_frontier_state
                                AND (blocked_reason IS NULL OR blocked_reason = '')
                            )
                      )
                      {selector_sql}
                    """
                ),
                params,
            ).fetchone()
            reserved_total = _clean_int(
                getattr(count_row, "reserved_total", 0),
                default=0,
            )
            reserved_same_selector = _clean_int(
                getattr(count_row, "reserved_same_selector", 0),
                default=0,
            )
            if reserved_total >= max_parallel_task_claims and (
                reserved_same_selector > 0
                or reserved_total >= fairness_overflow_limit
            ):
                return False

            result = conn.execute(
                text(
                    f"""
                    UPDATE tasks
                    SET next_eligible_at = :now,
                        blocked_reason = NULL,
                        blocked_payload = NULL,
                        queue_shard = :queue_shard,
                        frontier_state = :ready_frontier_state,
                        frontier_enqueued_at = :now,
                        execution_context = COALESCE(:execution_context, execution_context)
                    WHERE id = :task_id
                      AND status = :pending_status
                      AND frontier_state = :cold_frontier_state
                      AND blocked_reason IN ({", ".join(f":blocked_reason_{index}" for index in range(len(normalized_blocked_reasons)))})
                    """
                ),
                {
                    "task_id": task_id,
                    "now": now,
                    "queue_shard": queue_shard,
                    "pending_status": TaskStatus.PENDING.value,
                    "ready_frontier_state": "ready",
                    "cold_frontier_state": "cold",
                    "execution_context": (
                        self.serialize_json(execution_context)
                        if isinstance(execution_context, dict)
                        else None
                    ),
                    **{
                        f"blocked_reason_{index}": reason
                        for index, reason in enumerate(normalized_blocked_reasons)
                    },
                },
            )
            return result.rowcount == 1

    def try_claim_task(
        self,
        task_id: str,
        runner_id: str,
        concurrency_keys: Optional[List[str]] = None,
        workspace_quota_decision: Any = None,
    ) -> bool:
        now = _utc_now()

        with self.transaction() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT
                        status,
                        concurrency_key,
                        params,
                        execution_context,
                        workspace_id,
                        queue_shard,
                        pack_id,
                        task_type
                    FROM tasks
                    WHERE id = :task_id
                """
                ),
                {"task_id": task_id},
            ).fetchone()
            if not row:
                return False

            current_status = getattr(row, "status", None)
            if current_status != TaskStatus.PENDING.value:
                return False

            if not _workspace_quota_allows_claim(
                conn,
                task_id=task_id,
                row=row,
                workspace_quota_decision=workspace_quota_decision,
            ):
                return False

            task_params = self.deserialize_json(getattr(row, "params", None), {})
            existing_context = self.deserialize_json(
                getattr(row, "execution_context", None),
                {},
            )
            claim_execution_context = _build_claim_execution_context(
                existing_context,
                task_params=task_params,
                runner_id=runner_id,
                now=now,
            )

            keys = _normalize_concurrency_keys(concurrency_keys)
            persisted_key = getattr(row, "concurrency_key", None)
            if isinstance(persisted_key, str) and persisted_key.strip():
                keys = _normalize_concurrency_keys([*keys, persisted_key])
            conflict_clause, conflict_params = _running_concurrency_conflict_clause(
                keys
            )

            try:
                result = conn.execute(
                    text(
                        f"""
                    UPDATE tasks
                    SET status = :running_status,
                        started_at = :started_at,
                        runner_id = :runner_id,
                        heartbeat_at = :heartbeat_at,
                        execution_context = :execution_context,
                        blocked_reason = NULL,
                        blocked_payload = NULL,
                        frontier_state = :frontier_state,
                        frontier_enqueued_at = NULL
                    WHERE id = :task_id AND status = :pending_status
                    {conflict_clause}
                """
                    ),
                    {
                        "running_status": TaskStatus.RUNNING.value,
                        "pending_status": TaskStatus.PENDING.value,
                        "started_at": now,
                        "runner_id": runner_id,
                        "heartbeat_at": now,
                        "execution_context": self.serialize_json(
                            claim_execution_context
                        ),
                        "frontier_state": "running",
                        "task_id": task_id,
                        **conflict_params,
                    },
                )
            except IntegrityError:
                return False
            claimed = result.rowcount == 1
            if claimed and hasattr(self, "_record_task_claim"):
                self._record_task_claim(
                    conn,
                    task_id=task_id,
                    runner_id=runner_id,
                    started_at=now,
                )
            return claimed
