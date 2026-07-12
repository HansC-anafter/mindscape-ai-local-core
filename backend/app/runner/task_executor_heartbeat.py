"""Task executor heartbeat and lease-renew thread helpers."""

from concurrent.futures import TimeoutError as FutureTimeoutError
import logging
import os
import time
from threading import Event, Thread
from typing import Any, Callable, Optional

from backend.app.services.runner_live_state import RunnerLiveStateStore
from backend.app.services.runner_resources import (
    NodeBudgetReservation,
    RedisNodeBudgetStore,
    RedisResourceLeaseStore,
    renew_resource_lease_keys,
)
from backend.app.services.stores.redis.runner_queue_store import RedisRunnerQueueStore

from backend.app.runner.database_backoff import is_database_recovery_error

logger = logging.getLogger(__name__)

_LOOP_TIMEOUT_EXIT_CODE = 75


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _loop_timeout_exit_threshold() -> int:
    return max(1, _env_int("LOCAL_CORE_RUNNER_LOOP_TIMEOUT_EXIT_THRESHOLD", 3))


def _handle_loop_future_timeout(
    *,
    kind: str,
    task: Any,
    owner_id: Optional[str],
    consecutive_timeouts: int,
    threshold: int,
    exit_enabled: bool,
    exit_func: Callable[[int], None] = os._exit,
) -> None:
    logger.warning(
        "Runner main event loop did not service %s future task_id=%s playbook=%s owner_id=%s "
        "consecutive_timeouts=%s threshold=%s exit_enabled=%s",
        kind,
        task.id,
        task.pack_id,
        owner_id,
        consecutive_timeouts,
        threshold,
        exit_enabled,
        exc_info=True,
    )
    if not exit_enabled or consecutive_timeouts < threshold:
        return

    logger.critical(
        "Runner main event loop appears stuck after repeated %s future timeouts; forcing runner process exit "
        "task_id=%s playbook=%s owner_id=%s exit_code=%s",
        kind,
        task.id,
        task.pack_id,
        owner_id,
        _LOOP_TIMEOUT_EXIT_CODE,
    )
    exit_func(_LOOP_TIMEOUT_EXIT_CODE)


