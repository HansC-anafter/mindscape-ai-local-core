"""CLI composition for browser capacity acceptance."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Sequence

from .candidate_plan import build_candidate_request_plan
from .collectors import RuntimeTargets, collect_runtime_snapshot
from .commands import ReadOnlyCommandRunner
from .policy import CapacityInputs, evaluate_capacity


DEFAULT_RUNNERS = (
    "mindscape-ai-local-core-runner-browser",
    "mindscape-ai-local-core-runner-browser-extra",
    "mindscape-ai-local-core-runner-default-local-browser",
)
DEFAULT_SHARDS = ("browser_local", "ig_browser", "default_local_browser")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only browser normal-service capacity preflight",
    )
    parser.add_argument("mode", choices=("pre-resume", "post-resume"))
    parser.add_argument("--required-concurrency", type=int, required=True)
    parser.add_argument(
        "--request-evidence-json",
        type=Path,
        required=True,
    )
    parser.add_argument("--output-json", type=Path)
    parser.add_argument(
        "--backend-container",
        default="mindscape-ai-local-core-backend",
    )
    parser.add_argument(
        "--postgres-container",
        default="mindscape-ai-local-core-postgres",
    )
    parser.add_argument(
        "--redis-container",
        default="mindscape-ai-local-core-redis",
    )
    parser.add_argument("--runner-container", action="append")
    parser.add_argument("--queue-shard", action="append")
    return parser


def _capacity_inputs(
    args: argparse.Namespace,
    snapshot: dict,
    request_plan: dict,
) -> CapacityInputs:
    policy = snapshot["node_budget"].get("policy") or {}
    tasks = snapshot["tasks"]
    return CapacityInputs(
        mode=args.mode,
        required_concurrency=int(args.required_concurrency),
        claim_gate_state=str(snapshot["claim_gate"].get("state") or "unknown"),
        allocatable_bytes=int(policy.get("allocatable_bytes") or 0),
        reserved_bytes=sum(
            int(item.get("bytes") or 0)
            for item in snapshot["node_budget"].get("reservations") or []
            if isinstance(item, dict)
        ),
        additional_request_bytes=tuple(
            int(value)
            for value in request_plan.get("additional_request_bytes") or []
        ),
        missing_request_workload_count=len(
            request_plan.get("selected_missing_request_envelopes") or []
        ),
        mem_available_bytes=int(snapshot["memory"].get("available_bytes") or 0),
        running_count=int(tasks.get("running_count") or 0),
        fresh_live_running_count=int(
            tasks.get("fresh_live_running_count") or 0
        ),
        stale_running_count=int(
            tasks.get("stale_running_count") or 0
        ),
        eligible_candidate_count=int(
            request_plan.get("eligible_candidate_count") or 0
        ),
        running_lock_conflict_count=int(
            request_plan.get("running_lock_conflict_count") or 0
        ),
        selected_candidate_count=int(
            request_plan.get("selected_candidate_count") or 0
        ),
        runner_slot_capacity=int(snapshot.get("runner_slot_capacity") or 0),
        processing_count=int(
            snapshot["node_budget"].get("processing_count") or 0
        ),
        oom_kill_count=int(snapshot.get("oom_kill_count") or 0),
        oom_group_kill_count=int(snapshot.get("oom_group_kill_count") or 0),
    )


def load_request_evidence(path: Path) -> tuple[dict[str, int], dict]:
    """Load repeated-run memory requests keyed by workload envelope id."""

    raw = path.read_bytes()
    payload = json.loads(raw)
    workloads = payload.get("workloads") if isinstance(payload, dict) else None
    if not isinstance(workloads, list) or not workloads:
        raise ValueError("request evidence requires a non-empty workloads list")
    requests: dict[str, int] = {}
    normalized: list[dict] = []
    for item in workloads:
        if not isinstance(item, dict):
            raise ValueError("request evidence workload must be an object")
        envelope_id = str(item.get("envelope_id") or "").strip()
        request_bytes = int(item.get("request_bytes") or 0)
        valid_run_count = int(item.get("valid_run_count") or 0)
        if not envelope_id or request_bytes <= 0 or valid_run_count < 3:
            raise ValueError(
                "each envelope requires id, positive bytes, and three runs"
            )
        if envelope_id in requests:
            raise ValueError("request evidence envelope ids must be unique")
        requests[envelope_id] = request_bytes
        normalized.append(
            {
                "envelope_id": envelope_id,
                "request_bytes": request_bytes,
                "valid_run_count": valid_run_count,
            }
        )
    return requests, {
        "source": "calibration_summary",
        "path": str(path.resolve()),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "workloads": normalized,
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    targets = RuntimeTargets(
        backend_container=args.backend_container,
        postgres_container=args.postgres_container,
        redis_container=args.redis_container,
        runner_containers=tuple(args.runner_container or DEFAULT_RUNNERS),
        queue_shards=tuple(args.queue_shard or DEFAULT_SHARDS),
    )
    snapshot = collect_runtime_snapshot(ReadOnlyCommandRunner(), targets)
    envelope_request_bytes, request_evidence = load_request_evidence(
        args.request_evidence_json
    )
    node_policy = snapshot["node_budget"].get("policy") or {}
    reserved_bytes = sum(
        int(item.get("bytes") or 0)
        for item in snapshot["node_budget"].get("reservations") or []
        if isinstance(item, dict)
    )
    available_request_bytes = min(
        max(0, int(node_policy.get("allocatable_bytes") or 0) - reserved_bytes),
        int(snapshot["memory"].get("available_bytes") or 0),
    )
    request_plan = build_candidate_request_plan(
        snapshot["tasks"],
        required_concurrency=int(args.required_concurrency),
        default_request_bytes=None,
        envelope_request_bytes=envelope_request_bytes,
        slot_capacity_by_partition=(
            snapshot.get("runner_slot_capacity_by_partition") or {}
        ),
        available_request_bytes=available_request_bytes,
    )
    evaluation = evaluate_capacity(
        _capacity_inputs(args, snapshot, request_plan)
    )
    public_snapshot = dict(snapshot)
    public_tasks = dict(snapshot.get("tasks") or {})
    public_tasks.pop("task_candidates", None)
    public_snapshot["tasks"] = public_tasks
    output = {
        "evaluation": evaluation,
        "request_evidence": request_evidence,
        "request_plan": request_plan,
        "snapshot": public_snapshot,
    }
    rendered = json.dumps(output, indent=2, sort_keys=True)
    if args.output_json:
        args.output_json.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if evaluation["verdict"] == "pass" else 2
