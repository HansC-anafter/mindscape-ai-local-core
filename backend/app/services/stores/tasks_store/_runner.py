"""
TasksStore runner lifecycle mixin for claim, heartbeat, zombie reaping, and cancel.
"""

import json
import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.models.workspace import Task, TaskStatus
from backend.app.services.runner_live_state import RunnerLiveStateStore

from ._base import _utc_now

logger = logging.getLogger(__name__)

_CLAIM_CONTEXT_STALE_KEYS = (
    "dependency_hold",
    "error",
    "failed_at",
    "heartbeat_at",
    "resource_pressure",
    "resource_pressure_source",
    "resource_retry_delay_sec",
    "resource_snapshot",
    "resume_after",
    "runner_reaper",
    "runner_skip_conflict_lock_key",
    "runner_skip_lock_key",
    "runner_skip_reason",
)


def _parse_heartbeat_datetime(raw_value: Any) -> Optional[datetime]:
    if isinstance(raw_value, datetime):
        heartbeat_at = raw_value
    elif isinstance(raw_value, str) and raw_value:
        try:
            heartbeat_at = datetime.fromisoformat(raw_value)
        except Exception:
            return None
    else:
        return None

    if heartbeat_at.tzinfo is None:
        heartbeat_at = heartbeat_at.replace(tzinfo=timezone.utc)
    return heartbeat_at


def _effective_runner_heartbeat_at(
    task: Task,
    ctx: Dict[str, Any],
    live_state_store: Optional[RunnerLiveStateStore],
) -> Optional[datetime]:
    if live_state_store is not None:
        try:
            live_payload = live_state_store.get_task_heartbeat(task.id)
        except Exception:
            live_payload = None
        if isinstance(live_payload, dict):
            live_heartbeat_at = _parse_heartbeat_datetime(
                live_payload.get("heartbeat_at")
            )
            if live_heartbeat_at is not None:
                return live_heartbeat_at

    heartbeat_at = _parse_heartbeat_datetime(getattr(task, "heartbeat_at", None))
    if heartbeat_at is not None:
        return heartbeat_at
    return _parse_heartbeat_datetime(ctx.get("heartbeat_at"))


def _build_claim_execution_context(
    existing_ctx: Dict[str, Any],
    *,
    task_params: Optional[Dict[str, Any]] = None,
    runner_id: str,
    now: datetime,
) -> Dict[str, Any]:
    ctx = dict(existing_ctx) if isinstance(existing_ctx, dict) else {}
    params_inputs: Dict[str, Any] = {}
    if isinstance(task_params, dict):
        nested_params_inputs = task_params.get("inputs")
        if isinstance(nested_params_inputs, dict):
            params_inputs.update(nested_params_inputs)
        else:
            params_inputs.update(task_params)
    if params_inputs:
        ctx_inputs = ctx.get("inputs")
        merged_inputs = dict(params_inputs)
        if isinstance(ctx_inputs, dict):
            merged_inputs.update(ctx_inputs)
        ctx["inputs"] = merged_inputs
    for key in _CLAIM_CONTEXT_STALE_KEYS:
        ctx.pop(key, None)
    ctx["runner_id"] = runner_id
    ctx["heartbeat_at"] = now.isoformat()
    ctx["status"] = "running"
    return ctx


def _normalize_concurrency_keys(raw_keys: Optional[List[str]]) -> List[str]:
    keys: List[str] = []
    seen: set[str] = set()
    for raw_key in raw_keys or []:
        if not isinstance(raw_key, str):
            continue
        key = raw_key.strip()
        if not key or key in seen:
            continue
        keys.append(key)
        seen.add(key)
    return keys


def _running_concurrency_conflict_clause(
    concurrency_keys: List[str],
) -> tuple[str, Dict[str, str]]:
    if not concurrency_keys:
        return "", {}

    params = {f"concurrency_key_{idx}": key for idx, key in enumerate(concurrency_keys)}
    placeholders = ", ".join(f":concurrency_key_{idx}" for idx in range(len(params)))
    return (
        f"""
        AND NOT EXISTS (
            SELECT 1
            FROM tasks running_task
            WHERE running_task.id <> :task_id
              AND running_task.status = :running_status
              AND running_task.concurrency_key IN ({placeholders})
            LIMIT 1
        )
        """,
        params,
    )


