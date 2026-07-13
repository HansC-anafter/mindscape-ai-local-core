#!/usr/bin/env python3
"""Release one exact dead-runner lease from an inactive browser task."""

from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any, Mapping

from backend.app.services.runner_resources import RedisResourceLeaseStore
from backend.app.services.runner_resources.lease_keys import build_resource_lease_key
from backend.app.services.runner_resources.leases import (
    resource_lease_keys_from_context,
)
from backend.app.services.stores.redis.runner_queue_store import RedisRunnerQueueStore
from backend.app.services.stores.tasks_store import TasksStore


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--expected-owner", required=True)
    parser.add_argument("--expected-lease-key", required=True)
    parser.add_argument("--apply", action="store_true")
    return parser


def _status_text(task: Any) -> str:
    status = getattr(task, "status", None)
    return str(getattr(status, "value", status) or "").strip().lower()


INACTIVE_TASK_STATUSES = {
    "pending",
    "succeeded",
    "failed",
    "cancelled_by_user",
    "expired",
}


def _resource_keys_from_context(context: Mapping[str, Any]) -> list[str]:
    keys = resource_lease_keys_from_context(context)
    admission = context.get("resource_admission")
    if isinstance(admission, Mapping):
        for field_name in ("resource_keys", "lease_keys"):
            raw_keys = admission.get(field_name)
            if isinstance(raw_keys, list):
                keys.extend(
                    str(key).strip() for key in raw_keys if str(key).strip()
                )
        raw_key = admission.get("resource_key")
        if isinstance(raw_key, str) and raw_key.strip():
            keys.append(raw_key.strip())
    return list(dict.fromkeys(keys))


def _canonical_resource_keys_from_task(task: Any) -> list[str]:
    keys: list[str] = []
    context = (
        task.execution_context
        if isinstance(getattr(task, "execution_context", None), Mapping)
        else {}
    )
    keys.extend(_resource_keys_from_context(context))

    requirement_sources: list[Mapping[str, Any]] = []
    admission = context.get("resource_admission")
    if isinstance(admission, Mapping):
        requirements = admission.get("requirements")
        if isinstance(requirements, Mapping):
            requirement_sources.append(requirements)
    blocked_payload = getattr(task, "blocked_payload", None)
    if isinstance(blocked_payload, Mapping):
        for field_name in ("resource_keys", "lease_keys"):
            raw_keys = blocked_payload.get(field_name)
            if isinstance(raw_keys, list):
                keys.extend(str(key).strip() for key in raw_keys if str(key).strip())
        raw_key = blocked_payload.get("resource_key")
        if isinstance(raw_key, str) and raw_key.strip():
            keys.append(raw_key.strip())
        requirements = blocked_payload.get("requirements")
        if isinstance(requirements, Mapping):
            requirement_sources.append(requirements)

    for requirements in requirement_sources:
        profile_lock = requirements.get("ig_profile_lock")
        if isinstance(profile_lock, str) and profile_lock.strip():
            keys.append(
                build_resource_lease_key("ig_profile_lock", profile_lock.strip())
            )
    return list(dict.fromkeys(keys))


def validate_pending_orphan_lease_release_identity(
    *,
    task: Any,
    task_id: str,
    expected_owner: str,
    expected_lease_key: str,
    live_lease_owner: str | None,
    task_live_ttl: int,
    runner_task_live_ttl: int,
    runner_heartbeat_ttl: int,
    processing_score: Any,
) -> None:
    if str(getattr(task, "id", "") or "") != task_id:
        raise RuntimeError("task_identity_mismatch")
    if _status_text(task) not in INACTIVE_TASK_STATUSES:
        raise RuntimeError("task_not_inactive")
    status = _status_text(task)
    context = (
        task.execution_context
        if isinstance(getattr(task, "execution_context", None), Mapping)
        else {}
    )
    if str(getattr(task, "runner_id", "") or ""):
        raise RuntimeError("task_runner_owner_still_present")
    owner_runner, separator, owner_task = expected_owner.partition(":")
    if not separator or owner_task != task_id:
        raise RuntimeError("expected_owner_task_mismatch")
    context_runner = str(context.get("runner_id") or "")
    if context_runner and (
        status == "pending" or context_runner != owner_runner
    ):
        raise RuntimeError("task_runner_owner_still_present")
    lease_keys = _canonical_resource_keys_from_task(task)
    if expected_lease_key not in lease_keys:
        raise RuntimeError("task_lease_key_mismatch")
    if str(live_lease_owner or "") != expected_owner:
        raise RuntimeError("live_lease_owner_mismatch")
    if int(task_live_ttl) != -2 or int(runner_task_live_ttl) != -2:
        raise RuntimeError("live_owner_still_present")
    if int(runner_heartbeat_ttl) != -2:
        raise RuntimeError("runner_heartbeat_still_present")
    if processing_score is not None:
        raise RuntimeError("task_processing_owner_still_present")


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
    runner_heartbeat_key = f"mindscape:runner_resources:heartbeat:v1:{runner_id}"
    (
        live_owner,
        lease_ttl,
        task_live_ttl,
        runner_task_live_ttl,
        runner_heartbeat_ttl,
        processing_score,
    ) = await asyncio.gather(
        client.get(args.expected_lease_key),
        client.ttl(args.expected_lease_key),
        client.ttl(task_live_key),
        client.ttl(runner_task_live_key),
        client.ttl(runner_heartbeat_key),
        client.zscore(queue.q_processing, args.task_id),
    )
    if isinstance(live_owner, bytes):
        live_owner = live_owner.decode("utf-8", errors="strict")
    validate_pending_orphan_lease_release_identity(
        task=task,
        task_id=args.task_id,
        expected_owner=args.expected_owner,
        expected_lease_key=args.expected_lease_key,
        live_lease_owner=live_owner,
        task_live_ttl=task_live_ttl,
        runner_task_live_ttl=runner_task_live_ttl,
        runner_heartbeat_ttl=runner_heartbeat_ttl,
        processing_score=processing_score,
    )
    result: dict[str, Any] = {
        "status": "read_only_pass",
        "apply_requested": bool(args.apply),
        "task_id": args.task_id,
        "task_status": _status_text(task),
        "task_live_ttl": task_live_ttl,
        "runner_task_live_ttl": runner_task_live_ttl,
        "runner_heartbeat_ttl": runner_heartbeat_ttl,
        "processing_score": processing_score,
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
            raise RuntimeError("inactive_orphan_resource_lease_release_rejected")
        owner_after, ttl_after = await asyncio.gather(
            client.get(args.expected_lease_key),
            client.ttl(args.expected_lease_key),
        )
        if owner_after is not None or int(ttl_after) != -2:
            raise RuntimeError("inactive_orphan_resource_lease_release_readback_failed")
        result.update(status="applied", lease_owner_after=None, lease_ttl_after=-2)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def main() -> int:
    return asyncio.run(_run(_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