def start_heartbeat_thread(
    *,
    asyncio_module: Any,
    main_loop: Any,
    stop_event: Event,
    task: Any,
    tasks_store: Any,
    runner_id: str,
    redis_queue: Optional[RedisRunnerQueueStore],
    runner_live_state: RunnerLiveStateStore,
    node_budget_reservation: Optional[NodeBudgetReservation],
    ownership_lost_event: Event,
    node_budget_ttl_seconds: int,
    heartbeat_interval_ms: int,
    heartbeat_ttl_seconds: int,
    trace_heartbeat: bool,
    proc_ref: list[Any],
) -> Thread:
    node_budget_store = (
        RedisNodeBudgetStore(redis_queue)
        if redis_queue and node_budget_reservation is not None
        else None
    )

    def _heartbeat_thread() -> None:
        interval_s = max(1.0, heartbeat_interval_ms / 1000.0)
        beat_seq = 0
        next_db_recovery_log_at = 0.0
        loop_future_timeouts = 0
        node_budget_future_timeouts = 0
        loop_timeout_exit_enabled = _env_bool(
            "LOCAL_CORE_RUNNER_LOOP_TIMEOUT_EXIT_ENABLED",
            True,
        )
        loop_timeout_threshold = _loop_timeout_exit_threshold()
        while not stop_event.is_set():
            beat_seq += 1
            try:
                p = proc_ref[0]
                if p is not None and not p.is_alive():
                    logger.warning(
                        "Runner heartbeat stopping: subprocess died for task %s "
                        "(playbook=%s beat_seq=%s exitcode=%s)",
                        task.id,
                        task.pack_id,
                        beat_seq,
                        p.exitcode,
                    )
                    break
            except Exception as e:
                logger.error(f"Error checking subprocess alive status in heartbeat thread: {e}", exc_info=True)
            if node_budget_store and node_budget_reservation is not None:
                try:
                    fut = asyncio_module.run_coroutine_threadsafe(
                        node_budget_store.renew(
                            node_budget_reservation,
                            ttl_seconds=node_budget_ttl_seconds,
                        ),
                        main_loop,
                    )
                    renew_ok = fut.result(timeout=10)
                    node_budget_future_timeouts = 0
                    if not renew_ok:
                        logger.warning(
                            "Runner primary heartbeat node budget renew returned false "
                            "task_id=%s playbook=%s owner_id=%s revision=%s ttl_seconds=%s",
                            task.id,
                            task.pack_id,
                            node_budget_reservation.owner_id,
                            node_budget_reservation.revision,
                            node_budget_ttl_seconds,
                        )
                        ownership_lost_event.set()
                        return
                except FutureTimeoutError:
                    node_budget_future_timeouts += 1
                    _handle_loop_future_timeout(
                        kind="node budget renew",
                        task=task,
                        owner_id=node_budget_reservation.owner_id,
                        consecutive_timeouts=node_budget_future_timeouts,
                        threshold=loop_timeout_threshold,
                        exit_enabled=loop_timeout_exit_enabled,
                    )
                except Exception:
                    logger.warning(
                        "Runner primary heartbeat node budget renew failed "
                        "task_id=%s playbook=%s owner_id=%s revision=%s ttl_seconds=%s",
                        task.id,
                        task.pack_id,
                        node_budget_reservation.owner_id,
                        node_budget_reservation.revision,
                        node_budget_ttl_seconds,
                        exc_info=True,
                    )
                    ownership_lost_event.set()
                    return
            try:
                hb_started = time.monotonic()
                if trace_heartbeat and beat_seq <= 3:
                    logger.warning(
                        "Runner heartbeat begin task_id=%s playbook=%s beat_seq=%s phase=abort_check",
                        task.id,
                        task.pack_id,
                        beat_seq,
                    )
                should_abort = tasks_store.update_task_heartbeat(
                    task.id,
                    runner_id=runner_id,
                )
                hb_db_elapsed_ms = int((time.monotonic() - hb_started) * 1000)
                if (trace_heartbeat and beat_seq <= 3) or hb_db_elapsed_ms >= 2000:
                    log_fn = logger.warning if hb_db_elapsed_ms >= 2000 or trace_heartbeat else logger.info
                    log_fn(
                        "Runner heartbeat abort_check done task_id=%s playbook=%s beat_seq=%s elapsed_ms=%s should_abort=%s",
                        task.id,
                        task.pack_id,
                        beat_seq,
                        hb_db_elapsed_ms,
                        should_abort,
                    )
                if should_abort:
                    stop_event.set()
                    break
                live_started = time.monotonic()
                live_ok = runner_live_state.renew_task_heartbeat(
                    task_id=task.id,
                    runner_id=runner_id,
                    workspace_id=task.workspace_id,
                    execution_id=task.execution_id,
                    playbook_code=task.pack_id,
                    queue_shard=getattr(task, "queue_shard", None),
                    ttl_seconds=heartbeat_ttl_seconds,
                )
                hb_live_elapsed_ms = int((time.monotonic() - live_started) * 1000)
                if (trace_heartbeat and beat_seq <= 3) or hb_live_elapsed_ms >= 2000 or not live_ok:
                    log_fn = (
                        logger.warning
                        if hb_live_elapsed_ms >= 2000 or not live_ok or trace_heartbeat
                        else logger.info
                    )
                    log_fn(
                        "Runner heartbeat live_state done task_id=%s playbook=%s beat_seq=%s elapsed_ms=%s ok=%s",
                        task.id,
                        task.pack_id,
                        beat_seq,
                        hb_live_elapsed_ms,
                        live_ok,
                    )
                if redis_queue:
                    redis_started = time.monotonic()
                    if trace_heartbeat and beat_seq <= 3:
                        logger.warning(
                            "Runner heartbeat begin task_id=%s playbook=%s beat_seq=%s phase=touch_visibility",
                            task.id,
                            task.pack_id,
                            beat_seq,
                        )
                    fut = asyncio_module.run_coroutine_threadsafe(
                        redis_queue.touch_visibility_timeout(task.id, added_time_sec=180),
                        main_loop,
                    )
                    touch_ok = fut.result(timeout=10)
                    loop_future_timeouts = 0
                    hb_redis_elapsed_ms = int((time.monotonic() - redis_started) * 1000)
                    if (trace_heartbeat and beat_seq <= 3) or hb_redis_elapsed_ms >= 2000 or not touch_ok:
                        log_fn = (
                            logger.warning
                            if hb_redis_elapsed_ms >= 2000 or not touch_ok or trace_heartbeat
                            else logger.info
                        )
                        log_fn(
                            "Runner heartbeat touch_visibility done task_id=%s playbook=%s beat_seq=%s elapsed_ms=%s ok=%s",
                            task.id,
                            task.pack_id,
                            beat_seq,
                            hb_redis_elapsed_ms,
                            touch_ok,
                        )
            except FutureTimeoutError:
                loop_future_timeouts += 1
                _handle_loop_future_timeout(
                    kind="visibility heartbeat",
                    task=task,
                    owner_id=runner_id,
                    consecutive_timeouts=loop_future_timeouts,
                    threshold=loop_timeout_threshold,
                    exit_enabled=loop_timeout_exit_enabled,
                )
            except Exception as e:
                if is_database_recovery_error(e):
                    now_monotonic = time.monotonic()
                    if now_monotonic >= next_db_recovery_log_at:
                        logger.warning(
                            "Runner heartbeat deferred while PostgreSQL is recovering task_id=%s playbook=%s beat_seq=%s",
                            task.id,
                            task.pack_id,
                            beat_seq,
                        )
                        next_db_recovery_log_at = now_monotonic + 30.0
                else:
                    logger.error(
                        "Error updating heartbeat in heartbeat thread for task %s "
                        "(playbook=%s beat_seq=%s): %s",
                        task.id,
                        task.pack_id,
                        beat_seq,
                        e,
                        exc_info=True,
                    )
            stop_event.wait(interval_s)

    hb_thread = Thread(target=_heartbeat_thread, daemon=True)
    hb_thread.start()
    return hb_thread


