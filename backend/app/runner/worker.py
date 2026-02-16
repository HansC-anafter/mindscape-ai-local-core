import asyncio
import logging
import multiprocessing as mp
import os
import random
import socket
import threading
import uuid
from datetime import datetime, timedelta, timezone


def _utc_now() -> datetime:
    """Return timezone-aware UTC now. Fixes Postgres timestamptz offset bug."""
    return datetime.now(timezone.utc)


from typing import Any, Dict, Optional

from sqlalchemy import text

from backend.app.models.workspace import Task, TaskStatus
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.playbook_run_executor import PlaybookRunExecutor
from backend.app.services.stores.tasks_store import TasksStore
from backend.app.services.stores.runner_locks_store import RunnerLocksStore

logger = logging.getLogger(__name__)


def _child_execute_playbook(payload: Dict[str, Any]) -> None:
    """
    Run a single playbook execution inside a dedicated process.
    This isolates Playwright/driver hangs that may hold the GIL and would otherwise
    freeze runner heartbeats/lock renew threads.
    """
    os.environ["LOCAL_CORE_RUNNER_PROCESS"] = "1"
    try:
        _initialize_capability_packages_for_runner()
    except Exception:
        pass

    playbook_code = payload.get("playbook_code")
    profile_id = payload.get("profile_id")
    inputs = payload.get("inputs")
    workspace_id = payload.get("workspace_id")
    project_id = payload.get("project_id")

    async def _run() -> None:
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
                # If the task is running but heartbeat is stale, mark failed to avoid indefinite UI hang.
                # This also covers cases where the runner process restarted but kept the same runner_id.
                if _try_auto_resume_ig_task(tasks_store, t, ctx2, msg):
                    ctx2["runner_reaper"]["action"] = "auto_resume"
                    logger.warning(
                        f"Reaped + auto-resumed stale IG task task_id={t.id} ({msg})"
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
    tasks_store: TasksStore, locks_store: RunnerLocksStore, runner_id: str
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

    try:
        locks_store.ensure_table()
    except Exception:
        return

    try:
        with locks_store.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT lock_key, owner_id, expires_at, updated_at FROM runner_locks"
            )
            rows = cursor.fetchall()
    except Exception:
        return

    for row in rows or []:
        try:
            lock_key = row["lock_key"]
            owner_id = row["owner_id"]
            expires_at = _parse_utc_iso(row["expires_at"])
            updated_at = _parse_utc_iso(row["updated_at"])

            if not lock_key or not owner_id:
                continue
            if owner_id == runner_id:
                continue
            if owner_id in active_runner_ids:
                continue
            if updated_at and updated_at > threshold:
                continue
            if expires_at and expires_at < now:
                # Expired locks are safe to delete eagerly.
                pass

            with locks_store.transaction() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "DELETE FROM runner_locks WHERE lock_key = ?", (lock_key,)
                )
            logger.warning(
                f"Reaped stale runner lock lock_key={lock_key} owner_id={owner_id} expires_at={row['expires_at']}"
            )
        except Exception:
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


def _extract_target_username(task_ctx: Optional[Dict[str, Any]]) -> Optional[str]:
    if not isinstance(task_ctx, dict):
        return None
    inputs = task_ctx.get("inputs")
    if not isinstance(inputs, dict):
        return None
    for key in ("target_username", "seed", "handle"):
        val = inputs.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None


def _get_risk_cooldown_seconds() -> int:
    min_s = _env_int("IG_RISK_COOLDOWN_MIN_SECONDS", 3600)
    max_s = _env_int("IG_RISK_COOLDOWN_MAX_SECONDS", 21600)
    if max_s < min_s:
        max_s = min_s
    if max_s == min_s:
        return min_s
    return random.randint(min_s, max_s)


