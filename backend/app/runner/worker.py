import asyncio
import json
import logging
import multiprocessing as mp
import os
import random
import socket
import subprocess
import sys
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _utc_now() -> datetime:
    """Return timezone-aware UTC now. Fixes Postgres timestamptz offset bug."""
    return datetime.now(timezone.utc)


from typing import Any, Dict, Optional

from sqlalchemy import text

from backend.app.models.workspace import Task, TaskStatus
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.playbook_run_executor import PlaybookRunExecutor
from backend.app.services.stores.tasks_store import TasksStore
from backend.app.services.stores.postgres.runner_locks_store import (
    PostgresRunnerLocksStore,
)

logger = logging.getLogger(__name__)


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


def _parse_utc_iso(value: Optional[str]) -> Optional[datetime]:
    if not value or not isinstance(value, str):
        return None
    s = value.strip()
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s)
        # Ensure timezone-aware: old code stored naive UTC timestamps.
        # If naive, assume UTC so reaper comparisons don't raise TypeError.
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _initialize_capability_packages_for_runner() -> None:
    try:
        from pathlib import Path

        from backend.app.capabilities.registry import get_registry, load_capabilities
        from backend.app.capabilities.tool_loader import load_all_capability_tools

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
                ctx2.pop("runner_id", None)
                ctx2.pop("heartbeat_at", None)
                ctx2["status"] = "queued"
                ctx2["runner_reaper"]["action"] = "requeue"
                ctx2["runner_reaper"]["requeued_at"] = _utc_now().isoformat()
                tasks_store.update_task(
                    t.id,
                    execution_context=ctx2,
                    status=TaskStatus.PENDING,
                    error=None,
                )
                logger.warning(f"Re-queued stale runner task task_id={t.id} ({msg})")
            else:
                # If the task is running but heartbeat is stale, mark failed.
                # Try on_fail lifecycle hook first (declared in playbook spec).
                hook_handled = _invoke_on_fail_hook(ctx2, msg, t.id)
                if hook_handled:
                    ctx2["runner_reaper"]["action"] = "lifecycle_hook_on_fail"
                    logger.warning(
                        f"Reaped + on_fail hook handled stale task task_id={t.id} ({msg})"
                    )
                else:
                    ctx2["status"] = "failed"
                    ctx2["error"] = msg
                    ctx2["failed_at"] = _utc_now().isoformat()
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


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        v = int(raw)
        return v if v > 0 else default
    except Exception:
        return default


def _invoke_on_fail_hook(
    execution_context: Dict[str, Any],
    failure_reason: str,
    task_id: str,
) -> bool:
    """Invoke the on_fail lifecycle hook if declared in execution_context.

    This is a GENERIC mechanism -- no pack-specific logic. The playbook spec
    declares which tool to call and how to map inputs. The runner just
    resolves and invokes.

    Returns True if the hook was invoked (regardless of outcome), False if
    no on_fail hook is declared.
    """
    hooks = execution_context.get("lifecycle_hooks")
    if not isinstance(hooks, dict):
        return False
    on_fail = hooks.get("on_fail")
    if not isinstance(on_fail, dict):
        return False

    tool_slot = on_fail.get("tool_slot")
    inputs_map = on_fail.get("inputs_map", {})
    if not tool_slot:
        return False

    # Resolve inputs_map templates
    ctx_inputs = execution_context.get("inputs", {})
    if not isinstance(ctx_inputs, dict):
        ctx_inputs = {}

    resolved = {}
    for param_name, template in inputs_map.items():
        if not isinstance(template, str):
            resolved[param_name] = template
            continue
        if template.startswith("{{input.") and template.endswith("}}"):
            key = template[len("{{input.") : -len("}}")].strip()
            resolved[param_name] = ctx_inputs.get(key)
        elif template.startswith("{{context.") and template.endswith("}}"):
            key = template[len("{{context.") : -len("}}")].strip()
            if key == "task_id":
                resolved[param_name] = task_id
            elif key == "error":
                resolved[param_name] = failure_reason
            else:
                resolved[param_name] = execution_context.get(key)
        else:
            resolved[param_name] = template

    # Pass full execution_context so the hook tool has all the info it needs
    resolved["execution_context"] = execution_context

    try:
        import importlib

        backend_ref = None

        # Strategy 1: capability registry lookup (tool_slot = "cap.tool")
        if ":" not in tool_slot and "." in tool_slot:
            try:
                from backend.app.capabilities.registry import get_tool_backend

                parts = tool_slot.split(".", 1)
                if len(parts) == 2:
                    backend_ref = get_tool_backend(parts[0], parts[1])
            except Exception:
                pass

        # Strategy 2: direct Python import path
        if not backend_ref and ":" in tool_slot:
            backend_ref = tool_slot

        if not backend_ref:
            logger.warning(
                f"on_fail hook: tool_slot '{tool_slot}' not found in registry"
            )
            return False

        module_path, func_name = backend_ref.rsplit(":", 1)
        mod = importlib.import_module(module_path)
        func = getattr(mod, func_name)
        result = func(**resolved)
        logger.info(
            f"on_fail hook invoked: {tool_slot} for task {task_id} " f"result={result}"
        )
        return True
    except Exception as e:
        logger.warning(f"on_fail hook failed (non-fatal): {e}")
        return False


