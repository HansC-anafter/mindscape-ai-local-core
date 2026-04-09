#!/usr/bin/env python3
"""One-off runner harness for pause/resume smoke testing.

Runs a single queued task through the current task_executor implementation
without starting the long-lived runner worker loop.
"""

import asyncio
import sys

from backend.app.services.stores.tasks_store import TasksStore
from backend.app.services.stores.redis.runner_queue_store import RedisRunnerQueueStore
from backend.app.runner.concurrency import _resolve_lock_keys
from backend.app.runner.task_executor import _run_single_task


async def _main(task_id: str, runner_id: str, queue_name: str) -> int:
    tasks_store = TasksStore()
    queue = RedisRunnerQueueStore(pack_id=queue_name)

    popped = await queue.dequeue_task_nowait(visibility_timeout_sec=180)
    print(f"dequeued={popped}")
    if popped != task_id:
        raise RuntimeError(f"unexpected task dequeued: {popped!r}")

    task = tasks_store.get_task(task_id)
    if not task:
        raise RuntimeError(f"task not found: {task_id}")

    ctx = task.execution_context if isinstance(task.execution_context, dict) else {}
    lock_keys = _resolve_lock_keys(ctx, task.pack_id)
    print(f"lock_keys={lock_keys}")
    for key in lock_keys:
        acquired = await queue.acquire_lock(key, runner_id, ttl_seconds=120)
        print(f"acquire_lock {key} {acquired}")
        if not acquired:
            raise RuntimeError(f"failed to acquire lock: {key}")

    claimed = tasks_store.try_claim_task(task_id, runner_id=runner_id)
    print(f"claimed={claimed}")
    if not claimed:
        raise RuntimeError(f"failed to claim task: {task_id}")

    await _run_single_task(tasks_store, runner_id, task_id, redis_queue=queue)

    final_task = tasks_store.get_task(task_id)
    final_ctx = (
        final_task.execution_context
        if final_task and isinstance(final_task.execution_context, dict)
        else {}
    )
    print(f"final_status={getattr(final_task.status, 'value', None)}")
    print(f"final_blocked_reason={getattr(final_task, 'blocked_reason', None)}")
    print(f"final_exec_status={final_ctx.get('status')}")
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        print(
            "usage: codex_pause_smoke_runner.py <task_id> [runner_id] [queue_name]",
            file=sys.stderr,
        )
        return 2
    task_id = sys.argv[1]
    runner_id = sys.argv[2] if len(sys.argv) >= 3 else "codex-smoke"
    queue_name = sys.argv[3] if len(sys.argv) >= 4 else "browser_local"
    return asyncio.run(_main(task_id, runner_id, queue_name))


if __name__ == "__main__":
    raise SystemExit(main())