def _recent_ig_risk_signal(
    tasks_store: TasksStore, target_username: Optional[str]
) -> Optional[Dict[str, Any]]:
    if not target_username:
        return None
    try:
        with tasks_store.get_connection() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT updated_at,
                           content::jsonb->'progress'->>'error_type' AS error_type,
                           content::jsonb->'progress'->>'error_message' AS error_message,
                           content::jsonb->'progress'->>'stage' AS stage
                    FROM artifacts
                    WHERE playbook_code = 'ig_analyze_following'
                      AND content IS NOT NULL
                      AND content::jsonb->'metadata'->>'target_username' = :target
                      AND (
                        (content::jsonb->'progress'->>'error_type') IN ('rate_limited','challenge_required','login_required')
                        OR (content::jsonb->'progress'->>'stage') = 'blocked'
                        OR (content::jsonb->'progress'->>'error_message') ILIKE '%try again later%'
                        OR (content::jsonb->'progress'->>'error_message') ILIKE '%risk signal%'
                        OR (content::jsonb->'progress'->>'error_message') ILIKE '%we restrict%'
                      )
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """
                ),
                {"target": target_username},
            ).fetchone()
    except Exception as e:
        logger.debug(f"IG risk signal lookup failed: {e}")
        return None

    if not row:
        return None
    mapping = row._mapping if hasattr(row, "_mapping") else row
    updated_at = mapping.get("updated_at") if isinstance(mapping, dict) else row[0]
    if not isinstance(updated_at, datetime):
        return None
    return {
        "updated_at": updated_at,
        "error_type": (
            mapping.get("error_type") if isinstance(mapping, dict) else row[1]
        ),
        "error_message": (
            mapping.get("error_message") if isinstance(mapping, dict) else row[2]
        ),
        "stage": mapping.get("stage") if isinstance(mapping, dict) else row[3],
    }


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
    code = (playbook_code or "").strip().lower()
    return code.startswith("ig_") or code.startswith("ig.")


def _try_auto_resume_ig_task(
    tasks_store: TasksStore,
    task,
    current_ctx: Dict[str, Any],
    failure_reason: str,
) -> bool:
    """Auto-resume IG analyze_following by creating a new visit-only task.

    When an IG task fails due to timeout or runner crash, instead of just
    marking it failed, we create a follow-up task with run_mode=visit that
    picks up from the persisted list and visits only unfinished targets.

    Returns True if auto-resume was triggered, False otherwise.
    """
    if not _is_ig_playbook(getattr(task, "pack_id", "") or ""):
        return False

    retry_count = current_ctx.get("auto_resume_count", 0)
    max_retries = int(os.environ.get("IG_AUTO_RESUME_MAX_RETRIES", "3"))
    if retry_count >= max_retries:
        logger.info(
            f"Auto-resume skipped for task {task.id}: retry_count={retry_count} >= max={max_retries}"
        )
        return False

    # Risk cooldown guard: if recent IG risk signal detected, suppress auto-resume.
    target_username = _extract_target_username(current_ctx)
    cooldown_until = _parse_utc_iso(current_ctx.get("ig_risk_cooldown_until"))
    if cooldown_until and _utc_now() < cooldown_until:
        current_ctx["auto_resume_suppressed"] = True
        current_ctx["auto_resume_suppressed_reason"] = "ig_risk_cooldown_active"
        return False

    risk = _recent_ig_risk_signal(tasks_store, target_username)
    if risk:
        now_naive = datetime.utcnow()
        risk_time = risk.get("updated_at")
        if isinstance(risk_time, datetime):
            min_s = _env_int("IG_RISK_COOLDOWN_MIN_SECONDS", 3600)
            max_s = _env_int("IG_RISK_COOLDOWN_MAX_SECONDS", 21600)
            if max_s < min_s:
                max_s = min_s
            if risk_time >= (now_naive - timedelta(seconds=max_s)):
                cooldown_seconds = _get_risk_cooldown_seconds()
                cooldown_until_ts = _utc_now() + timedelta(seconds=cooldown_seconds)
                current_ctx["auto_resume_suppressed"] = True
                current_ctx["auto_resume_suppressed_reason"] = "ig_risk_signal"
                current_ctx["ig_risk_detected_at"] = risk_time.isoformat()
                current_ctx["ig_risk_error_type"] = risk.get("error_type")
                current_ctx["ig_risk_error_message"] = risk.get("error_message")
                current_ctx["ig_risk_cooldown_until"] = cooldown_until_ts.isoformat()
                logger.warning(
                    f"Auto-resume suppressed for task {task.id} due to IG risk signal "
                    f"(target={target_username}, cooldown_until={current_ctx['ig_risk_cooldown_until']})"
                )
                return False

    # Mark CURRENT task as failed with resume note
    current_ctx["auto_resumed"] = True
    resume_error = f"{failure_reason} (auto-resume #{retry_count + 1} queued)"
    tasks_store.update_task(
        task.id,
        execution_context=current_ctx,
        status=TaskStatus.FAILED,
        completed_at=_utc_now(),
        error=resume_error,
    )

    # Build params for the follow-up visit-only task
    original_params = task.params if isinstance(task.params, dict) else {}
    new_params = dict(original_params)
    new_params["run_mode"] = "visit"
    new_params["allow_partial_resume"] = True

    new_ctx = dict(current_ctx)
    new_ctx["auto_resume_count"] = retry_count + 1
    new_ctx["resumed_from_task_id"] = task.id
    new_ctx["status"] = "queued"
    new_ctx.pop("auto_resumed", None)
    new_ctx.pop("runner_id", None)
    new_ctx.pop("heartbeat_at", None)
    new_ctx.pop("failed_at", None)
    new_ctx.pop("error", None)

    # CRITICAL: _build_inputs reads from execution_context.inputs,
    # so we must inject run_mode and allow_partial_resume there.
    ctx_inputs = new_ctx.get("inputs", {})
    if not isinstance(ctx_inputs, dict):
        ctx_inputs = {}
    ctx_inputs = dict(ctx_inputs)
    ctx_inputs["run_mode"] = "visit"
    ctx_inputs["allow_partial_resume"] = True
    new_ctx["inputs"] = ctx_inputs

    # Create NEW follow-up task
    new_task = Task(
        id=str(uuid.uuid4()),
        workspace_id=task.workspace_id,
        message_id=getattr(task, "message_id", "") or "",
        execution_id=getattr(task, "execution_id", None),
        project_id=getattr(task, "project_id", None),
        pack_id=task.pack_id,
        task_type=getattr(task, "task_type", "playbook_execution"),
        status=TaskStatus.PENDING,
        params=new_params,
        execution_context=new_ctx,
        created_at=_utc_now(),
    )
    tasks_store.create_task(new_task)
    logger.info(
        f"Auto-resume #{retry_count + 1} queued for IG task {task.id} → new task {new_task.id}"
    )
    return True


def _extract_user_data_dir(task_ctx: Optional[Dict[str, Any]]) -> Optional[str]:
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
    lock_key = None
    lock_ttl_seconds = _env_int("LOCAL_CORE_RUNNER_LOCK_TTL_SECONDS", 3600)
    if _is_ig_playbook(task.pack_id):
        ud = _extract_user_data_dir(ctx)
        if ud:
            lock_key = _lock_key_for_ig_profile(ud)
            try:
                store = MindscapeStore()
                locks_store = RunnerLocksStore(db_path=store.db_path)
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
                        f"Runner skipped task due to IG profile lock task_id={task.id} owner={owner}"
                    )
                    try:
                        ctx2 = dict(ctx) if isinstance(ctx, dict) else {}
                        ctx2["runner_skip_reason"] = "ig_profile_locked"
                        ctx2["runner_skip_owner"] = owner
                        tasks_store.update_task(task.id, execution_context=ctx2)
                    except Exception:
                        pass
                    return
                # Lock acquired successfully. Clear any stale skip markers from previous runner attempts.
                try:
                    ctx2 = dict(ctx) if isinstance(ctx, dict) else {}
                    if ctx2.get("runner_skip_reason") or ctx2.get("runner_skip_owner"):
                        ctx2.pop("runner_skip_reason", None)
                        ctx2.pop("runner_skip_owner", None)
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
        task_timeout_seconds = _env_int("LOCAL_CORE_RUNNER_TASK_TIMEOUT_SECONDS", 3600)
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

        payload = {
            "playbook_code": task.pack_id,
            "profile_id": (
                getattr(task, "profile_id", None)
                or (ctx.get("profile_id") if isinstance(ctx, dict) else None)
                or "default-user"
            ),
            "inputs": inputs,
            "workspace_id": task.workspace_id,
            "project_id": task.project_id,
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
                    if not _try_auto_resume_ig_task(tasks_store, latest, ctxf, msg):
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
                        tasks_store.update_task(
                            latest.id,
                            execution_context=ctxf,
                            status=TaskStatus.FAILED,
                            completed_at=_utc_now(),
                            error=msg,
                        )
                except Exception:
                    pass
    finally:
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


async def run_forever() -> None:
    poll_interval_ms = _env_int("LOCAL_CORE_RUNNER_POLL_INTERVAL_MS", 1000)
    max_inflight = _env_int("LOCAL_CORE_RUNNER_MAX_INFLIGHT", 1)
    # Poll a bit more than inflight so we can quickly fill capacity.
    batch_limit = _env_int(
        "LOCAL_CORE_RUNNER_POLL_BATCH_LIMIT", max(1, max_inflight * 2)
    )
    runner_id = _runner_id()

    store = MindscapeStore()
    tasks_store = TasksStore(db_path=store.db_path)
    locks_store = RunnerLocksStore(db_path=store.db_path)

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
                if _is_ig_playbook(t.pack_id):
                    ctx = (
                        t.execution_context
                        if isinstance(t.execution_context, dict)
                        else {}
                    )
                    ud = _extract_user_data_dir(ctx)
                    if ud:
                        lock_key = _lock_key_for_ig_profile(ud)
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
                                ctx2 = dict(ctx) if isinstance(ctx, dict) else {}
                                ctx2["runner_skip_reason"] = "ig_profile_locked"
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
                logger.error(f"Runner task failed task_id={t.id}: {e}", exc_info=True)
                try:
                    ctx = (
                        t.execution_context
                        if isinstance(t.execution_context, dict)
                        else {}
                    )
                    ctx = dict(ctx)
                    ctx["status"] = "failed"
                    ctx["error"] = str(e)
                    ctx["runner_id"] = runner_id
                    ctx["failed_at"] = _utc_now().isoformat()
                    tasks_store.update_task(
                        t.id,
                        execution_context=ctx,
                        status=TaskStatus.FAILED,
                        completed_at=_utc_now(),
                        error=str(e),
                    )
                except Exception:
                    pass

        await asyncio.sleep(poll_interval_ms / 1000)


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    _initialize_capability_packages_for_runner()
    try:
        store = MindscapeStore()
        tasks_store = TasksStore(db_path=store.db_path)
        rid = _runner_id()
        _reap_stale_running_tasks(tasks_store, runner_id=rid)
        _reap_stale_runner_locks(
            tasks_store, RunnerLocksStore(db_path=store.db_path), runner_id=rid
        )
    except Exception:
        pass
    asyncio.run(run_forever())


if __name__ == "__main__":
    main()