# --- Deprecated IG-specific helpers (retained for external compatibility) ---


def _runner_id() -> str:
    val = (os.getenv("LOCAL_CORE_RUNNER_ID", "") or "").strip()
    if val:
        return val
    try:
        host = socket.gethostname()
    except Exception:
        host = "runner"
    return f"{host}-{uuid.uuid4().hex[:8]}"


async def _heartbeat_loop(
    tasks_store: TasksStore, task_id: str, runner_id: str, interval_ms: int
) -> None:
    while True:
        try:
            tasks_store.update_task_heartbeat(task_id, runner_id=runner_id)
            logger.debug(f"Heartbeat sent for task_id={task_id} runner_id={runner_id}")
        except Exception as e:
            logger.warning(f"Heartbeat loop failed for task_id={task_id}: {e}")
        await asyncio.sleep(interval_ms / 1000)


def _is_ig_playbook(playbook_code: str) -> bool:
    """DEPRECATED: Legacy IG playbook detection. Retained for lock key fallback only."""
    code = (playbook_code or "").strip().lower()
    return code.startswith("ig_") or code.startswith("ig.")


def _resolve_lock_key(
    task_ctx: Optional[Dict[str, Any]],
    pack_id: str,
) -> Optional[str]:
    """Resolve the concurrency lock key for a task.

    Priority:
      1. Explicit: execution_context.concurrency.lock_key_input → read from inputs
      2. Legacy fallback: IG playbooks auto-lock by user_data_dir

    Returns a lock_key string (e.g. "concurrency:user_data_dir:/path/to/profile"),
    or None if the task has no concurrency constraint.
    """
    if not isinstance(task_ctx, dict):
        return None

    inputs = task_ctx.get("inputs")
    if not isinstance(inputs, dict):
        inputs = {}

    # --- Explicit concurrency policy (preferred) ---
    concurrency = task_ctx.get("concurrency")
    if isinstance(concurrency, dict):
        lock_key_input = concurrency.get("lock_key_input")
        lock_scope = concurrency.get("lock_scope", "input")
        if lock_key_input and lock_scope == "input":
            val = inputs.get(lock_key_input)
            if isinstance(val, str) and val.strip():
                return f"concurrency:{lock_key_input}:{val.strip()}"
        elif lock_scope == "playbook":
            return f"concurrency:playbook:{pack_id}"
        elif lock_scope == "workspace":
            ws = task_ctx.get("workspace_id", "")
            return f"concurrency:workspace:{ws}" if ws else None

    # --- Legacy fallback: IG playbooks lock by user_data_dir ---
    if _is_ig_playbook(pack_id):
        val = inputs.get("user_data_dir")
        if isinstance(val, str) and val.strip():
            return f"ig_profile:{val.strip()}"

    return None


def _extract_user_data_dir(task_ctx: Optional[Dict[str, Any]]) -> Optional[str]:
    """DEPRECATED: Legacy helper, retained for external compatibility."""
    if not isinstance(task_ctx, dict):
        return None
    inputs = task_ctx.get("inputs")
    if not isinstance(inputs, dict):
        return None
    val = inputs.get("user_data_dir")
    if not isinstance(val, str):
        return None
    s = val.strip()
    return s or None


def _has_conflicting_ig_profile_lock(
    tasks_store: TasksStore, workspace_id: str, user_data_dir: str, self_task_id: str
) -> bool:
    """DEPRECATED: Legacy helper, retained for external compatibility."""
    if not user_data_dir:
        return False
    try:
        running = tasks_store.list_running_playbook_execution_tasks(
            workspace_id=workspace_id, limit=200
        )
    except Exception:
        return False
    for t in running:
        if not t or t.id == self_task_id:
            continue
        if not _is_ig_playbook(t.pack_id):
            continue
        ctx = t.execution_context if isinstance(t.execution_context, dict) else {}
        other_dir = _extract_user_data_dir(ctx)
        if other_dir and other_dir == user_data_dir:
            return True
    return False


