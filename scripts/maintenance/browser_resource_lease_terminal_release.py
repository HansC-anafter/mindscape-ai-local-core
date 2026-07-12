#!/usr/bin/env python3
"""Release one exact terminal-task browser resource lease fail-closed."""

from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any, Mapping

from backend.app.services.runner_resources import RedisResourceLeaseStore
from backend.app.services.runner_resources.leases import (
    resource_lease_keys_from_context,
)
from backend.app.services.stores.redis.runner_queue_store import RedisRunnerQueueStore
from backend.app.services.stores.tasks_store import TasksStore
from scripts.maintenance.browser_node_budget_terminal_release import (
    TERMINAL_STATUSES,
    _status_text,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--expected-owner", required=True)
    parser.add_argument("--expected-lease-key", required=True)
    parser.add_argument("--apply", action="store_true")
    return parser


def validate_terminal_lease_release_identity(
    *,
    task: Any,
    task_id: str,
    expected_owner: str,
    expected_lease_key: str,
    live_lease_owner: str | None,
    task_live_ttl: int,
    runner_task_live_ttl: int,
) -> None:
    if str(getattr(task, "id", "") or "") != task_id:
        raise RuntimeError("task_identity_mismatch")
    if _status_text(task) not in TERMINAL_STATUSES:
        raise RuntimeError("task_not_terminal")
    context = getattr(task, "execution_context", None)
    lease_keys = resource_lease_keys_from_context(
        context if isinstance(context, Mapping) else None
    )
    if expected_lease_key not in lease_keys:
        raise RuntimeError("task_lease_key_mismatch")
    if str(live_lease_owner or "") != expected_owner:
        raise RuntimeError("live_lease_owner_mismatch")
    if int(task_live_ttl) != -2 or int(runner_task_live_ttl) != -2:
        raise RuntimeError("live_owner_still_present")


async def _run(args: argparse.Namespace) -> int:
    task = await asyncio.to_thread(TasksStore().get_task, args.task_id)
    if task is None:
        raise RuntimeError("task_not_found")
    queue = RedisRunnerQueueStore(
        pack_id=str(getattr(task, "queue_shard", "") or "default_local_browser")
    )
    client = await queue._get_client()
    if client is None:
        raise RuntimeError("redis_unavailable")
    runner_id = args.expected_owner.split(":", 1)[0]
    task_live_key = f"mindscape:runner_live:task:{args.task_id}"
    runner_task_live_key = (
        f"mindscape:runner_live:runner:{runner_id}:task:{args.task_id}"
    )
    live_owner, lease_ttl, task_live_ttl, runner_task_live_ttl = await asyncio.gather(
        client.get(args.expected_lease_key),
        client.ttl(args.expected_lease_key),
        client.ttl(task_live_key),
        client.ttl(runner_task_live_key),
    )
    if isinstance(live_owner, bytes):
        live_owner = live_owner.decode("utf-8", errors="strict")
    validate_terminal_lease_release_identity(
        task=task,
        task_id=args.task_id,
        expected_owner=args.expected_owner,
        expected_lease_key=args.expected_lease_key,
        live_lease_owner=live_owner,
        task_live_ttl=task_live_ttl,
        runner_task_live_ttl=runner_task_live_ttl,
    )
    result: dict[str, Any] = {
        "status": "read_only_pass",
        "apply_requested": bool(args.apply),
        "task_id": args.task_id,
        "task_status": _status_text(task),
        "task_live_ttl": task_live_ttl,
        "runner_task_live_ttl": runner_task_live_ttl,
        "lease_key": args.expected_lease_key,
        "lease_owner": live_owner,
        "lease_ttl": lease_ttl,
    }
    if args.apply:
        released = await RedisResourceLeaseStore(queue).release(
            args.expected_lease_key,
            args.expected_owner,
        )
        if not released:
            raise RuntimeError("terminal_resource_lease_release_rejected")
        owner_after, ttl_after = await asyncio.gather(
            client.get(args.expected_lease_key),
            client.ttl(args.expected_lease_key),
        )
        if owner_after is not None or int(ttl_after) != -2:
            raise RuntimeError("terminal_resource_lease_release_readback_failed")
        result.update(status="applied", lease_owner_after=None, lease_ttl_after=-2)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def main() -> int:
    return asyncio.run(_run(_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
