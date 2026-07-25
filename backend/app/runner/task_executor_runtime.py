"""Task executor orchestration runtime."""

import logging
import os
import threading
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

from backend.app.models.workspace import TaskStatus
from backend.app.services.runner_live_state import RunnerLiveStateStore
from backend.app.services.runner_resources import (
    NodeBudgetReservation,
    RedisNodeBudgetStore,
    reservation_from_context,
    resource_lease_keys_from_context,
)
from backend.app.services.stores.redis.runner_queue_store import RedisRunnerQueueStore
from backend.app.services.stores.tasks_store import TasksStore

from backend.app.runner.concurrency import _resolve_lock_keys
from backend.app.runner.task_executor_heartbeat import (
    start_heartbeat_thread,
    start_lease_renew_thread,
)
from backend.app.runner.task_executor_process import (
    build_child_payload,
    create_result_file,
    start_child_process,
    wait_for_process_exit,
)
from backend.app.runner.task_executor_runtime_cleanup import (
    cleanup_process,
    finalize_process_exit,
    handle_control_signal,
    ignore_cancelled,
    wait_for_late_subprocess,
)
from backend.app.runner.utils import _env_int

logger = logging.getLogger(__name__)


async def _renew_node_budget_before_child(
    redis_queue: Optional[RedisRunnerQueueStore],
    reservation: Optional[NodeBudgetReservation],
    *,
    ttl_seconds: int,
) -> bool:
    if reservation is None:
        return True
    if redis_queue is None:
        return False
    return await RedisNodeBudgetStore(redis_queue).renew(
        reservation,
        ttl_seconds=ttl_seconds,
    )


@dataclass(frozen=True)
class TaskExecutorHooks:
    asyncio_module: Any
    mp_module: Any
    resolve_execution_attempt_inputs: Callable[..., Any]
    park_task_after_intent_resolution: Callable[..., Awaitable[None]]
    release_task_locks: Callable[..., Awaitable[None]]
    release_task_resource_leases: Callable[..., Awaitable[None]]
    get_task_control_signal: Callable[..., Optional[dict[str, str]]]
    apply_runtime_binding_to_playbook_task: Callable[..., Any]
    serialize_runtime_binding: Callable[..., dict[str, Any]]
    prepare_runner_child_admission: Callable[..., Awaitable[Any]]
    park_task_for_runner_admission: Callable[..., Awaitable[None]]
    child_execute_playbook: Callable[[dict[str, Any]], None]
    build_subprocess_failure_message: Callable[[Optional[str], int], str]
    build_resource_failure_snapshot: Callable[..., Optional[dict[str, Any]]]
    mark_task_failed: Callable[..., Awaitable[None]]
    mark_task_succeeded: Callable[..., Awaitable[None]]
    emit_run_state_changed_for_task: Callable[..., None]
    utc_now: Callable[[], Any]