class TasksStoreRunnerMixin:
    """Runner lifecycle operations for TasksStore."""

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

    def try_claim_task(
        self,
        task_id: str,
        runner_id: str,
        concurrency_keys: Optional[List[str]] = None,
    ) -> bool:
        now = _utc_now()

        with self.transaction() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT status, concurrency_key, params, execution_context
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

    def update_task_heartbeat(
        self, task_id: str, runner_id: Optional[str] = None
    ) -> bool:
        """Return True if the task should be aborted without mutating heartbeat.

        Returns:
            should_abort: True if the DB task status indicates the runner
            should stop (cancelled, expired, or externally failed).
        """
        restart_error = "Execution interrupted by server restart"
        abort_statuses = {
            TaskStatus.CANCELLED_BY_USER.value,
            TaskStatus.EXPIRED.value,
        }

        with self.get_connection() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT status, error
                    FROM tasks
                    WHERE id = :task_id
                    """
                ),
                {"task_id": task_id},
            ).fetchone()
        if not row:
            return True

        status_raw = getattr(row, "status", None)
        error_raw = getattr(row, "error", None) or ""
        if status_raw in abort_statuses:
            logger.warning(
                "Task %s status=%s - signalling abort to runner", task_id, status_raw
            )
            return True
        if status_raw == TaskStatus.FAILED.value and error_raw != restart_error:
            logger.warning(
                "Task %s externally failed (%s) - signalling abort",
                task_id,
                error_raw,
            )
            return True

        logger.debug("Checked abort state for task %s (runner=%s)", task_id, runner_id)
        return False

    def should_abort_task(self, task_id: str) -> bool:
        """Return True when the runner should abort the task without mutating heartbeat."""
        task = self.get_task(task_id)
        if not task:
            return True

        abort_statuses = {
            TaskStatus.CANCELLED_BY_USER,
            TaskStatus.EXPIRED,
        }
        if task.status in abort_statuses:
            logger.warning(
                "Task %s status=%s - signalling abort to runner", task_id, task.status
            )
            return True
        if (
            task.status == TaskStatus.FAILED
            and (task.error or "") != "Execution interrupted by server restart"
        ):
            logger.warning(
                "Task %s externally failed (%s) - signalling abort",
                task_id,
                task.error,
            )
            return True
        return False

    def reap_zombie_tasks(
        self,
        heartbeat_ttl_minutes: int = 10,
        no_heartbeat_ttl_minutes: int = 30,
    ) -> List[str]:
        """Reap zombie tasks that have stale or missing heartbeats.

        A task is considered zombie if:
        - It has a heartbeat older than heartbeat_ttl_minutes, OR
        - It has no heartbeat and has been running for > no_heartbeat_ttl_minutes

        Args:
            heartbeat_ttl_minutes: Max age of heartbeat before task is reaped
            no_heartbeat_ttl_minutes: Max running time without any heartbeat

        Returns:
            List of reaped task IDs
        """
        from datetime import timedelta

        now = _utc_now()
        tasks = self.list_tasks_by_workspace(
            workspace_id=None, status=TaskStatus.RUNNING
        )
        try:
            live_state_store = RunnerLiveStateStore()
        except Exception:
            live_state_store = None

        reaped_ids: List[str] = []
        for task in tasks:
            ctx = (
                task.execution_context
                if isinstance(task.execution_context, dict)
                else {}
            )
            hb_dt = _effective_runner_heartbeat_at(task, ctx, live_state_store)

            is_zombie = False
            reason = ""

            if hb_dt:
                age = now - hb_dt
                if age > timedelta(minutes=heartbeat_ttl_minutes):
                    is_zombie = True
                    reason = (
                        f"Zombie: heartbeat stale for {int(age.total_seconds())}s "
                        f"(threshold {heartbeat_ttl_minutes}m)"
                    )
            else:
                # Use task age when no heartbeat exists.
                started = task.started_at or task.created_at
                if started:
                    if started.tzinfo is None:
                        started = started.replace(tzinfo=timezone.utc)
                    age = now - started
                    if age > timedelta(minutes=no_heartbeat_ttl_minutes):
                        is_zombie = True
                        reason = (
                            f"Zombie: no heartbeat, running for {int(age.total_seconds())}s "
                            f"(threshold {no_heartbeat_ttl_minutes}m)"
                        )

            if is_zombie:
                try:
                    self.update_task_status(
                        task_id=task.id,
                        status=TaskStatus.FAILED,
                        error=reason,
                        completed_at=now,
                    )
                    reaped_ids.append(task.id)
                    logger.warning("Reaped zombie task %s: %s", task.id, reason)
                except Exception as e:
                    logger.error("Failed to reap zombie task %s: %s", task.id, e)

        if reaped_ids:
            logger.info("Zombie reaper: reaped %d tasks", len(reaped_ids))
        else:
            logger.debug("Zombie reaper: no zombie tasks found")

        return reaped_ids

    def cancel_task(self, task_id: str) -> bool:
        """Cancel a task by setting its status to CANCELLED_BY_USER.

        Works on PENDING or RUNNING tasks. For RUNNING tasks, the runner
        will detect the cancellation via the heartbeat abort check.

        Args:
            task_id: Task ID to cancel

        Returns:
            True if the task was cancelled, False if not found or
            already in a terminal state.
        """
        task = self.get_task(task_id)
        if not task:
            return False

        if task.status not in (TaskStatus.PENDING, TaskStatus.RUNNING):
            return False

        now = _utc_now()
        try:
            self.update_task_status(
                task_id=task_id,
                status=TaskStatus.CANCELLED_BY_USER,
                error="Cancelled by user",
                completed_at=now,
            )
            logger.info("Task %s cancelled by user", task_id)
            return True
        except Exception as e:
            logger.error("Failed to cancel task %s: %s", task_id, e)
            return False

    def ensure_runner_heartbeats_table(self) -> None:
        """Create runner_heartbeats table if it does not exist."""
        with self.transaction() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS runner_heartbeats (
                        runner_id TEXT PRIMARY KEY,
                        profile_code TEXT,
                        hostname TEXT,
                        inflight INTEGER NOT NULL DEFAULT 0,
                        heartbeat_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
            )
            for statement in (
                "ALTER TABLE runner_heartbeats ADD COLUMN IF NOT EXISTS profile_code TEXT",
                "ALTER TABLE runner_heartbeats ADD COLUMN IF NOT EXISTS hostname TEXT",
                "ALTER TABLE runner_heartbeats ADD COLUMN IF NOT EXISTS inflight INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE runner_heartbeats ADD COLUMN IF NOT EXISTS resource_snapshot JSONB",
            ):
                try:
                    conn.execute(text(statement))
                except Exception:
                    pass

    def _upsert_runner_heartbeat_legacy(self, runner_id: str) -> None:
        with self.transaction() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO runner_heartbeats (runner_id, heartbeat_at)
                    VALUES (:runner_id, NOW())
                    ON CONFLICT (runner_id)
                    DO UPDATE SET heartbeat_at = NOW()
                    """
                ),
                {"runner_id": runner_id},
            )

    def upsert_runner_heartbeat(
        self,
        runner_id: str,
        *,
        profile_code: str | None = None,
        hostname: str | None = None,
        inflight: int = 0,
        resource_snapshot: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record that a runner is alive (called every poll cycle)."""
        resource_snapshot_payload = (
            json.dumps(resource_snapshot, separators=(",", ":"))
            if isinstance(resource_snapshot, dict)
            else None
        )
        try:
            with self.transaction() as conn:
                conn.execute(
                    text(
                        """
                        INSERT INTO runner_heartbeats (
                            runner_id,
                            profile_code,
                            hostname,
                            inflight,
                            resource_snapshot,
                            heartbeat_at
                        )
                        VALUES (
                            :runner_id,
                            :profile_code,
                            :hostname,
                            :inflight,
                            CAST(:resource_snapshot AS JSONB),
                            NOW()
                        )
                        ON CONFLICT (runner_id)
                        DO UPDATE SET
                            profile_code = EXCLUDED.profile_code,
                            hostname = EXCLUDED.hostname,
                            inflight = EXCLUDED.inflight,
                            resource_snapshot = EXCLUDED.resource_snapshot,
                            heartbeat_at = NOW()
                        """
                    ),
                    {
                        "runner_id": runner_id,
                        "profile_code": profile_code,
                        "hostname": hostname,
                        "inflight": max(0, int(inflight or 0)),
                        "resource_snapshot": resource_snapshot_payload,
                    },
                )
        except Exception:
            # Table might not exist yet; create it and retry.
            try:
                self.ensure_runner_heartbeats_table()
                try:
                    with self.transaction() as conn:
                        conn.execute(
                            text(
                                """
                                INSERT INTO runner_heartbeats (
                                    runner_id,
                                    profile_code,
                                    hostname,
                                    inflight,
                                    resource_snapshot,
                                    heartbeat_at
                                )
                                VALUES (
                                    :runner_id,
                                    :profile_code,
                                    :hostname,
                                    :inflight,
                                    CAST(:resource_snapshot AS JSONB),
                                    NOW()
                                )
                                ON CONFLICT (runner_id)
                                DO UPDATE SET
                                    profile_code = EXCLUDED.profile_code,
                                    hostname = EXCLUDED.hostname,
                                    inflight = EXCLUDED.inflight,
                                    resource_snapshot = EXCLUDED.resource_snapshot,
                                    heartbeat_at = NOW()
                                """
                            ),
                            {
                                "runner_id": runner_id,
                                "profile_code": profile_code,
                                "hostname": hostname,
                                "inflight": max(0, int(inflight or 0)),
                                "resource_snapshot": resource_snapshot_payload,
                            },
                        )
                except Exception:
                    self._upsert_runner_heartbeat_legacy(runner_id)
            except Exception:
                try:
                    self._upsert_runner_heartbeat_legacy(runner_id)
                except Exception:
                    pass

    def has_active_runner(self, max_age_seconds: float = 120.0) -> bool:
        """Check if any runner has sent a heartbeat within max_age_seconds."""
        return bool(
            self.list_runner_heartbeats(
                max_age_seconds=max_age_seconds,
                limit=1,
            )
        )

    def _list_runner_resource_heartbeats_from_redis(
        self,
        *,
        max_age_seconds: Optional[float],
        limit: int,
    ) -> List[Dict[str, Any]]:
        try:
            from backend.app.services.cache.redis_cache import get_cache_service

            cache = get_cache_service()
            ensure_connected = getattr(cache, "_ensure_connected", None)
            if callable(ensure_connected) and not ensure_connected():
                return []
            client = getattr(cache, "_client", None)
            if client is None:
                return []
            now_epoch = datetime.now(timezone.utc).timestamp()
            max_age = (
                float(max_age_seconds)
                if isinstance(max_age_seconds, (int, float)) and max_age_seconds > 0
                else None
            )
            heartbeats: List[Dict[str, Any]] = []
            for key in client.scan_iter(
                match="mindscape:runner_resources:heartbeat:v1:*",
                count=max(100, int(limit or 50)),
            ):
                raw = client.get(key)
                if raw is None:
                    continue
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8", errors="ignore")
                try:
                    payload = json.loads(str(raw))
                except Exception:
                    continue
                if not isinstance(payload, dict):
                    continue
                captured_at = payload.get("captured_at_epoch")
                if not isinstance(captured_at, (int, float)):
                    continue
                if max_age is not None and now_epoch - float(captured_at) > max_age:
                    continue
                capacity = (
                    payload.get("capacity")
                    if isinstance(payload.get("capacity"), dict)
                    else {}
                )
                heartbeat_at = datetime.fromtimestamp(float(captured_at), timezone.utc)
                heartbeats.append(
                    {
                        "runner_id": str(payload.get("runner_id") or ""),
                        "profile_code": payload.get("profile_code"),
                        "hostname": None,
                        "inflight": int(capacity.get("inflight") or 0),
                        "resource_snapshot": payload.get("resource_snapshot")
                        if isinstance(payload.get("resource_snapshot"), dict)
                        else {},
                        "heartbeat_at": heartbeat_at.isoformat(),
                    }
                )
            heartbeats.sort(
                key=lambda row: str(row.get("heartbeat_at") or ""),
                reverse=True,
            )
            return heartbeats[:limit]
        except Exception:
            return []

    def list_runner_heartbeats(
        self,
        *,
        max_age_seconds: Optional[float] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Return recent runner heartbeats with profile metadata when available."""
        limit = max(1, int(limit or 50))
        redis_heartbeats = self._list_runner_resource_heartbeats_from_redis(
            max_age_seconds=max_age_seconds,
            limit=limit,
        )
        if redis_heartbeats:
            return redis_heartbeats

        query_parts = [
            """
            SELECT runner_id, profile_code, hostname, inflight, resource_snapshot, heartbeat_at
            FROM runner_heartbeats
            """
        ]
        params: Dict[str, Any] = {"limit": limit}
        if isinstance(max_age_seconds, (int, float)) and max_age_seconds > 0:
            query_parts.append(
                "WHERE heartbeat_at > NOW() - INTERVAL '1 second' * :max_age"
            )
            params["max_age"] = float(max_age_seconds)
        query_parts.append("ORDER BY heartbeat_at DESC")
        query_parts.append("LIMIT :limit")

        try:
            with self.get_connection() as conn:
                rows = conn.execute(text(" ".join(query_parts)), params).fetchall()
        except Exception:
            try:
                fallback_query = [
                    "SELECT runner_id, heartbeat_at FROM runner_heartbeats"
                ]
                fallback_params: Dict[str, Any] = {"limit": limit}
                if isinstance(max_age_seconds, (int, float)) and max_age_seconds > 0:
                    fallback_query.append(
                        "WHERE heartbeat_at > NOW() - INTERVAL '1 second' * :max_age"
                    )
                    fallback_params["max_age"] = float(max_age_seconds)
                fallback_query.append("ORDER BY heartbeat_at DESC")
                fallback_query.append("LIMIT :limit")
                with self.get_connection() as conn:
                    rows = conn.execute(
                        text(" ".join(fallback_query)),
                        fallback_params,
                    ).fetchall()
            except Exception:
                return []

        heartbeats: List[Dict[str, Any]] = []
        for row in rows:
            mapping = getattr(row, "_mapping", None)
            runner_id = mapping["runner_id"] if mapping is not None else row[0]
            heartbeat_at = (
                mapping["heartbeat_at"]
                if mapping is not None and "heartbeat_at" in mapping
                else row[-1]
            )
            profile_code = (
                mapping["profile_code"]
                if mapping is not None and "profile_code" in mapping
                else None
            )
            hostname = (
                mapping["hostname"]
                if mapping is not None and "hostname" in mapping
                else None
            )
            inflight = (
                mapping["inflight"]
                if mapping is not None and "inflight" in mapping
                else 0
            )
            resource_snapshot = (
                mapping["resource_snapshot"]
                if mapping is not None and "resource_snapshot" in mapping
                else None
            )
            if isinstance(resource_snapshot, str):
                try:
                    resource_snapshot = json.loads(resource_snapshot)
                except Exception:
                    resource_snapshot = None
            heartbeats.append(
                {
                    "runner_id": runner_id,
                    "profile_code": profile_code,
                    "hostname": hostname,
                    "inflight": int(inflight or 0),
                    "resource_snapshot": resource_snapshot,
                    "heartbeat_at": (
                        heartbeat_at.isoformat()
                        if hasattr(heartbeat_at, "isoformat")
                        else str(heartbeat_at)
                    ),
                }
            )
        return heartbeats
