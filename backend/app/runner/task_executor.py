"""Runner task executor — subprocess spawn and task lifecycle management."""

import asyncio
import json
import logging
import multiprocessing as mp
import os
import threading
from datetime import timedelta
from typing import Any, Dict, Optional

from backend.app.models.workspace import Task, TaskStatus
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.playbook_run_executor import PlaybookRunExecutor
from backend.app.services.stores.tasks_store import TasksStore
from backend.app.services.stores.redis.runner_queue_store import RedisRunnerQueueStore

from backend.app.runner.concurrency import _build_inputs, _resolve_lock_key
from backend.app.runner.lifecycle_hooks import _invoke_on_fail_hook
from backend.app.runner.utils import _env_int, _utc_now

logger = logging.getLogger(__name__)


def _initialize_capability_packages_for_runner() -> None:
    try:
        from pathlib import Path

        from backend.app.services.capability_registry import get_registry, load_capabilities
        from backend.app.services.capability_tool_loader import load_all_capability_tools

        app_dir = Path(__file__).resolve().parent.parent
        capabilities_dir = (app_dir / "capabilities").resolve()
        load_capabilities(capabilities_dir)
        load_all_capability_tools()

        registry = get_registry()
        logger.info(
            f"Runner capability packages loaded: {len(registry.list_capabilities())} capabilities, {len(registry.list_tools())} tools"
        )
    except Exception as e:
        logger.error(f"Runner failed to load capability packages: {e}", exc_info=True)


def _child_execute_playbook(payload: Dict[str, Any]) -> None:
    """
    Run a single playbook or tool execution inside a dedicated process.
    This isolates Playwright/driver hangs that may hold the GIL and would otherwise
    freeze runner heartbeats/lock renew threads.
    """
    os.environ["LOCAL_CORE_RUNNER_PROCESS"] = "1"
    try:
        _initialize_capability_packages_for_runner()
    except Exception:
        pass

    task_type = payload.get("task_type", "playbook_execution")
    playbook_code = payload.get("playbook_code")
    profile_id = payload.get("profile_id")
    inputs = payload.get("inputs")
    workspace_id = payload.get("workspace_id")
    project_id = payload.get("project_id")
    result_file = payload.get("_result_file")

    async def _run() -> None:
        if task_type == "tool_execution":
            # Direct tool invocation via UnifiedToolExecutor
            tool_name = payload.get("tool_name") or playbook_code
            from backend.app.services.unified_tool_executor import (
                UnifiedToolExecutor,
            )

            executor = UnifiedToolExecutor()
            result = await executor.execute_tool(
                tool_name=tool_name,
                arguments=inputs or {},
            )
            if not result.success:
                raise RuntimeError(
                    f"Tool execution failed for '{tool_name}': {result.error}"
                )
            # Write result to temp file for parent process to read
            if result_file:
                import json as _json

                try:
                    with open(result_file, "w") as f:
                        _json.dump(result.to_dict(), f)
                except Exception:
                    pass
        else:
            # Standard playbook execution path
            executor = PlaybookRunExecutor()
            await executor.execute_playbook_run(
                playbook_code=playbook_code,
                profile_id=profile_id,
                inputs=inputs,
                workspace_id=workspace_id,
                project_id=project_id,
            )

    asyncio.run(_run())


# ---------------------------------------------------------------------------
#  Extracted helpers: deduplicate failure / success task-update patterns
# ---------------------------------------------------------------------------


