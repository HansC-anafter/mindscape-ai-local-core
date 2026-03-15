"""Runner worker — main loop coordinator.

This file was refactored from a 1150-line monolith into a slim coordinator
that delegates to focused sub-modules:

  utils.py          — _utc_now, _parse_utc_iso, _env_int
  concurrency.py    — _runner_id, _resolve_lock_key, _build_inputs
  lifecycle_hooks.py — _invoke_on_fail_hook
  reaper.py         — _reap_stale_running_tasks, _reap_stale_runner_locks
  task_executor.py  — _child_execute_playbook, _run_single_task
  restart.py        — _check_restart_sentinel
"""

import asyncio
import logging
import os
import sys
from typing import Optional
from datetime import datetime

from backend.app.models.workspace import TaskStatus
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.stores.tasks_store import TasksStore
from backend.app.services.stores.postgres.runner_locks_store import (
    PostgresRunnerLocksStore,
)

# ── Sub-module imports ──
from backend.app.runner.utils import _utc_now, _parse_utc_iso, _env_int
from backend.app.runner.concurrency import (
    _runner_id,
    _resolve_lock_key,
    _build_inputs,
    _is_ig_playbook,
)
from backend.app.runner.lifecycle_hooks import _invoke_on_fail_hook
from backend.app.runner.reaper import (
    _reap_stale_running_tasks,
    _reap_stale_runner_locks,
)
from backend.app.runner.task_executor import (
    _child_execute_playbook,
    _initialize_capability_packages_for_runner,
    _run_single_task,
)
from backend.app.runner.restart import (
    _check_restart_sentinel,
    _RESTART_SENTINEL_PATH,
    _RESTART_DRAIN_TIMEOUT_SECONDS,
)

logger = logging.getLogger(__name__)

# Re-export all public symbols so existing imports (e.g. tests) keep working.
__all__ = [
    "_utc_now",
    "_parse_utc_iso",
    "_env_int",
    "_runner_id",
    "_resolve_lock_key",
    "_build_inputs",
    "_is_ig_playbook",
    "_invoke_on_fail_hook",
    "_reap_stale_running_tasks",
    "_reap_stale_runner_locks",
    "_child_execute_playbook",
    "_initialize_capability_packages_for_runner",
    "_run_single_task",
    "_check_restart_sentinel",
    "_RESTART_SENTINEL_PATH",
    "_RESTART_DRAIN_TIMEOUT_SECONDS",
    "run_forever",
    "main",
]


# ============================================================
#  Main runner loop
# ============================================================


