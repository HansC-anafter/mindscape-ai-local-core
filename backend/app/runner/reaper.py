"""Runner reaper — cleans up stale tasks and orphaned locks."""

import logging
from datetime import timedelta
from typing import Optional

from sqlalchemy import text

from backend.app.models.workspace import TaskStatus
from backend.app.services.stores.tasks_store import TasksStore
from backend.app.services.stores.postgres.runner_locks_store import (
    PostgresRunnerLocksStore,
)

from backend.app.runner.lifecycle_hooks import _invoke_on_fail_hook
from backend.app.runner.utils import _env_int, _parse_utc_iso, _utc_now

logger = logging.getLogger(__name__)


def _reap_stale_running_tasks(tasks_store: TasksStore, runner_id: str) -> None:
    stale_seconds = _env_int("LOCAL_CORE_RUNNER_STALE_TASK_SECONDS", 180)
    threshold = _utc_now() - timedelta(seconds=stale_seconds)

    try:
        running = tasks_store.list_running_playbook_execution_tasks(
            workspace_id=None, limit=500
        )
    except Exception as e:
        logger.warning(f"Runner stale-task scan failed: {e}")
        return

    for t in running:
        try:
            ctx = t.execution_context if isinstance(t.execution_context, dict) else {}
            ctx_runner_id = ctx.get("runner_id")
            heartbeat_at = _parse_utc_iso(ctx.get("heartbeat_at"))

            if not ctx_runner_id:
                continue

            # Only reap tasks that were executed in runner mode (or clearly runner-owned).
            if ctx.get("execution_mode") not in (None, "runner"):
                continue

            if heartbeat_at and heartbeat_at > threshold:
                continue

            msg = f"Runner heartbeat stale (previous_runner_id={ctx_runner_id}, heartbeat_at={ctx.get('heartbeat_at')})"
            ctx2 = dict(ctx)
            ctx2["runner_reaper"] = {
                "runner_id": runner_id,
                "stale_seconds": stale_seconds,
                "action": None,
                "reason": msg,
            }

            # If the task is still queued, re-queue it so a healthy runner can claim it.
            # IMPORTANT:
            # - Do NOT use sandbox_id/current_step_index as "started" heuristics; some runner tasks
            #   execute in-process and may never set sandbox_id even after making real progress.
            if ctx2.get("status") == "queued":
                # Track re-queue count to prevent infinite crash loops
                requeue_count = 0
                if isinstance(ctx.get("runner_reaper"), dict):
                    requeue_count = ctx["runner_reaper"].get("requeue_count", 0)

                if requeue_count >= 3:
                    # Too many re-queues — fail permanently
                    ctx2["status"] = "failed"
                    ctx2["error"] = f"Exceeded max re-queue attempts ({requeue_count})"
                    ctx2["runner_reaper"]["action"] = "fail_max_requeue"
                    ctx2["runner_reaper"]["requeue_count"] = requeue_count
                    tasks_store.update_task(
                        t.id,
                        execution_context=ctx2,
                        status=TaskStatus.FAILED,
                        completed_at=_utc_now(),
                        error=ctx2["error"],
                    )
                    logger.warning(
                        f"Failed task after {requeue_count} re-queues task_id={t.id} ({msg})"
                    )
                else:
                    ctx2.pop("runner_id", None)
                    ctx2.pop("heartbeat_at", None)
                    ctx2["status"] = "queued"
                    ctx2["runner_reaper"]["action"] = "requeue"
                    ctx2["runner_reaper"]["requeue_count"] = requeue_count + 1
                    ctx2["runner_reaper"]["requeued_at"] = _utc_now().isoformat()
                    tasks_store.update_task(
                        t.id,
                        execution_context=ctx2,
                        status=TaskStatus.PENDING,
                        error=None,
                    )
                    logger.warning(
                        f"Re-queued stale runner task task_id={t.id} (attempt {requeue_count + 1}/3) ({msg})"
                    )
            else:
                # If the task is running but heartbeat is stale, mark failed.
                # Try on_fail lifecycle hook first (declared in playbook spec).
                hook_handled = False
                try:
                    hook_handled = _invoke_on_fail_hook(ctx2, msg, t.id)
                except Exception as hook_err:
                    logger.warning(f"Reaper on_fail hook error for {t.id}: {hook_err}")

                if hook_handled:
                    ctx2["runner_reaper"]["action"] = "lifecycle_hook_on_fail"
                    logger.warning(
                        f"Reaped + on_fail hook invoked for stale task task_id={t.id} ({msg})"
                    )

                # ALWAYS ensure task reaches terminal state, regardless of hook result.
                # Re-read to check if hook already marked it FAILED.
                refreshed = tasks_store.get_task(t.id)
                if refreshed and refreshed.status not in (
                    TaskStatus.FAILED,
                    TaskStatus.CANCELLED_BY_USER,
                    TaskStatus.SUCCEEDED,
                    TaskStatus.EXPIRED,
                ):
                    ctx2["status"] = "failed"
                    ctx2["error"] = msg
                    ctx2["failed_at"] = _utc_now().isoformat()
                    if not hook_handled:
                        ctx2["runner_reaper"]["action"] = "fail"
                    tasks_store.update_task(
                        t.id,
                        execution_context=ctx2,
                        status=TaskStatus.FAILED,
                        completed_at=_utc_now(),
                        error=msg,
                    )
                    logger.warning(f"Reaped stale running task task_id={t.id} ({msg})")
            logger.info(
                f"Reaper checked task_id={t.id} - status={t.status} - heartbeat_at={ctx.get('heartbeat_at')} - Threshold={threshold.isoformat()}"
            )
        except Exception as e:
            logger.warning(f"Failed to reap stale task {getattr(t,'id',None)}: {e}")


