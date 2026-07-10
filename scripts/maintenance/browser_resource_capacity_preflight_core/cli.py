"""CLI composition for browser capacity acceptance."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Sequence

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
    request_source = parser.add_mutually_exclusive_group(required=True)
    request_source.add_argument(
        "--container-limit-fallback",
        action="store_true",
    )
    request_source.add_argument("--request-evidence-json", type=Path)
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
    request_bytes: int,
) -> CapacityInputs:
    policy = snapshot["node_budget"].get("policy") or {}
    tasks = snapshot["tasks"]
    return CapacityInputs(
        mode=args.mode,
        required_concurrency=int(args.required_concurrency),
        claim_gate_state=str(snapshot["claim_gate"].get("state") or "unknown"),
        allocatable_bytes=int(policy.get("allocatable_bytes") or 0),
        request_bytes=int(request_bytes),
        mem_available_bytes=int(snapshot["memory"].get("available_bytes") or 0),
        running_count=int(tasks.get("running_count") or 0),
        running_distinct_locks=int(tasks.get("running_distinct_locks") or 0),
        runnable_distinct_locks=int(tasks.get("runnable_distinct_locks") or 0),
        duplicate_running_lock_count=int(
            tasks.get("duplicate_running_lock_count") or 0
        ),
        runner_slot_capacity=int(snapshot.get("runner_slot_capacity") or 0),
        processing_count=int(
            snapshot["node_budget"].get("processing_count") or 0
        ),
        oom_kill_count=int(snapshot.get("oom_kill_count") or 0),
        oom_group_kill_count=int(snapshot.get("oom_group_kill_count") or 0),
    )


def load_request_evidence(path: Path) -> tuple[int, dict]:
    """Load repeated-run memory requests and return the conservative maximum."""

    raw = path.read_bytes()
    payload = json.loads(raw)
    workloads = payload.get("workloads") if isinstance(payload, dict) else None
    if not isinstance(workloads, list) or not workloads:
        raise ValueError("request evidence requires a non-empty workloads list")
    requests: list[int] = []
    normalized: list[dict] = []
    for item in workloads:
        if not isinstance(item, dict):
            raise ValueError("request evidence workload must be an object")
        code = str(item.get("workload_code") or "").strip()
        request_bytes = int(item.get("request_bytes") or 0)
        valid_run_count = int(item.get("valid_run_count") or 0)
        if not code or request_bytes <= 0 or valid_run_count < 3:
            raise ValueError("each workload requires code, positive bytes, and three runs")
        requests.append(request_bytes)
        normalized.append(
            {
                "workload_code": code,
                "request_bytes": request_bytes,
                "valid_run_count": valid_run_count,
            }
        )
    return max(requests), {
        "source": "calibration_summary",
        "path": str(path.resolve()),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "workloads": normalized,
    }


def resolve_request(args: argparse.Namespace, snapshot: dict) -> tuple[int, dict]:
    if args.container_limit_fallback:
        request_bytes = int(snapshot.get("browser_cgroup_limit_bytes") or 0)
        if request_bytes <= 0:
            raise ValueError("finite browser cgroup limit is required")
        return request_bytes, {
            "source": "container_limit_fallback",
            "request_bytes": request_bytes,
        }
    return load_request_evidence(args.request_evidence_json)


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
    request_bytes, request_evidence = resolve_request(args, snapshot)
    evaluation = evaluate_capacity(
        _capacity_inputs(args, snapshot, request_bytes)
    )
    output = {
        "evaluation": evaluation,
        "request_evidence": request_evidence,
        "snapshot": snapshot,
    }
    rendered = json.dumps(output, indent=2, sort_keys=True)
    if args.output_json:
        args.output_json.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if evaluation["verdict"] == "pass" else 2