def _mark_task_failed(
    tasks_store: TasksStore,
    task_id: str,
    runner_id: str,
    msg: str,
    redis_queue: Optional[RedisRunnerQueueStore] = None,
) -> None:
    """Mark a task as FAILED, increment retry_count, and NACK or Deadletter via Redis."""
    max_attempts = _env_int("LOCAL_CORE_RUNNER_MAX_ATTEMPTS", 3)
    try:
        latest = tasks_store.get_task(task_id)
        if latest and latest.status not in (
            TaskStatus.CANCELLED_BY_USER,
            TaskStatus.FAILED,
        ):
            ctxf = (
                latest.execution_context
                if isinstance(latest.execution_context, dict)
                else {}
            )
            ctxf = dict(ctxf)
            retry_count = ctxf.get("retry_count", 0) + 1
            ctxf["retry_count"] = retry_count
            ctxf["error"] = msg
            ctxf["runner_id"] = runner_id
            ctxf["failed_at"] = _utc_now().isoformat()
            
            is_deadletter = retry_count >= max_attempts

            # For terminal deadletters, change status to FAILED.
            # Otherwise we keep it as PENDING but defer it to delayed queue.
            new_status = TaskStatus.FAILED if is_deadletter else TaskStatus.PENDING
            ctxf["status"] = "failed" if is_deadletter else "queued"

            # Invoke on_fail hook (best-effort, may create follow-up tasks).
            # Hook result is logged but does NOT gate the DB status update.
            try:
                _invoke_on_fail_hook(ctxf, msg, latest.id)
            except Exception as hook_err:
                logger.warning(f"on_fail hook error for task {task_id}: {hook_err}")

            # 1. Strict DB write first
            tasks_store.update_task(
                latest.id,
                execution_context=ctxf,
                status=new_status,
                completed_at=_utc_now() if is_deadletter else None,
                error=msg if is_deadletter else None,
            )

            # 2. Redis Transport resolution
            if redis_queue:
                import asyncio
                if is_deadletter:
                    logger.warning(f"Task {task_id} reached max_attempts ({max_attempts}). Sending to Deadletter.")
                    asyncio.run(redis_queue.move_to_deadletter(task_id))
                    asyncio.run(redis_queue.ack_task(task_id)) # Clean up from processing
                else:
                    logger.warning(f"Task {task_id} failed transiently (attempt {retry_count}). NACKing to delayed queue.")
                    asyncio.run(redis_queue.nack_task_to_delayed(task_id, delay_sec=15))
    except Exception as e:
        logger.error(f"Failed to mark task {task_id} as failed: {e}", exc_info=True)


def _mark_task_succeeded(
    tasks_store: TasksStore,
    task_id: str,
    runner_id: str,
    result_file: Optional[str],
    redis_queue: Optional[RedisRunnerQueueStore] = None,
) -> None:
    """Mark a task as SUCCEEDED, reading tool result from IPC temp file."""
    try:
        # Read tool result from temp file IPC
        tool_result = None
        if result_file and os.path.exists(result_file):
            try:
                with open(result_file, "r") as f:
                    tool_result = json.load(f)
            except Exception:
                pass

        latest = tasks_store.get_task(task_id)
        if latest and latest.status not in (
            TaskStatus.CANCELLED_BY_USER,
            TaskStatus.FAILED,
        ):
            ctxs = (
                latest.execution_context
                if isinstance(latest.execution_context, dict)
                else {}
            )
            ctxs = dict(ctxs)
            ctxs["status"] = "succeeded"
            ctxs["runner_id"] = runner_id
            ctxs["completed_at"] = _utc_now().isoformat()
            update_kwargs = dict(
                execution_context=ctxs,
                status=TaskStatus.SUCCEEDED,
                completed_at=_utc_now(),
            )
            if tool_result is not None:
                update_kwargs["result"] = tool_result
            
            # 1. DB Write MUST precede Ack
            tasks_store.update_task(
                latest.id,
                **update_kwargs,
            )
            
            # 2. Redis Ack
            if redis_queue:
                import asyncio
                asyncio.run(redis_queue.ack_task(task_id))
    except Exception as e:
        logger.error(f"Failed to mark task {task_id} as succeeded: {e}", exc_info=True)


# ---------------------------------------------------------------------------
#  Main task execution orchestrator
# ---------------------------------------------------------------------------


