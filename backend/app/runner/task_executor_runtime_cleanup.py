"""Task executor process finalization helpers."""

import logging
import time
from typing import Any, Optional

from backend.app.models.workspace import TaskStatus
from backend.app.services.stores.redis.runner_queue_store import RedisRunnerQueueStore
from backend.app.services.stores.tasks_store import TasksStore

logger = logging.getLogger(__name__)


async def ignore_cancelled(task: Any) -> None:
    try:
        await task
    except BaseException:
        pass


async def handle_control_signal(
    hooks: Any,
    tasks_store: TasksStore,
    task: Any,
    runner_id: str,
    redis_queue: Optional[RedisRunnerQueueStore],
    proc: Any,
    exec_task: Any,
    timeout_task: Any,
    control_task: Any,
) -> None:
    signal = control_task.result() or {}
    logger.warning(
        "Runner control signal received task_id=%s playbook=%s signal=%s",
        task.id,
        task.pack_id,
        signal,
    )
    try:
        if proc.is_alive():
            proc.terminate()
    except Exception:
        pass
    exec_task.cancel()
    timeout_task.cancel()
    await ignore_cancelled(exec_task)
    await ignore_cancelled(timeout_task)
    latest = None
    try:
        latest = await hooks.asyncio_module.to_thread(tasks_store.get_task, task.id)
    except Exception:
        latest = None

    signal_kind = signal.get("kind")
    if signal_kind == "cancelled":
        await finalize_cancelled_task(hooks, tasks_store, latest, task, runner_id, redis_queue)
    elif latest and latest.status in (TaskStatus.FAILED, TaskStatus.EXPIRED):
        hooks.emit_run_state_changed_for_task(
            latest,
            previous_state="RUNNING",
            new_state="FAILED",
            reason=latest.error or "execution_failed",
        )
        if redis_queue:
            try:
                await redis_queue.ack_task(task.id)
            except Exception:
                pass
    else:
        msg = signal.get("message") or "Runner control signal requested abort"
        await hooks.mark_task_failed(tasks_store, task.id, runner_id, msg, redis_queue)


async def finalize_cancelled_task(
    hooks: Any,
    tasks_store: TasksStore,
    latest: Any,
    task: Any,
    runner_id: str,
    redis_queue: Optional[RedisRunnerQueueStore],
) -> None:
    try:
        if latest and latest.status == TaskStatus.CANCELLED_BY_USER:
            ctxc = latest.execution_context if isinstance(latest.execution_context, dict) else {}
            ctxc = dict(ctxc)
            ctxc["status"] = "cancelled"
            ctxc["cancelled_at"] = hooks.utc_now().isoformat()
            ctxc["last_runner_id"] = runner_id
            ctxc.pop("runner_id", None)
            ctxc.pop("heartbeat_at", None)
            tasks_store.update_task(
                latest.id,
                execution_context=ctxc,
                status=TaskStatus.CANCELLED_BY_USER,
                completed_at=hooks.utc_now(),
                error=latest.error or "Cancelled by user",
                runner_id=None,
                heartbeat_at=None,
            )
    except Exception:
        pass
    if redis_queue:
        try:
            await redis_queue.ack_task(task.id)
        except Exception:
            pass


async def finalize_process_exit(
    hooks: Any,
    tasks_store: TasksStore,
    task: Any,
    runner_id: str,
    result_file: Optional[str],
    redis_queue: Optional[RedisRunnerQueueStore],
    exitcode: int,
) -> None:
    if exitcode != 0:
        msg = hooks.build_subprocess_failure_message(result_file, exitcode)
        from backend.app.runner.resource_pressure import classify_subprocess_resource_failure
        from backend.app.runner.resource_pressure import resource_failure_retry_delay_seconds

        resource_source = classify_subprocess_resource_failure(exitcode, msg)
        resource_snapshot = None
        retry_delay_sec = 15
        if resource_source:
            retry_delay_sec = resource_failure_retry_delay_seconds()
            resource_snapshot = hooks.build_resource_failure_snapshot(inflight=1)
        await hooks.mark_task_failed(
            tasks_store,
            task.id,
            runner_id,
            msg,
            redis_queue,
            retry_delay_sec=retry_delay_sec,
            resource_pressure_source=resource_source,
            resource_snapshot=resource_snapshot,
        )
    else:
        await hooks.mark_task_succeeded(tasks_store, task.id, runner_id, result_file, redis_queue)


async def wait_for_late_subprocess(
    hooks: Any,
    tasks_store: TasksStore,
    task: Any,
    runner_id: str,
    result_file: Optional[str],
    redis_queue: Optional[RedisRunnerQueueStore],
    proc: Any,
    task_timeout_seconds: int,
) -> None:
    logger.warning(
        "Runner orchestration reached cleanup before subprocess exit; "
        "waiting for child task_id=%s playbook=%s pid=%s timeout=%ss",
        task.id,
        task.pack_id,
        proc.pid,
        task_timeout_seconds,
    )
    try:
        cleanup_deadline = time.monotonic() + max(1, int(task_timeout_seconds))
        while proc.is_alive() and time.monotonic() < cleanup_deadline:
            await hooks.asyncio_module.sleep(0.5)
        if not proc.is_alive():
            exitcode = proc.exitcode
            if exitcode is None:
                exitcode = -1
            await finalize_process_exit(
                hooks, tasks_store, task, runner_id, result_file, redis_queue, int(exitcode)
            )
    except BaseException:
        logger.exception("Runner cleanup wait failed for task %s", task.id)


async def cleanup_process(
    hooks: Any,
    tasks_store: TasksStore,
    task: Any,
    runner_id: str,
    redis_queue: Optional[RedisRunnerQueueStore],
    proc: Any,
) -> None:
    try:
        if proc:
            proc.join(timeout=5.0)
            if proc.is_alive():
                logger.warning(f"Runner subprocess still alive after join, killing task {task.id}")
                proc.kill()
                proc.join(timeout=1.0)
                latest = None
                try:
                    latest = tasks_store.get_task(task.id)
                except Exception:
                    latest = None
                terminal_statuses = {
                    TaskStatus.SUCCEEDED,
                    TaskStatus.FAILED,
                    TaskStatus.CANCELLED_BY_USER,
                    TaskStatus.EXPIRED,
                }
                if not latest or latest.status not in terminal_statuses:
                    await hooks.mark_task_failed(
                        tasks_store,
                        task.id,
                        runner_id,
                        f"Runner subprocess killed after join timeout (pid={proc.pid})",
                        redis_queue,
                    )
    except Exception as e:
        logger.warning(f"Runner subprocess cleanup error for task {task.id}: {e}")
