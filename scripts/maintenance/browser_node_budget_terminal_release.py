#!/usr/bin/env python3
"""Release one exact terminal-task browser node reservation fail-closed."""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict
from typing import Any, Mapping

from backend.app.services.runner_resources import (
    NODE_BUDGET_CONTEXT_KEY,
    RedisNodeBudgetStore,
    reservation_from_context,
)
from backend.app.services.stores.redis.runner_queue_store import RedisRunnerQueueStore
from backend.app.services.stores.tasks_store import TasksStore


TERMINAL_STATUSES = {"succeeded", "failed", "cancelled", "cancelled_by_user"}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--expected-owner", required=True)
    parser.add_argument("--expected-revision", type=int, required=True)
    parser.add_argument("--apply", action="store_true")
    return parser


def _status_text(task: Any) -> str:
    status = getattr(task, "status", None)
    return str(getattr(status, "value", status) or "").strip().lower()


def validate_terminal_release_identity(
    *,
    task: Any,
    task_id: str,
    expected_owner: str,
    expected_revision: int,
    live_reservation: Mapping[str, Any],
    task_live_ttl: int,
    runner_task_live_ttl: int,
):
    if str(getattr(task, "id", "") or "") != task_id:
        raise RuntimeError("task_identity_mismatch")
    if _status_text(task) not in TERMINAL_STATUSES:
        raise RuntimeError("task_not_terminal")
    context = getattr(task, "execution_context", None)
    reservation = reservation_from_context(
        context if isinstance(context, Mapping) else None
    )
    if reservation is None:
        raise RuntimeError("task_reservation_missing_or_invalid")
    if reservation.owner_id != expected_owner:
        raise RuntimeError("task_reservation_owner_mismatch")
    if reservation.revision != expected_revision:
        raise RuntimeError("task_reservation_revision_mismatch")
    if str(live_reservation.get("owner_id") or "") != expected_owner:
        raise RuntimeError("live_reservation_owner_mismatch")
    if int(live_reservation.get("revision") or 0) != expected_revision:
        raise RuntimeError("live_reservation_revision_mismatch")
    if int(task_live_ttl) != -2 or int(runner_task_live_ttl) != -2:
        raise RuntimeError("live_owner_still_present")
    return reservation


def _find_live_reservation(snapshot: Mapping[str, Any], owner: str) -> dict[str, Any]:
    matches = [
        dict(item)
        for item in snapshot.get("reservations") or []
        if str(item.get("owner_id") or "") == owner
    ]
    if len(matches) != 1:
        raise RuntimeError("live_reservation_identity_not_unique")
    return matches[0]


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
    budget_store = RedisNodeBudgetStore(queue)
    before = await budget_store.snapshot()
    if before.get("available") is not True:
        raise RuntimeError("node_budget_snapshot_unavailable")
    live_reservation = _find_live_reservation(before, args.expected_owner)
    runner_id = args.expected_owner.split(":", 1)[0]
    task_live_key = f"mindscape:runner_live:task:{args.task_id}"
    runner_task_live_key = (
        f"mindscape:runner_live:runner:{runner_id}:task:{args.task_id}"
    )
    task_live_ttl, runner_task_live_ttl = await asyncio.gather(
        client.ttl(task_live_key),
        client.ttl(runner_task_live_key),
    )
    reservation = validate_terminal_release_identity(
        task=task,
        task_id=args.task_id,
        expected_owner=args.expected_owner,
        expected_revision=args.expected_revision,
        live_reservation=live_reservation,
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
        "reservation_before": live_reservation,
        "reserved_bytes_before": int(before.get("reserved_bytes") or 0),
    }
    if args.apply:
        if not await budget_store.release(reservation):
            raise RuntimeError("terminal_reservation_release_rejected")
        after = await budget_store.snapshot()
        if any(
            str(item.get("owner_id") or "") == args.expected_owner
            for item in after.get("reservations") or []
        ):
            raise RuntimeError("terminal_reservation_release_readback_failed")
        expected_after = max(
            0,
            int(before.get("reserved_bytes") or 0) - int(reservation.bytes),
        )
        if int(after.get("reserved_bytes") or 0) != expected_after:
            raise RuntimeError("terminal_reservation_reserved_bytes_mismatch")
        result.update(
            status="applied",
            released_reservation=asdict(reservation),
            reserved_bytes_after=int(after.get("reserved_bytes") or 0),
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def main() -> int:
    return asyncio.run(_run(_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