async def run_forever() -> None:
    poll_interval_ms = _env_int("LOCAL_CORE_RUNNER_POLL_INTERVAL_MS", 1000)
    max_inflight = _env_int("LOCAL_CORE_RUNNER_MAX_INFLIGHT", 1)
    # Poll a bit more than inflight so we can quickly fill capacity.
    batch_limit = _env_int(
        "LOCAL_CORE_RUNNER_POLL_BATCH_LIMIT", max(1, max_inflight * 2)
    )
    runner_id = _runner_id()

    store = MindscapeStore()
    tasks_store = TasksStore()
    locks_store = PostgresRunnerLocksStore()

    logger.info(
        f"Local-Core runner started runner_id={runner_id} poll_interval_ms={poll_interval_ms} max_inflight={max_inflight}"
    )

    # Ensure heartbeat table exists before entering the poll loop.
    try:
        tasks_store.ensure_runner_heartbeats_table()
    except Exception:
        pass

    inflight: set[asyncio.Task] = set()
    last_reap_at: Optional[datetime] = None
    reap_interval_seconds = _env_int("LOCAL_CORE_RUNNER_REAP_INTERVAL_SECONDS", 60)

    while True:
        # Periodic reaping for runner restarts / orphaned tasks.
        try:
            now = _utc_now()
            if (last_reap_at is None) or (
                (now - last_reap_at).total_seconds() >= reap_interval_seconds
            ):
                _reap_stale_running_tasks(tasks_store, runner_id=runner_id)
                _reap_stale_runner_locks(tasks_store, locks_store, runner_id=runner_id)
                last_reap_at = now
        except Exception:
            pass

        # Runner liveness heartbeat via shared PostgreSQL.
        try:
            tasks_store.upsert_runner_heartbeat(runner_id)
        except Exception:
            pass

        # Restart sentinel: backend writes this when Device Node is unreachable.
        # Drain inflight tasks gracefully, then exit for Docker auto-restart.
        if _check_restart_sentinel():
            if inflight:
                logger.info(
                    "Restart sentinel: waiting for %d inflight tasks to drain "
                    "(max %ds)",
                    len(inflight),
                    _RESTART_DRAIN_TIMEOUT_SECONDS,
                )
                drain_deadline = (
                    asyncio.get_event_loop().time() + _RESTART_DRAIN_TIMEOUT_SECONDS
                )
                while inflight and asyncio.get_event_loop().time() < drain_deadline:
                    done = {t for t in inflight if t.done()}
                    for t in done:
                        inflight.discard(t)
                        try:
                            _ = t.result()
                        except Exception:
                            pass
                    if inflight:
                        await asyncio.sleep(1.0)
                if inflight:
                    logger.warning(
                        "Restart sentinel: %d tasks still inflight after drain timeout, "
                        "forcing exit",
                        len(inflight),
                    )
            logger.info("Runner exiting for restart (sentinel)")
            sys.exit(1)

        # Cleanup finished tasks
        try:
            done = {t for t in inflight if t.done()}
            for t in done:
                inflight.discard(t)
                try:
                    _ = t.result()
                except Exception:
                    pass
        except Exception:
            pass

        if len(inflight) >= max_inflight:
            await asyncio.sleep(poll_interval_ms / 1000)
            continue

        tasks = []
        try:
            tasks = tasks_store.list_runnable_playbook_execution_tasks(
                limit=batch_limit
            )
        except Exception as e:
            logger.warning(f"Runner poll failed: {e}")

        if not tasks:
            await asyncio.sleep(poll_interval_ms / 1000)
            continue

        from datetime import datetime, timedelta, timezone

        dispatched_lock_keys: set = set()

        for t in tasks:
            try:
                if len(inflight) >= max_inflight:
                    break
                if t.status == TaskStatus.CANCELLED_BY_USER:
                    continue
                lock_ctx = (
                    t.execution_context if isinstance(t.execution_context, dict) else {}
                )
                lock_key = _resolve_lock_key(lock_ctx, t.pack_id)
                if lock_key:
                    owner = locks_store.get_owner(lock_key)
                    in_poll_conflict = lock_key in dispatched_lock_keys

                    if owner is not None or in_poll_conflict:
                        try:
                            ctx2 = dict(lock_ctx)
                            ctx2["runner_skip_reason"] = "concurrency_locked"
                            ctx2["runner_skip_lock_key"] = lock_key
                            ctx2["runner_skip_owner"] = owner if owner is not None else "in_poll_dedup"
                            
                            resume_dt = datetime.now(timezone.utc) + timedelta(seconds=15)
                            ctx2["resume_after"] = resume_dt.isoformat()
                            
                            tasks_store.update_task(t.id, execution_context=ctx2)
                        except Exception:
                            pass
                        continue

                claimed = tasks_store.try_claim_task(t.id, runner_id=runner_id)
                if not claimed:
                    continue
                if lock_key:
                    dispatched_lock_keys.add(lock_key)
                task_coro = _run_single_task(tasks_store, runner_id, t.id)
                inflight.add(asyncio.create_task(task_coro))
            except Exception as e:
                logger.warning(f"Runner task dispatch error: {e}", exc_info=True)

        await asyncio.sleep(poll_interval_ms / 1000)


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    _initialize_capability_packages_for_runner()
    try:
        store = MindscapeStore()
        tasks_store = TasksStore()
        rid = _runner_id()
        _reap_stale_running_tasks(tasks_store, runner_id=rid)
        _reap_stale_runner_locks(tasks_store, PostgresRunnerLocksStore(), runner_id=rid)
    except Exception:
        pass
    asyncio.run(run_forever())


if __name__ == "__main__":
    main()
