#!/usr/bin/env python3
"""End-to-end smoke for ig_analyze_following true pause/resume.

Run this inside the local-core backend container, for example:

    docker exec -i mindscape-ai-local-core-backend \
      python /app/scripts/e2e/run_ig_true_pause_smoke.py \
      --user-data-dir /app/data/ig-browser-profiles/pause-smoke-20260401c \
      --target-username kanon420_official

The script:
1. Creates or reuses a workspace
2. Creates a runner task on an isolated queue shard
3. Runs the one-off smoke harness
4. Requests cooperative pause
5. Verifies paused-reserved DB + workspace projection state
6. Resumes the same execution
7. Verifies queued/resumed state
8. Optionally cleans the isolated queue/task artifact
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
import traceback
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def _utc_now():
    return datetime.now(timezone.utc)


def _log(message: str) -> None:
    print(f"[ig-true-pause-smoke] {message}", flush=True)


_BACKEND_SYMBOLS: Optional[dict[str, Any]] = None


def _wait_for_postgres_ready(max_attempts: int = 8) -> None:
    import psycopg2

    dsn = os.getenv("DATABASE_URL_CORE") or os.getenv("DATABASE_URL")
    if not dsn:
        return

    delay = 1.0
    last_error: Optional[Exception] = None
    for attempt in range(1, max_attempts + 1):
        try:
            conn = psycopg2.connect(dsn)
            conn.close()
            return
        except Exception as exc:  # pragma: no cover - environment dependent
            last_error = exc
            if attempt == max_attempts:
                break
            _log(
                f"PostgreSQL not ready (attempt {attempt}/{max_attempts}): {exc}. "
                f"Retrying in {int(delay)}s..."
            )
            time.sleep(delay)
            delay = min(delay * 2, 8.0)
    raise RuntimeError(
        f"PostgreSQL schema validation failed after {max_attempts} attempts: {last_error}"
    )


def _backend() -> dict[str, Any]:
    global _BACKEND_SYMBOLS
    if _BACKEND_SYMBOLS is not None:
        return _BACKEND_SYMBOLS

    _wait_for_postgres_ready()

    from backend.app.models.workspace import (
        PlaybookExecution,
        Task,
        TaskStatus,
        Workspace,
    )
    from backend.app.routes.core.execution_metadata import resolve_runner_metadata
    from backend.app.routes.core.execution_schemas import (
        PauseExecutionRequest,
        ResumeExecutionRequest,
    )
    from backend.app.routes.core.playbook_execution import (
        pause_playbook_execution,
        playbook_service,
        resume_playbook_execution,
    )
    from backend.app.runner.concurrency import _resolve_lock_keys
    from backend.app.runner.task_executor import _run_single_task
    from backend.app.services.mindscape_store import MindscapeStore
    from backend.app.services.stores.redis.runner_queue_store import (
        RedisRunnerQueueStore,
    )
    from backend.app.services.stores.tasks_store import TasksStore
    from backend.app.services.task_execution_projection import project_execution_for_api
    from backend.app.services.task_pause_contract import (
        USER_PAUSE_RESERVED_BLOCKED_REASON,
    )

    _BACKEND_SYMBOLS = {
        "PlaybookExecution": PlaybookExecution,
        "Task": Task,
        "TaskStatus": TaskStatus,
        "Workspace": Workspace,
        "PauseExecutionRequest": PauseExecutionRequest,
        "ResumeExecutionRequest": ResumeExecutionRequest,
        "resolve_runner_metadata": resolve_runner_metadata,
        "pause_playbook_execution": pause_playbook_execution,
        "playbook_service": playbook_service,
        "resume_playbook_execution": resume_playbook_execution,
        "_resolve_lock_keys": _resolve_lock_keys,
        "_run_single_task": _run_single_task,
        "MindscapeStore": MindscapeStore,
        "RedisRunnerQueueStore": RedisRunnerQueueStore,
        "TasksStore": TasksStore,
        "project_execution_for_api": project_execution_for_api,
        "USER_PAUSE_RESERVED_BLOCKED_REASON": USER_PAUSE_RESERVED_BLOCKED_REASON,
    }
    return _BACKEND_SYMBOLS


@dataclass
class SmokeContext:
    workspace_id: str
    execution_id: str
    queue_name: str
    runner_id: str
    created_workspace: bool


def _build_workspace(title: str, owner_user_id: str) -> Workspace:
    Workspace = _backend()["Workspace"]
    now = _utc_now()
    return Workspace(
        id=str(uuid.uuid4()),
        owner_user_id=owner_user_id,
        title=title,
        description="Codex true-pause smoke workspace",
        created_at=now,
        updated_at=now,
    )


async def _ensure_workspace(
    workspace_id: Optional[str],
    *,
    owner_user_id: str,
    title_prefix: str,
) -> tuple[str, bool]:
    if workspace_id:
        return workspace_id, False

    MindscapeStore = _backend()["MindscapeStore"]
    store = MindscapeStore()
    workspaces = store.workspaces
    workspace = _build_workspace(
        title=f"{title_prefix} {_utc_now().strftime('%Y-%m-%d %H:%M:%S')}",
        owner_user_id=owner_user_id,
    )
    await asyncio.to_thread(workspaces.create_workspace, workspace)
    return workspace.id, True


async def _create_smoke_execution(
    *,
    workspace_id: str,
    owner_user_id: str,
    queue_name: str,
    user_data_dir: str,
    target_username: str,
    visit_account_pages: bool,
    max_accounts: Optional[int],
) -> str:
    backend = _backend()
    PlaybookExecution = backend["PlaybookExecution"]
    Task = backend["Task"]
    TaskStatus = backend["TaskStatus"]
    resolve_runner_metadata = backend["resolve_runner_metadata"]
    playbook_service = backend["playbook_service"]
    TasksStore = backend["TasksStore"]
    MindscapeStore = backend["MindscapeStore"]
    playbook_run = await playbook_service.load_playbook_run(
        playbook_code="ig_analyze_following",
        locale="zh-TW",
        workspace_id=workspace_id,
    )
    runner_metadata = resolve_runner_metadata(playbook_run)
    execution_id = str(uuid.uuid4())
    playbook_name = (
        playbook_run.playbook.metadata.name
        if playbook_run.playbook and playbook_run.playbook.metadata
        else "ig_analyze_following"
    )
    total_steps = (
        len(playbook_run.playbook_json.steps)
        if playbook_run.playbook_json and playbook_run.playbook_json.steps
        else 1
    )

    inputs = {
        "execution_id": execution_id,
        "workspace_id": workspace_id,
        "profile_id": owner_user_id,
        "target_username": target_username,
        "visit_account_pages": visit_account_pages,
        "max_accounts": max_accounts,
        "user_data_dir": user_data_dir,
        "run_mode": "full",
        "allow_partial_resume": False,
        "execution_backend": "runner",
        "auto_execute": True,
    }

    execution_context = {
        "playbook_code": "ig_analyze_following",
        "playbook_name": playbook_name,
        "execution_id": execution_id,
        "status": "queued",
        "execution_mode": "runner",
        "execution_backend_hint": "runner",
        "inputs": inputs,
        "workspace_id": workspace_id,
        "profile_id": owner_user_id,
        "total_steps": total_steps,
        "current_step_index": 0,
        **runner_metadata,
        "queue_shard": queue_name,
        "queue_partition": queue_name,
    }

    tasks_store = TasksStore()
    store = MindscapeStore()
    executions_store = store.playbook_executions

    await asyncio.to_thread(
        tasks_store.create_task,
        Task(
            id=execution_id,
            workspace_id=workspace_id,
            message_id=str(uuid.uuid4()),
            execution_id=execution_id,
            project_id=None,
            pack_id="ig_analyze_following",
            task_type="playbook_execution",
            status=TaskStatus.PENDING,
            queue_shard=queue_name,
            execution_context=execution_context,
            created_at=_utc_now(),
            started_at=None,
        ),
    )

    if executions_store:
        await asyncio.to_thread(
            executions_store.create_execution,
            PlaybookExecution(
                id=execution_id,
                workspace_id=workspace_id,
                playbook_code="ig_analyze_following",
                thread_id=None,
                intent_instance_id=None,
                status="running",
                phase="queue",
                last_checkpoint=None,
                progress_log_path=None,
                feature_list_path=None,
                metadata={
                    "execution_mode": "runner",
                    "execution_backend_hint": "runner",
                    "playbook_name": playbook_name,
                    "resource_class": runner_metadata.get("resource_class"),
                    "queue_partition": queue_name,
                    "queue_shard": queue_name,
                    "runner_profile_hint": runner_metadata.get("runner_profile_hint"),
                    "runtime_affinity": runner_metadata.get("runtime_affinity"),
                },
                created_at=_utc_now(),
                updated_at=_utc_now(),
            ),
        )

    return execution_id


async def _wait_for_task(
    execution_id: str,
    predicate: Callable[[Any], bool],
    *,
    timeout_sec: int,
    poll_interval_sec: float = 1.0,
    label: str,
):
    TasksStore = _backend()["TasksStore"]
    tasks_store = TasksStore()
    deadline = asyncio.get_running_loop().time() + timeout_sec
    last_task = None
    while asyncio.get_running_loop().time() < deadline:
        task = await asyncio.to_thread(tasks_store.get_task_by_execution_id, execution_id)
        if not task:
            task = await asyncio.to_thread(tasks_store.get_task, execution_id)
        last_task = task
        if task and predicate(task):
            return task
        await asyncio.sleep(poll_interval_sec)
    raise TimeoutError(f"timed out waiting for {label}; last_task={last_task}")


async def _run_harness(
    execution_id: str,
    *,
    runner_id: str,
    queue_name: str,
) -> None:
    backend = _backend()
    tasks_store = backend["TasksStore"]()
    queue = backend["RedisRunnerQueueStore"](pack_id=queue_name)
    _resolve_lock_keys = backend["_resolve_lock_keys"]
    _run_single_task = backend["_run_single_task"]

    popped = await queue.dequeue_task_nowait(visibility_timeout_sec=180)
    _log(f"harness.dequeued={popped}")
    if popped != execution_id:
        raise RuntimeError(f"unexpected task dequeued: {popped!r}")

    task = await asyncio.to_thread(tasks_store.get_task, execution_id)
    if not task:
        raise RuntimeError(f"task not found: {execution_id}")

    ctx = task.execution_context if isinstance(task.execution_context, dict) else {}
    lock_keys = _resolve_lock_keys(ctx, task.pack_id)
    _log(f"harness.lock_keys={lock_keys}")
    for key in lock_keys:
        acquired = await queue.acquire_lock(key, runner_id, ttl_seconds=120)
        _log(f"harness.acquire_lock {key} -> {acquired}")
        if not acquired:
            raise RuntimeError(f"failed to acquire lock: {key}")

    claimed = await asyncio.to_thread(tasks_store.try_claim_task, execution_id, runner_id)
    _log(f"harness.claimed={claimed}")
    if not claimed:
        raise RuntimeError(f"failed to claim task: {execution_id}")

    await _run_single_task(tasks_store, runner_id, execution_id, redis_queue=queue)

    final_task = await asyncio.to_thread(tasks_store.get_task, execution_id)
    final_ctx = (
        final_task.execution_context
        if final_task and isinstance(final_task.execution_context, dict)
        else {}
    )
    _log(f"harness.final_status={getattr(final_task.status, 'value', None)}")
    _log(f"harness.final_blocked_reason={getattr(final_task, 'blocked_reason', None)}")
    _log(f"harness.final_exec_status={final_ctx.get('status')}")


async def _assert_workspace_projection(
    *,
    workspace_id: str,
    execution_id: str,
    expected_status: str,
    expected_task_status: str,
    expected_blocked_reason: Optional[str],
    expected_frontier_state: str,
    expected_status_phase: str,
) -> dict[str, Any]:
    backend = _backend()
    tasks_store = backend["TasksStore"]()
    project_execution_for_api = backend["project_execution_for_api"]
    task = await asyncio.to_thread(tasks_store.get_task_by_execution_id, execution_id)
    if not task:
        raise AssertionError(f"execution {execution_id} missing from task store")
    item = project_execution_for_api(
        task.model_dump(),
        queue_position=None,
        queue_total=1,
        watchdog_state={},
    )
    actual = {
        "status": item.get("status"),
        "task_status": item.get("task_status"),
        "blocked_reason": item.get("blocked_reason"),
        "frontier_state": item.get("frontier_state"),
        "status_phase": item.get("status_phase"),
    }
    expected = {
        "status": expected_status,
        "task_status": expected_task_status,
        "blocked_reason": expected_blocked_reason,
        "frontier_state": expected_frontier_state,
        "status_phase": expected_status_phase,
    }
    if actual != expected:
        raise AssertionError(
            f"projection mismatch for {execution_id}: actual={actual} expected={expected}"
        )
    return item


async def _cleanup_smoke_execution(ctx: SmokeContext) -> None:
    backend = _backend()
    tasks_store = backend["TasksStore"]()
    queue = backend["RedisRunnerQueueStore"](pack_id=ctx.queue_name)
    TaskStatus = backend["TaskStatus"]
    task = await asyncio.to_thread(tasks_store.get_task_by_execution_id, ctx.execution_id)
    if task and task.status == TaskStatus.PENDING:
        popped = await queue.dequeue_task_nowait(visibility_timeout_sec=30)
        if popped == ctx.execution_id:
            await queue.ack_task(ctx.execution_id)
        await asyncio.to_thread(tasks_store.cancel_task, ctx.execution_id)


def _task_debug(task: Any) -> str:
    if not task:
        return "<missing>"
    ctx = task.execution_context if isinstance(task.execution_context, dict) else {}
    return (
        f"status={getattr(task.status, 'value', task.status)} "
        f"blocked_reason={getattr(task, 'blocked_reason', None)} "
        f"frontier_state={getattr(task, 'frontier_state', None)} "
        f"exec_status={ctx.get('status')} "
        f"control_state={(ctx.get('control') or {}).get('state')} "
        f"requested_transition={(ctx.get('control') or {}).get('requested_transition')}"
    )


async def _main(args: argparse.Namespace) -> int:
    backend = _backend()
    PauseExecutionRequest = backend["PauseExecutionRequest"]
    ResumeExecutionRequest = backend["ResumeExecutionRequest"]
    pause_playbook_execution = backend["pause_playbook_execution"]
    resume_playbook_execution = backend["resume_playbook_execution"]
    USER_PAUSE_RESERVED_BLOCKED_REASON = backend["USER_PAUSE_RESERVED_BLOCKED_REASON"]

    workspace_id, created_workspace = await _ensure_workspace(
        args.workspace_id,
        owner_user_id=args.owner_user_id,
        title_prefix=args.workspace_title_prefix,
    )
    queue_name = args.queue_name or f"browser_pause_smoke_{uuid.uuid4().hex[:8]}"
    runner_id = args.runner_id or "codex-smoke"

    execution_id = await _create_smoke_execution(
        workspace_id=workspace_id,
        owner_user_id=args.owner_user_id,
        queue_name=queue_name,
        user_data_dir=args.user_data_dir,
        target_username=args.target_username,
        visit_account_pages=not args.no_visit_account_pages,
        max_accounts=args.max_accounts,
    )
    ctx = SmokeContext(
        workspace_id=workspace_id,
        execution_id=execution_id,
        queue_name=queue_name,
        runner_id=runner_id,
        created_workspace=created_workspace,
    )

    _log(f"workspace_id={workspace_id}")
    _log(f"execution_id={execution_id}")
    _log(f"queue_name={queue_name}")

    harness_task = asyncio.create_task(
        _run_harness(execution_id, runner_id=runner_id, queue_name=queue_name)
    )
    try:
        await _wait_for_task(
            execution_id,
            lambda task: getattr(task.status, "value", task.status) == "running",
            timeout_sec=args.start_timeout_sec,
            poll_interval_sec=1.0,
            label="runner claim",
        )
        _log("task entered running state")

        pause_result = await pause_playbook_execution(
            execution_id=execution_id,
            request=PauseExecutionRequest(reason=args.pause_reason),
        )
        _log(f"pause_result={pause_result}")

        paused_task = await _wait_for_task(
            execution_id,
            lambda task: (
                getattr(task.status, "value", task.status) == "pending"
                and getattr(task, "blocked_reason", None)
                == USER_PAUSE_RESERVED_BLOCKED_REASON
                and isinstance(task.execution_context, dict)
                and task.execution_context.get("status") == "paused"
            ),
            timeout_sec=args.pause_timeout_sec,
            poll_interval_sec=1.0,
            label="paused-reserved task state",
        )
        _log(f"paused_task={_task_debug(paused_task)}")

        paused_projection = await _assert_workspace_projection(
            workspace_id=workspace_id,
            execution_id=execution_id,
            expected_status="paused",
            expected_task_status="pending",
            expected_blocked_reason=USER_PAUSE_RESERVED_BLOCKED_REASON,
            expected_frontier_state="cold",
            expected_status_phase="queued",
        )
        _log(f"paused_projection={paused_projection['status']}/{paused_projection['status_phase']}")

        await harness_task
        _log("harness completed after pause")

        resume_result = await resume_playbook_execution(
            execution_id=execution_id,
            request=ResumeExecutionRequest(action="approve"),
            profile_id=args.owner_user_id,
        )
        _log(f"resume_result={resume_result}")

        resumed_task = await _wait_for_task(
            execution_id,
            lambda task: (
                getattr(task.status, "value", task.status) == "pending"
                and getattr(task, "blocked_reason", None) in (None, "")
                and getattr(task, "frontier_state", None) == "ready"
                and isinstance(task.execution_context, dict)
                and task.execution_context.get("status") == "queued"
                and ((task.execution_context.get("control") or {}).get("state") == "resumed")
            ),
            timeout_sec=args.resume_timeout_sec,
            poll_interval_sec=1.0,
            label="resumed queued state",
        )
        _log(f"resumed_task={_task_debug(resumed_task)}")

        resumed_projection = await _assert_workspace_projection(
            workspace_id=workspace_id,
            execution_id=execution_id,
            expected_status="pending",
            expected_task_status="pending",
            expected_blocked_reason=None,
            expected_frontier_state="ready",
            expected_status_phase="queued",
        )
        _log(f"resumed_projection={resumed_projection['status']}/{resumed_projection['status_phase']}")

        if not args.no_cleanup:
            await _cleanup_smoke_execution(ctx)
            _log("cleanup complete")

        _log("true pause smoke passed")
        return 0
    finally:
        if not harness_task.done():
            harness_task.cancel()
            try:
                await harness_task
            except asyncio.CancelledError:
                pass
        elif harness_task.done():
            exc = harness_task.exception()
            if exc:
                _log("harness exception:\n" + "".join(
                    traceback.format_exception(type(exc), exc, exc.__traceback__)
                ))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run ig_analyze_following true pause/resume smoke validation."
    )
    parser.add_argument("--workspace-id", default=None)
    parser.add_argument("--owner-user-id", default="default-user")
    parser.add_argument("--workspace-title-prefix", default="IG True Pause Smoke")
    parser.add_argument("--runner-id", default="codex-smoke")
    parser.add_argument("--queue-name", default=None)
    parser.add_argument("--user-data-dir", required=True)
    parser.add_argument("--target-username", required=True)
    parser.add_argument("--max-accounts", type=int, default=None)
    parser.add_argument("--no-visit-account-pages", action="store_true")
    parser.add_argument(
        "--pause-reason",
        default="codex e2e true pause smoke",
    )
    parser.add_argument("--start-timeout-sec", type=int, default=180)
    parser.add_argument("--pause-timeout-sec", type=int, default=240)
    parser.add_argument("--resume-timeout-sec", type=int, default=30)
    parser.add_argument("--no-cleanup", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    return asyncio.run(_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