async def _run_single_task_impl(
    tasks_store: TasksStore,
    runner_id: str,
    task_id: str,
    redis_queue: Optional[RedisRunnerQueueStore],
    lock_owner_id: Optional[str],
    hooks: TaskExecutorHooks,
    admitted_node_budget_reservation: Optional[NodeBudgetReservation] = None,
) -> None:
    asyncio_mod = hooks.asyncio_module
    task = tasks_store.get_task(task_id)
    if not task:
        if redis_queue:
            await redis_queue.ack_task(task_id)
        return

    if task.status == TaskStatus.CANCELLED_BY_USER:
        if redis_queue:
            await redis_queue.ack_task(task_id)
        return

    os.environ["LOCAL_CORE_RUNNER_PROCESS"] = "1"
    ctx = task.execution_context if isinstance(task.execution_context, dict) else {}
    lock_keys = _resolve_lock_keys(
        ctx,
        task.pack_id,
        persisted_concurrency_key=getattr(task, "concurrency_key", None),
    )
    resource_lease_keys = resource_lease_keys_from_context(ctx)
    node_budget_reservation = (
        admitted_node_budget_reservation or reservation_from_context(ctx)
    )
    lock_owner_id = lock_owner_id or runner_id
    lock_ttl_seconds = _env_int("LOCAL_CORE_RUNNER_LOCK_TTL_SECONDS", 120)
    stop_event = threading.Event()
    ownership_lost_event = threading.Event()
    hb_thread: Optional[threading.Thread] = None
    lock_renew_thread = None
    proc = None
    result_file = None
    exec_task = None
    control_task = None
    timeout_task = None
    task_finalized = False
    task_timeout_seconds = _env_int("LOCAL_CORE_RUNNER_TASK_TIMEOUT_SECONDS", 3600)
    resource_baseline = None

    try:
        ctx2 = dict(ctx)
        if (
            ctx2.get("runner_skip_reason")
            or ctx2.get("runner_skip_owner")
            or ctx2.get("resume_after")
            or ctx2.get("dependency_hold")
            or ctx2.get("watchdog_abort_requested_at")
            or ctx2.get("watchdog_abort_reason")
            or ctx2.get("watchdog_abort")
        ):
            ctx2.pop("runner_skip_reason", None)
            ctx2.pop("runner_skip_owner", None)
            ctx2.pop("runner_skip_lock_key", None)
            ctx2.pop("resume_after", None)
            ctx2.pop("dependency_hold", None)
            ctx2.pop("watchdog_abort_requested_at", None)
            ctx2.pop("watchdog_abort_reason", None)
            ctx2.pop("watchdog_abort", None)
            tasks_store.update_task(task.id, execution_context=ctx2)
            ctx = ctx2
    except Exception:
        pass

    inputs, intent_resolution = hooks.resolve_execution_attempt_inputs(task, ctx)
    if intent_resolution.park_task:
        try:
            await hooks.park_task_after_intent_resolution(
                tasks_store,
                task,
                runner_id,
                intent_resolution,
                redis_queue,
            )
        finally:
            await hooks.release_task_locks(redis_queue, lock_keys, lock_owner_id)
            await hooks.release_task_resource_leases(
                redis_queue,
                resource_lease_keys,
                lock_owner_id,
                node_budget_reservation,
            )
        return

    resolved_profile_id = (
        getattr(task, "profile_id", None)
        or (ctx.get("profile_id") if isinstance(ctx, dict) else None)
        or "default-user"
    )
    inputs, ctx, runtime_binding = hooks.apply_runtime_binding_to_playbook_task(
        task,
        ctx,
        inputs,
        profile_id=resolved_profile_id,
    )
    runtime_binding_payload = hooks.serialize_runtime_binding(runtime_binding)
    if runtime_binding_payload:
        try:
            tasks_store.update_task(task.id, execution_context=ctx)
        except Exception:
            logger.warning(
                "Failed to persist runtime binding for task %s",
                task.id,
                exc_info=True,
            )
        logger.info(
            "Runner resolved runtime binding task=%s playbook=%s dispatch_mode=%s runtime_id=%s site_key=%s device_id=%s via=%s",
            task.id,
            task.pack_id,
            runtime_binding_payload.get("dispatch_mode"),
            runtime_binding_payload.get("runtime_id"),
            runtime_binding_payload.get("site_key"),
            runtime_binding_payload.get("device_id"),
            runtime_binding_payload.get("via"),
        )

    try:
        admission = await hooks.prepare_runner_child_admission(
            task,
            inputs,
            ctx,
            profile_id=resolved_profile_id,
        )
        inputs = admission.inputs
        ctx = admission.execution_context
        if admission.changed:
            tasks_store.update_task(task.id, execution_context=ctx)
    except Exception as admission_error:
        try:
            await hooks.park_task_for_runner_admission(
                tasks_store,
                task,
                runner_id,
                admission_error,
                redis_queue,
            )
        finally:
            await hooks.release_task_locks(
                redis_queue,
                lock_keys,
                lock_owner_id,
            )
            await hooks.release_task_resource_leases(
                redis_queue,
                resource_lease_keys,
                lock_owner_id,
                node_budget_reservation,
            )
        return

    hb_interval_ms = _env_int("LOCAL_CORE_RUNNER_HEARTBEAT_INTERVAL_MS", 15000)
    heartbeat_ttl_seconds = max(60, int((hb_interval_ms / 1000.0) * 4))
    runner_live_state = RunnerLiveStateStore()
    main_loop = asyncio_mod.get_running_loop()
    proc_ref = [None]
    trace_heartbeat = bool(ctx.get("trace_runner_heartbeat"))

    if node_budget_reservation is not None:
        renew_ok = await _renew_node_budget_before_child(
            redis_queue,
            node_budget_reservation,
            ttl_seconds=lock_ttl_seconds,
        )
        if not renew_ok:
            logger.warning(
                "Runner prelaunch node budget renew failed task_id=%s playbook=%s "
                "owner_id=%s revision=%s ttl_seconds=%s",
                task.id,
                task.pack_id,
                node_budget_reservation.owner_id,
                node_budget_reservation.revision,
                lock_ttl_seconds,
            )
            await hooks.mark_task_failed(
                tasks_store,
                task.id,
                runner_id,
                "Runner node budget ownership was not valid before child launch",
                redis_queue,
                resource_pressure_source="resource_ownership_lost",
            )
            await hooks.release_task_locks(
                redis_queue,
                lock_keys,
                lock_owner_id,
            )
            await hooks.release_task_resource_leases(
                redis_queue,
                resource_lease_keys,
                lock_owner_id,
                node_budget_reservation,
            )
            return

    hb_thread = start_heartbeat_thread(
        asyncio_module=asyncio_mod,
        main_loop=main_loop,
        stop_event=stop_event,
        task=task,
        tasks_store=tasks_store,
        runner_id=runner_id,
        redis_queue=redis_queue,
        runner_live_state=runner_live_state,
        node_budget_reservation=node_budget_reservation,
        ownership_lost_event=ownership_lost_event,
        node_budget_ttl_seconds=lock_ttl_seconds,
        heartbeat_interval_ms=hb_interval_ms,
        heartbeat_ttl_seconds=heartbeat_ttl_seconds,
        trace_heartbeat=trace_heartbeat,
        proc_ref=proc_ref,
    )
    lock_renew_thread = start_lease_renew_thread(
        asyncio_module=asyncio_mod,
        main_loop=main_loop,
        stop_event=stop_event,
        task=task,
        redis_queue=redis_queue,
        lock_keys=lock_keys,
        resource_lease_keys=resource_lease_keys,
        ownership_lost_event=ownership_lost_event,
        lock_owner_id=lock_owner_id,
        lock_ttl_seconds=lock_ttl_seconds,
        heartbeat_interval_ms=hb_interval_ms,
    )

    try:
        cancel_poll_ms = _env_int("LOCAL_CORE_RUNNER_CANCEL_POLL_INTERVAL_MS", 2000)
        ctx_timeout = ctx.get("runner_timeout_seconds")
        if isinstance(ctx_timeout, (int, float)) and ctx_timeout > 0:
            max_ceiling = _env_int("LOCAL_CORE_RUNNER_MAX_TIMEOUT_SECONDS", 43200)
            task_timeout_seconds = min(int(ctx_timeout), max_ceiling)
            logger.info(
                f"Runner using spec-declared timeout={task_timeout_seconds}s "
                f"for task {task.id} (ceiling={max_ceiling}s)"
            )
        ctx_mp = hooks.mp_module.get_context("spawn")

        async def _wait_for_control_signal() -> Optional[dict[str, str]]:
            while True:
                if ownership_lost_event.is_set():
                    return {
                        "kind": "resource_ownership_lost",
                        "message": "Runner resource reservation ownership was lost",
                    }
                try:
                    latest = await asyncio_mod.to_thread(tasks_store.get_task, task.id)
                    signal = hooks.get_task_control_signal(latest)
                    if signal:
                        return signal
                except Exception:
                    pass
                await asyncio_mod.sleep(cancel_poll_ms / 1000)

        result_file = create_result_file(task.id)
        payload = build_child_payload(
            task=task,
            runner_id=runner_id,
            inputs=inputs,
            ctx=ctx,
            resolved_profile_id=resolved_profile_id,
            result_file=result_file,
        )
        resource_baseline = hooks.build_resource_failure_snapshot(inflight=1)
        proc = start_child_process(
            ctx_mp=ctx_mp,
            target=hooks.child_execute_playbook,
            payload=payload,
            task=task,
            trace_heartbeat=trace_heartbeat,
        )
        proc_ref[0] = proc

        async def _wait_for_proc() -> int:
            return await wait_for_process_exit(
                proc=proc,
                task=task,
                trace_heartbeat=trace_heartbeat,
                asyncio_module=asyncio_mod,
            )

        async def _wait_for_timeout() -> bool:
            await asyncio_mod.sleep(task_timeout_seconds)
            return True

        exec_task = asyncio_mod.create_task(_wait_for_proc())
        control_task = asyncio_mod.create_task(_wait_for_control_signal())
        timeout_task = asyncio_mod.create_task(_wait_for_timeout())

        done, _pending = await asyncio_mod.wait(
            {exec_task, control_task, timeout_task},
            return_when=asyncio_mod.FIRST_COMPLETED,
        )
        done_labels = []
        if exec_task in done:
            done_labels.append("exec")
        if control_task in done:
            done_labels.append("control")
        if timeout_task in done:
            done_labels.append("timeout")
        logger.info(
            "Runner wait completed task_id=%s playbook=%s done=%s proc_alive=%s",
            task.id,
            task.pack_id,
            ",".join(done_labels) or "unknown",
            proc.is_alive() if proc else None,
        )

        if control_task in done:
            await handle_control_signal(
                hooks, tasks_store, task, runner_id, redis_queue, proc,
                exec_task, timeout_task, control_task,
            )
            task_finalized = True
        elif timeout_task in done and timeout_task.result() is True:
            try:
                if proc.is_alive():
                    proc.terminate()
            except Exception:
                pass
            exec_task.cancel()
            control_task.cancel()
            await ignore_cancelled(exec_task)
            await ignore_cancelled(control_task)
            msg = f"Runner task timeout ({task_timeout_seconds}s) - subprocess terminated"
            await hooks.mark_task_failed(tasks_store, task.id, runner_id, msg, redis_queue)
            task_finalized = True
        else:
            control_task.cancel()
            timeout_task.cancel()
            await ignore_cancelled(control_task)
            await ignore_cancelled(timeout_task)
            exitcode = await exec_task
            await finalize_process_exit(
                hooks,
                tasks_store,
                task,
                runner_id,
                result_file,
                redis_queue,
                exitcode,
                resource_baseline,
            )
            task_finalized = True
    finally:
        if proc and proc.is_alive() and not task_finalized:
            await wait_for_late_subprocess(
                hooks, tasks_store, task, runner_id, result_file, redis_queue,
                proc, task_timeout_seconds, resource_baseline,
            )
        try:
            if result_file and os.path.exists(result_file):
                os.unlink(result_file)
        except Exception:
            pass
        stop_event.set()
        await cleanup_process(hooks, tasks_store, task, runner_id, redis_queue, proc)
        if hb_thread:
            try:
                hb_thread.join(timeout=1.0)
            except Exception:
                pass
        try:
            runner_live_state.clear_task_heartbeat(task_id=task.id, runner_id=runner_id)
        except Exception:
            pass
        if lock_renew_thread:
            try:
                lock_renew_thread.join(timeout=1.0)
            except Exception:
                pass
        ctx = task.execution_context if isinstance(task.execution_context, dict) else {}
        lock_keys = _resolve_lock_keys(
            ctx,
            task.pack_id,
            persisted_concurrency_key=getattr(task, "concurrency_key", None),
        )
        await hooks.release_task_locks(redis_queue, lock_keys, lock_owner_id)
        await hooks.release_task_resource_leases(
            redis_queue,
            resource_lease_keys,
            lock_owner_id,
            node_budget_reservation,
        )