async def _run_single_task(
    tasks_store: TasksStore, runner_id: str, task_id: str, redis_queue: Optional[RedisRunnerQueueStore] = None
) -> None:
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
    inflight_files = set()

    ctx = task.execution_context if isinstance(task.execution_context, dict) else {}
    lock_key = _resolve_lock_key(ctx, task.pack_id)
    lock_ttl_seconds = _env_int("LOCAL_CORE_RUNNER_LOCK_TTL_SECONDS", 120)
    
    # Lock has ALREADY been acquired by runner/worker.py in the Redis store.
    # We clear any leftover UI lock status metadata as this task is executing now.
    try:
        ctx2 = dict(ctx)
        if ctx2.get("runner_skip_reason") or ctx2.get("runner_skip_owner") or ctx2.get("resume_after"):
            ctx2.pop("runner_skip_reason", None)
            ctx2.pop("runner_skip_owner", None)
            ctx2.pop("runner_skip_lock_key", None)
            ctx2.pop("resume_after", None)
            tasks_store.update_task(task.id, execution_context=ctx2)
    except Exception:
        pass
        
    inputs = _build_inputs(task.execution_id or task.id, ctx)

    hb_interval_ms = _env_int("LOCAL_CORE_RUNNER_HEARTBEAT_INTERVAL_MS", 15000)
    # Heartbeat/lock renew must keep ticking even if the main async task blocks (e.g. Playwright hanging).
    stop_event = threading.Event()

    # proc reference will be set before heartbeat starts checking it
    proc_ref = [None]  # Use list for mutable reference in closure

    def _heartbeat_thread() -> None:
        interval_s = max(1.0, hb_interval_ms / 1000.0)
        while not stop_event.is_set():
            # Check if subprocess is still running - stop heartbeat if subprocess died
            try:
                p = proc_ref[0]
                if p is not None and not p.is_alive():
                    logger.warning(
                        f"Runner heartbeat stopping: subprocess died for task {task.id}, exitcode={p.exitcode}"
                    )
                    break
            except Exception as e:
                logger.error(f"Error checking subprocess alive status in heartbeat thread: {e}", exc_info=True)
            try:
                tasks_store.update_task_heartbeat(task.id, runner_id=runner_id)
                # Touch Redis queue visibility timeout to prevent ghosting by Reaper
                if redis_queue:
                    asyncio.run(redis_queue.touch_visibility_timeout(task.id, added_time_sec=180))
            except Exception as e:
                logger.error(f"Error updating heartbeat in heartbeat thread for task {task.id}: {e}", exc_info=True)
            stop_event.wait(interval_s)

    hb_thread = threading.Thread(target=_heartbeat_thread, daemon=True)
    hb_thread.start()

    lock_renew_thread = None
    if redis_queue and lock_key:

        def _renew_thread() -> None:
            interval_s = max(5.0, hb_interval_ms / 1000.0)
            while not stop_event.is_set():
                try:
                    asyncio.run(
                        redis_queue.renew_lock(
                            lock_key=lock_key,
                            owner_id=runner_id,
                            ttl_seconds=lock_ttl_seconds,
                        )
                    )
                except Exception:
                    pass
                stop_event.wait(interval_s)

        lock_renew_thread = threading.Thread(target=_renew_thread, daemon=True)
        lock_renew_thread.start()

    proc = None
    result_file = None
    try:
        cancel_poll_ms = _env_int("LOCAL_CORE_RUNNER_CANCEL_POLL_INTERVAL_MS", 2000)
        # Dynamic timeout: playbook-declared > env var > default 3600s
        ctx_timeout = ctx.get("runner_timeout_seconds")
        if isinstance(ctx_timeout, (int, float)) and ctx_timeout > 0:
            max_ceiling = _env_int("LOCAL_CORE_RUNNER_MAX_TIMEOUT_SECONDS", 43200)
            task_timeout_seconds = min(int(ctx_timeout), max_ceiling)
            logger.info(
                f"Runner using spec-declared timeout={task_timeout_seconds}s "
                f"for task {task.id} (ceiling={max_ceiling}s)"
            )
        else:
            task_timeout_seconds = _env_int(
                "LOCAL_CORE_RUNNER_TASK_TIMEOUT_SECONDS", 3600
            )
        ctx_mp = mp.get_context("spawn")

        async def _wait_for_cancel() -> bool:
            while True:
                try:
                    latest = tasks_store.get_task(task.id)
                    if latest and latest.status == TaskStatus.CANCELLED_BY_USER:
                        return True
                except Exception:
                    pass
                await asyncio.sleep(cancel_poll_ms / 1000)

        import tempfile

        result_fd, result_file = tempfile.mkstemp(
            prefix=f"runner_result_{task.id}_", suffix=".json"
        )
        os.close(result_fd)

        payload = {
            "playbook_code": task.pack_id,
            "task_type": task.task_type or "playbook_execution",
            "tool_name": (ctx.get("tool_name") if isinstance(ctx, dict) else None),
            "profile_id": (
                getattr(task, "profile_id", None)
                or (ctx.get("profile_id") if isinstance(ctx, dict) else None)
                or "default-user"
            ),
            "inputs": inputs,
            "workspace_id": task.workspace_id,
            "project_id": task.project_id,
            "_result_file": result_file,
        }

        proc = ctx_mp.Process(
            target=_child_execute_playbook, args=(payload,), daemon=True
        )
        proc.start()
        # Update proc reference for heartbeat thread to monitor
        proc_ref[0] = proc

        async def _wait_for_proc() -> int:
            while proc.is_alive():
                await asyncio.sleep(0.5)
            # Treat None exitcode as error (-1) to catch zombie/abnormal termination
            exitcode = proc.exitcode
            if exitcode is None:
                logger.warning(
                    f"Runner subprocess exitcode is None (zombie?) for task {task.id}"
                )
                return -1
            return int(exitcode)

        async def _wait_for_timeout() -> bool:
            # Returns True if timeout fired.
            await asyncio.sleep(task_timeout_seconds)
            return True

        exec_task = asyncio.create_task(_wait_for_proc())
        cancel_task = asyncio.create_task(_wait_for_cancel())
        timeout_task = asyncio.create_task(_wait_for_timeout())

        done, pending = await asyncio.wait(
            {exec_task, cancel_task, timeout_task}, return_when=asyncio.FIRST_COMPLETED
        )

        if cancel_task in done and cancel_task.result() is True:
            # --- Cancelled by user ---
            try:
                if proc.is_alive():
                    proc.terminate()
            except Exception:
                pass
            exec_task.cancel()
            timeout_task.cancel()
            try:
                await exec_task
            except BaseException:
                pass
            try:
                await timeout_task
            except BaseException:
                pass
            try:
                latest = tasks_store.get_task(task.id)
                if latest and latest.status == TaskStatus.CANCELLED_BY_USER:
                    ctxc = (
                        latest.execution_context
                        if isinstance(latest.execution_context, dict)
                        else {}
                    )
                    ctxc = dict(ctxc)
                    ctxc["status"] = "cancelled"
                    ctxc["cancelled_at"] = _utc_now().isoformat()
                    ctxc["runner_id"] = runner_id
                    tasks_store.update_task(
                        latest.id,
                        execution_context=ctxc,
                        status=TaskStatus.CANCELLED_BY_USER,
                        completed_at=_utc_now(),
                        error=latest.error or "Cancelled by user",
                    )
            except Exception:
                pass
        elif timeout_task in done and timeout_task.result() is True:
            # --- Hard timeout ---
            try:
                if proc.is_alive():
                    proc.terminate()
            except Exception:
                pass
            exec_task.cancel()
            cancel_task.cancel()
            try:
                await exec_task
            except BaseException:
                pass
            try:
                await cancel_task
            except BaseException:
                pass
            msg = (
                f"Runner task timeout ({task_timeout_seconds}s) - subprocess terminated"
            )
            _mark_task_failed(tasks_store, task.id, runner_id, msg, redis_queue)
        else:
            # --- Process finished ---
            cancel_task.cancel()
            timeout_task.cancel()
            try:
                await cancel_task
            except BaseException:
                pass
            try:
                await timeout_task
            except BaseException:
                pass
            exitcode = await exec_task
            if exitcode != 0:
                msg = f"Runner subprocess exited non-zero (exitcode={exitcode})"
                _mark_task_failed(tasks_store, task.id, runner_id, msg, redis_queue)
            else:
                _mark_task_succeeded(tasks_store, task.id, runner_id, result_file, redis_queue)
    finally:
        # Clean up result temp file regardless of outcome
        try:
            if result_file and os.path.exists(result_file):
                os.unlink(result_file)
        except Exception:
            pass
        stop_event.set()
        # Explicitly join subprocess to prevent zombie accumulation
        try:
            if proc:
                proc.join(timeout=5.0)
                if proc.is_alive():
                    logger.warning(
                        f"Runner subprocess still alive after join, killing task {task.id}"
                    )
                    proc.kill()
                    proc.join(timeout=1.0)
                    # Mark killed task as FAILED to prevent reaper re-queue loop
                    _mark_task_failed(
                        tasks_store, task.id, runner_id,
                        f"Runner subprocess killed after join timeout (pid={proc.pid})",
                        redis_queue
                    )
        except Exception as e:
            logger.warning(f"Runner subprocess cleanup error for task {task.id}: {e}")
        try:
            hb_thread.join(timeout=1.0)
        except Exception:
            pass
        if lock_renew_thread:
            try:
                lock_renew_thread.join(timeout=1.0)
            except Exception:
                pass
        # Release lock
        ctx = task.execution_context if isinstance(task.execution_context, dict) else {}
        lock_key = _resolve_lock_key(ctx, task.pack_id)
        if redis_queue and lock_key:
            try:
                await redis_queue.release_lock(lock_key=lock_key, owner_id=runner_id)
            except Exception:
                pass