def _reap_stale_runner_locks(
    tasks_store: TasksStore, locks_store: PostgresRunnerLocksStore, runner_id: str
) -> None:
    stale_seconds = _env_int("LOCAL_CORE_RUNNER_STALE_LOCK_SECONDS", 300)
    now = _utc_now()
    threshold = now - timedelta(seconds=stale_seconds)

    active_runner_ids = set()
    try:
        running = tasks_store.list_running_playbook_execution_tasks(
            workspace_id=None, limit=500
        )
        for t in running:
            ctx = t.execution_context if isinstance(t.execution_context, dict) else {}
            rid = ctx.get("runner_id")
            hb = _parse_utc_iso(ctx.get("heartbeat_at"))
            if rid and hb and hb > threshold:
                active_runner_ids.add(rid)
    except Exception:
        pass

    # Table is managed by Alembic; no ensure_table() needed.

    try:
        with locks_store.get_connection() as conn:
            from sqlalchemy import text as _sa_text

            result = conn.execute(
                _sa_text(
                    "SELECT lock_key, owner_id, expires_at, updated_at FROM runner_locks"
                )
            )
            rows = result.fetchall()
    except Exception:
        return

    for row in rows or []:
        try:
            lock_key = (
                row[0] if not hasattr(row, "_mapping") else row._mapping["lock_key"]
            )
            owner_id = (
                row[1] if not hasattr(row, "_mapping") else row._mapping["owner_id"]
            )
            expires_at_raw = (
                row[2] if not hasattr(row, "_mapping") else row._mapping["expires_at"]
            )
            updated_at_raw = (
                row[3] if not hasattr(row, "_mapping") else row._mapping["updated_at"]
            )
            expires_at = (
                _parse_utc_iso(expires_at_raw)
                if isinstance(expires_at_raw, str)
                else expires_at_raw
            )
            updated_at = (
                _parse_utc_iso(updated_at_raw)
                if isinstance(updated_at_raw, str)
                else updated_at_raw
            )

            if not lock_key or not owner_id:
                continue
            if owner_id == runner_id:
                continue
            if owner_id in active_runner_ids:
                continue

            # Expired locks: delete eagerly regardless of updated_at
            expired = expires_at and expires_at < now
            # Non-expired but stale heartbeat: also delete
            stale = updated_at and updated_at < threshold

            if not expired and not stale:
                continue

            from sqlalchemy import text as _sa_text2

            with locks_store.transaction() as conn:
                conn.execute(
                    _sa_text2("DELETE FROM runner_locks WHERE lock_key = :lk"),
                    {"lk": lock_key},
                )
            logger.warning(
                f"Reaped stale runner lock lock_key={lock_key} owner_id={owner_id} "
                f"expires_at={expires_at_raw} expired={expired} stale={stale}"
            )
        except Exception as e:
            logger.warning(f"Failed to reap lock {row}: {e}")
            continue
