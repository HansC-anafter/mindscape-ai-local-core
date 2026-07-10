#!/usr/bin/env python3
"""Thin operator facade for evidence-bound browser reservation reconciliation."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from backend.app.services.runner_resources import (
    NODE_BUDGET_CONTEXT_KEY,
    RedisNodeBudgetStore,
    reservation_from_context,
)
from backend.app.services.stores.redis.runner_queue_store import RedisRunnerQueueStore
from scripts.maintenance.browser_node_budget_reconcile_core import (
    validate_reconciliation_evidence,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-jsonl", type=Path, required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--runner-container", required=True)
    parser.add_argument("--expected-owner", required=True)
    parser.add_argument("--expected-revision", type=int, required=True)
    parser.add_argument("--apply", action="store_true")
    return parser


def _find_reservation(snapshot: dict[str, Any], owner: str) -> dict[str, Any]:
    matches = [
        item
        for item in snapshot.get("reservations") or []
        if str(item.get("owner_id") or "") == owner
    ]
    if len(matches) != 1:
        raise RuntimeError("live_reservation_identity_not_unique")
    return matches[0]


async def _run(args: argparse.Namespace) -> int:
    evidence = validate_reconciliation_evidence(
        args.evidence_jsonl,
        task_id=args.task_id,
        runner_container=args.runner_container,
    )
    expected_owner = f"{evidence.runner_id}:{evidence.task_id}"
    if args.expected_owner != expected_owner:
        raise RuntimeError("expected_owner_does_not_match_evidence")
    store = RedisNodeBudgetStore(
        RedisRunnerQueueStore(pack_id="default_local_browser")
    )
    before = await store.snapshot()
    if before.get("available") is not True:
        raise RuntimeError("node_budget_snapshot_unavailable")
    raw_reservation = _find_reservation(before, args.expected_owner)
    reservation = reservation_from_context(
        {NODE_BUDGET_CONTEXT_KEY: raw_reservation}
    )
    if reservation is None:
        raise RuntimeError("live_reservation_invalid")
    if reservation.revision != args.expected_revision:
        raise RuntimeError("live_reservation_revision_mismatch")
    if evidence.request_bytes >= reservation.bytes:
        raise RuntimeError("derived_request_is_not_downward")

    result: dict[str, Any] = {
        "status": "read_only_pass",
        "apply_requested": bool(args.apply),
        "evidence": evidence.to_dict(),
        "reservation_before": raw_reservation,
        "reserved_bytes_before": before.get("reserved_bytes"),
    }
    if args.apply:
        applied = await store.reconcile_down(
            reservation,
            request_bytes=evidence.request_bytes,
            evidence_fingerprint=evidence.evidence_fingerprint,
        )
        if not applied:
            raise RuntimeError("reservation_reconciliation_rejected")
        after = await store.snapshot()
        raw_after = _find_reservation(after, args.expected_owner)
        if (
            int(raw_after.get("revision") or 0) != args.expected_revision
            or int(raw_after.get("bytes") or 0) != evidence.request_bytes
            or raw_after.get("reconciliation_evidence_fingerprint")
            != evidence.evidence_fingerprint
        ):
            raise RuntimeError("reservation_reconciliation_readback_mismatch")
        result.update(
            status="applied",
            reservation_after=raw_after,
            reserved_bytes_after=after.get("reserved_bytes"),
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def main() -> int:
    return asyncio.run(_run(_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