def start_lease_renew_thread(
    *,
    asyncio_module: Any,
    main_loop: Any,
    stop_event: Event,
    task: Any,
    redis_queue: Optional[RedisRunnerQueueStore],
    lock_keys: list[str],
    resource_lease_keys: list[str],
    ownership_lost_event: Event,
    lock_owner_id: str,
    lock_ttl_seconds: int,
    heartbeat_interval_ms: int,
) -> Optional[Thread]:
    if not redis_queue or not (lock_keys or resource_lease_keys):
        return None

    resource_lease_store = (
        RedisResourceLeaseStore(redis_queue) if resource_lease_keys else None
    )
    def _renew_thread() -> None:
        interval_s = max(5.0, heartbeat_interval_ms / 1000.0)
        loop_future_timeouts = 0
        loop_timeout_exit_enabled = _env_bool(
            "LOCAL_CORE_RUNNER_LOOP_TIMEOUT_EXIT_ENABLED",
            True,
        )
        loop_timeout_threshold = _loop_timeout_exit_threshold()
        while not stop_event.is_set():
            try:
                for held_key in lock_keys:
                    fut = asyncio_module.run_coroutine_threadsafe(
                        redis_queue.renew_lock(
                            lock_key=held_key,
                            owner_id=lock_owner_id,
                            ttl_seconds=lock_ttl_seconds,
                        ),
                        main_loop,
                    )
                    renew_ok = fut.result(timeout=10)
                    loop_future_timeouts = 0
                    if not renew_ok:
                        logger.warning(
                            "Runner concurrency lock renew returned false task_id=%s playbook=%s lock_key=%s owner_id=%s",
                            task.id,
                            task.pack_id,
                            held_key,
                            lock_owner_id,
                        )
                        ownership_lost_event.set()
                        return
                if resource_lease_store and resource_lease_keys:
                    fut = asyncio_module.run_coroutine_threadsafe(
                        renew_resource_lease_keys(
                            resource_lease_store,
                            resource_lease_keys,
                            owner_id=lock_owner_id,
                            ttl_seconds=lock_ttl_seconds,
                        ),
                        main_loop,
                    )
                    renew_ok = fut.result(timeout=10)
                    loop_future_timeouts = 0
                    if not renew_ok:
                        logger.warning(
                            "Runner resource lease renew returned false task_id=%s playbook=%s owner_id=%s",
                            task.id,
                            task.pack_id,
                            lock_owner_id,
                        )
                        ownership_lost_event.set()
                        return
            except FutureTimeoutError:
                loop_future_timeouts += 1
                _handle_loop_future_timeout(
                    kind="lease renew",
                    task=task,
                    owner_id=lock_owner_id,
                    consecutive_timeouts=loop_future_timeouts,
                    threshold=loop_timeout_threshold,
                    exit_enabled=loop_timeout_exit_enabled,
                )
            except Exception as e:
                ownership_lost_event.set()
                logger.warning(
                    "Runner lease renew failed task_id=%s playbook=%s owner_id=%s: %s",
                    task.id,
                    task.pack_id,
                    lock_owner_id,
                    e,
                    exc_info=True,
                )
                return
            stop_event.wait(interval_s)

    lock_renew_thread = Thread(target=_renew_thread, daemon=True)
    lock_renew_thread.start()
    return lock_renew_thread