def _lock_key_for_ig_profile(user_data_dir: str) -> str:
    """DEPRECATED: Legacy helper, retained for external compatibility."""
    return f"ig_profile:{user_data_dir}"


def _build_inputs(
    task_execution_id: str, task_ctx: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    ctx_inputs = None
    if isinstance(task_ctx, dict):
        ctx_inputs = task_ctx.get("inputs")
    inputs: Dict[str, Any] = dict(ctx_inputs) if isinstance(ctx_inputs, dict) else {}
    if "execution_id" not in inputs:
        inputs["execution_id"] = task_execution_id
    return inputs


# ============================================================
#  Agent dispatch task handler (Gemini CLI inference)
# ============================================================


async def _run_single_task(
    tasks_store: TasksStore, runner_id: str, task_id: str
) -> None:
    task = tasks_store.get_task(task_id)
    if not task:
        return

    if task.status == TaskStatus.CANCELLED_BY_USER:
        return

    os.environ["LOCAL_CORE_RUNNER_PROCESS"] = "1"

    ctx = task.execution_context if isinstance(task.execution_context, dict) else {}
    locks_store = None
    lock_key = _resolve_lock_key(ctx, task.pack_id)
    lock_ttl_seconds = _env_int("LOCAL_CORE_RUNNER_LOCK_TTL_SECONDS", 3600)
    if lock_key:
        try:
            store = MindscapeStore()
            locks_store = PostgresRunnerLocksStore()
            acquired = locks_store.try_acquire(
                lock_key=lock_key, owner_id=runner_id, ttl_seconds=lock_ttl_seconds
            )
            if not acquired:
                owner = None
                try:
                    owner = locks_store.get_owner(lock_key)
                except Exception:
                    pass
                logger.warning(
                    f"Runner skipped task due to concurrency lock task_id={task.id} lock_key={lock_key} owner={owner}"
                )
                try:
                    ctx2 = dict(ctx)
                    ctx2["runner_skip_reason"] = "concurrency_locked"
                    ctx2["runner_skip_lock_key"] = lock_key
                    ctx2["runner_skip_owner"] = owner
                    tasks_store.update_task(task.id, execution_context=ctx2)
                except Exception:
                    pass
                return
            # Lock acquired. Clear stale skip markers from previous attempts.
            try:
                ctx2 = dict(ctx)
                if ctx2.get("runner_skip_reason") or ctx2.get("runner_skip_owner"):
                    ctx2.pop("runner_skip_reason", None)
                    ctx2.pop("runner_skip_owner", None)
                    ctx2.pop("runner_skip_lock_key", None)
                    tasks_store.update_task(task.id, execution_context=ctx2)
            except Exception:
                pass
        except Exception as e:
            logger.warning(f"Runner lock acquire failed task_id={task.id}: {e}")
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
            except Exception:
                pass
            try:
                tasks_store.update_task_heartbeat(task.id, runner_id=runner_id)
            except Exception:
                pass
            stop_event.wait(interval_s)

    hb_thread = threading.Thread(target=_heartbeat_thread, daemon=True)
    hb_thread.start()

    lock_renew_thread = None
    if locks_store and lock_key:

        def _renew_thread() -> None:
            interval_s = max(5.0, hb_interval_ms / 1000.0)
            while not stop_event.is_set():
                try:
                    locks_store.renew(
                        lock_key=lock_key,
                        owner_id=runner_id,
                        ttl_seconds=lock_ttl_seconds,
                    )
                except Exception:
                    pass
                stop_event.wait(interval_s)

        lock_renew_thread = threading.Thread(target=_renew_thread, daemon=True)
        lock_renew_thread.start()

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
            deadline = _utc_now() + timedelta(seconds=task_timeout_seconds)
            while True:
                if _utc_now() >= deadline:
                    return True
                await asyncio.sleep(1.0)

        exec_task = asyncio.create_task(_wait_for_proc())
        cancel_task = asyncio.create_task(_wait_for_cancel())
        timeout_task = asyncio.create_task(_wait_for_timeout())

        done, pending = await asyncio.wait(
            {exec_task, cancel_task, timeout_task}, return_when=asyncio.FIRST_COMPLETED
        )
        if cancel_task in done and cancel_task.result() is True:
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
            # Hard timeout: kill hung subprocess and mark failed.
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
            try:
                latest = tasks_store.get_task(task.id)
                if latest and latest.status != TaskStatus.CANCELLED_BY_USER:
                    ctxf = (
                        latest.execution_context
                        if isinstance(latest.execution_context, dict)
                        else {}
                    )
                    ctxf = dict(ctxf)
                    ctxf["status"] = "failed"
                    ctxf["error"] = msg
                    ctxf["runner_id"] = runner_id
                    ctxf["failed_at"] = _utc_now().isoformat()
                    if not _invoke_on_fail_hook(ctxf, msg, latest.id):
                        tasks_store.update_task(
                            latest.id,
                            execution_context=ctxf,
                            status=TaskStatus.FAILED,
                            completed_at=_utc_now(),
                            error=msg,
                        )
            except Exception:
                pass
        else:
            # Process finished.
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
                try:
                    latest = tasks_store.get_task(task.id)
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
                        ctxf["status"] = "failed"
                        ctxf["error"] = msg
                        ctxf["runner_id"] = runner_id
                        ctxf["failed_at"] = _utc_now().isoformat()
                        if not _invoke_on_fail_hook(ctxf, msg, latest.id):
                            tasks_store.update_task(
                                latest.id,
                                execution_context=ctxf,
                                status=TaskStatus.FAILED,
                                completed_at=_utc_now(),
                                error=msg,
                            )
                except Exception:
                    pass
            else:
                # ── SUCCESS: mark task completed ──
                try:
                    # Read tool result from temp file IPC
                    tool_result = None
                    if result_file and os.path.exists(result_file):
                        try:
                            with open(result_file, "r") as f:
                                tool_result = json.load(f)
                        except Exception:
                            pass

                    latest = tasks_store.get_task(task.id)
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
                        tasks_store.update_task(
                            latest.id,
                            **update_kwargs,
                        )
                except Exception:
                    pass
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
        if locks_store and lock_key:
            try:
                locks_store.release(lock_key=lock_key, owner_id=runner_id)
            except Exception:
                pass


_RESTART_SENTINEL_PATH = Path("/app/data/.restart_runner")
_RESTART_DRAIN_TIMEOUT_SECONDS = 30


def _check_restart_sentinel() -> bool:
    """Check if a restart sentinel file exists and is still valid.

    Returns True if the runner should exit for restart.
    Removes the sentinel file before returning to prevent restart loops.
    """
    if not _RESTART_SENTINEL_PATH.exists():
        return False
    try:
        raw = _RESTART_SENTINEL_PATH.read_text(encoding="utf-8")
        sentinel = json.loads(raw)
        requested_at = sentinel.get("requested_at", "")
        ttl_seconds = sentinel.get("ttl_seconds", 30)
        request_id = sentinel.get("request_id", "unknown")

        # Validate TTL to prevent stale sentinels from triggering restart loops
        req_time = datetime.fromisoformat(requested_at)
        if req_time.tzinfo is None:
            req_time = req_time.replace(tzinfo=timezone.utc)
        age = (_utc_now() - req_time).total_seconds()
        if age > ttl_seconds:
            logger.warning(
                "Stale restart sentinel (age=%.1fs, ttl=%ds), removing: %s",
                age,
                ttl_seconds,
                request_id,
            )
            _RESTART_SENTINEL_PATH.unlink(missing_ok=True)
            return False

        # Valid sentinel: remove first, then signal restart
        _RESTART_SENTINEL_PATH.unlink(missing_ok=True)
        logger.info(
            "Restart sentinel detected (age=%.1fs, request_id=%s), preparing to exit",
            age,
            request_id,
        )
        return True
    except Exception as e:
        logger.warning("Failed to parse restart sentinel, removing: %s", e)
        _RESTART_SENTINEL_PATH.unlink(missing_ok=True)
        return False


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
                    lock_ttl_seconds = _env_int(
                        "LOCAL_CORE_RUNNER_LOCK_TTL_SECONDS", 3600
                    )
                    acquired = locks_store.try_acquire(
                        lock_key=lock_key,
                        owner_id=runner_id,
                        ttl_seconds=lock_ttl_seconds,
                    )
                    if not acquired:
                        owner = locks_store.get_owner(lock_key)
                        try:
                            ctx2 = dict(lock_ctx)
                            ctx2["runner_skip_reason"] = "concurrency_locked"
                            ctx2["runner_skip_lock_key"] = lock_key
                            ctx2["runner_skip_owner"] = owner
                            tasks_store.update_task(t.id, execution_context=ctx2)
                        except Exception:
                            pass
                        continue
                    try:
                        locks_store.release(lock_key=lock_key, owner_id=runner_id)
                    except Exception:
                        pass
                claimed = tasks_store.try_claim_task(t.id, runner_id=runner_id)
                if not claimed:
                    continue
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
