"""CLI composition for controlled browser resource calibration."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any, Sequence

from .collectors import CalibrationCollector, pool_sample_failures
from .evidence import JsonlEvidenceWriter, write_immutable_json
from .http_client import LocalApiClient
from .parsing import summarize_baseline, summarize_workload_runs
from .workloads import build_run_sequence, build_start_request, load_workload_manifest


NODE_INTERVAL_SECONDS = 5
POOL_INTERVAL_SECONDS = 60
TERMINAL_STATUSES = {"succeeded", "failed", "cancelled", "cancelled_by_user", "expired"}
PRESERVED_BLOCKS = {"resource_exhausted", "unclassified_sigkill"}
DEFAULT_BROWSERS = (
    "mindscape-ai-local-core-runner-browser",
    "mindscape-ai-local-core-runner-browser-extra",
    "mindscape-ai-local-core-runner-default-local-browser",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Controlled browser calibration harness")
    subparsers = parser.add_subparsers(dest="mode", required=True)
    baseline = subparsers.add_parser("baseline")
    baseline.add_argument("--duration-seconds", type=int, required=True)
    _add_outputs(baseline)
    workload = subparsers.add_parser("workload")
    workload.add_argument("--manifest", type=Path, required=True)
    workload.add_argument("--repetitions", type=int, required=True)
    workload.add_argument("--sequential", action="store_true", required=True)
    workload.add_argument("--max-run-seconds", type=int, default=43200)
    _add_outputs(workload)
    parser.add_argument("--api-base", default="http://127.0.0.1:8200")
    parser.add_argument("--browser-container", action="append")
    return parser


def _add_outputs(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--output-jsonl", type=Path, required=True)
    parser.add_argument("--summary-json", type=Path, required=True)


def _collector(args: argparse.Namespace) -> CalibrationCollector:
    return CalibrationCollector(
        browser_containers=tuple(args.browser_container or DEFAULT_BROWSERS),
        api_base=args.api_base,
    )


def _run_baseline(args: argparse.Namespace) -> int:
    if args.duration_seconds < 1800:
        raise ValueError("formal baseline must run for at least 1800 seconds")
    collector = _collector(args)
    if collector.count_running_browser_tasks() != 0:
        raise ValueError("baseline requires zero running browser tasks")
    writer = JsonlEvidenceWriter(args.output_jsonl)
    samples: list[dict[str, Any]] = []
    failures: list[str] = []
    started = time.monotonic()
    next_pool = started
    try:
        while time.monotonic() - started < args.duration_seconds:
            node = collector.collect_node()
            samples.append(node)
            writer.append({"kind": "node", **node})
            now = time.monotonic()
            if now >= next_pool:
                pool = collector.collect_pool()
                pool_failures = pool_sample_failures(pool)
                failures.extend(pool_failures)
                writer.append({"kind": "pool", "failures": pool_failures, **pool})
                if collector.count_running_browser_tasks() != 0:
                    failures.append("browser_task_started_during_baseline")
                next_pool = now + POOL_INTERVAL_SECONDS
            time.sleep(max(0.0, NODE_INTERVAL_SECONDS - (time.monotonic() - now)))
    finally:
        writer.close()
    summary = summarize_baseline(samples, duration_seconds=args.duration_seconds)
    summary["failures"] = sorted(set(failures))
    if failures:
        summary["status"] = "blocked"
    write_immutable_json(args.summary_json, summary)
    return 0 if summary["status"] == "pass" else 2


def _run_workloads(args: argparse.Namespace) -> int:
    if not args.sequential or args.repetitions != 3:
        raise ValueError("formal workload calibration requires sequential repetitions=3")
    if args.max_run_seconds <= 0:
        raise ValueError("max run seconds must be positive")
    manifest = load_workload_manifest(args.manifest)
    baseline_path = Path(manifest["baseline_summary_path"])
    baseline_raw = baseline_path.read_bytes()
    baseline = json.loads(baseline_raw)
    if baseline.get("status") != "pass" or int(baseline.get("duration_seconds") or 0) < 1800:
        raise ValueError("workload calibration requires a passing 30-minute baseline")
    sequence = build_run_sequence(manifest, args.repetitions)
    collector = _collector(args)
    api = LocalApiClient()
    writer = JsonlEvidenceWriter(args.output_jsonl)
    run_summaries: list[dict[str, Any]] = []
    try:
        for workload in sequence:
            if collector.count_running_browser_tasks() != 0:
                raise ValueError("sequential calibration found another running browser task")
            pool = collector.collect_pool()
            preflight_failures = pool_sample_failures(pool)
            if preflight_failures:
                raise ValueError(f"pool preflight failed: {preflight_failures}")
            prelaunch_node = collector.collect_node()
            writer.append(
                {
                    "kind": "workload_prelaunch",
                    "envelope_id": workload["envelope_id"],
                    "workload_code": workload["workload_code"],
                    "repetition": workload["repetition"],
                    **prelaunch_node,
                }
            )
            url, payload = build_start_request(
                api_base=args.api_base,
                workspace_id=manifest["workspace_id"],
                profile_id=manifest["profile_id"],
                workload=workload,
            )
            launched = api.request("POST", url, payload=payload)
            task_id = str(launched.payload.get("execution_id") or "")
            if launched.status >= 300 or not task_id:
                raise ValueError("playbook start did not return an execution id")
            run_summary = _observe_run(
                collector=collector,
                writer=writer,
                workload=workload,
                task_id=task_id,
                baseline=baseline,
                prelaunch_node=prelaunch_node,
                max_run_seconds=args.max_run_seconds,
            )
            run_summaries.append(run_summary)
            if not run_summary["valid"]:
                break
    finally:
        writer.close()
    summary = summarize_workload_runs(run_summaries)
    summary["run_count"] = len(run_summaries)
    summary["baseline_summary_sha256"] = hashlib.sha256(baseline_raw).hexdigest()
    write_immutable_json(args.summary_json, summary)
    return 0 if summary["status"] == "pass" else 2


def _observe_run(
    *,
    collector: CalibrationCollector,
    writer: JsonlEvidenceWriter,
    workload: dict[str, Any],
    task_id: str,
    baseline: dict[str, Any],
    prelaunch_node: dict[str, Any],
    max_run_seconds: int,
) -> dict[str, Any]:
    started = time.monotonic()
    next_pool = started
    node_samples: list[dict[str, Any]] = []
    failures: list[str] = []
    terminal_task: dict[str, Any] = {}
    initial_oom = sum(
        int(row.get("oom_kill") or 0) + int(row.get("oom_group_kill") or 0)
        for row in prelaunch_node["browser_cgroups"]
    )
    final_oom = 0
    while time.monotonic() - started < max_run_seconds:
        node = collector.collect_node()
        node_samples.append(node)
        writer.append(
            {
                "kind": "workload_node",
                "task_id": task_id,
                "envelope_id": workload["envelope_id"],
                "workload_code": workload["workload_code"],
                "repetition": workload["repetition"],
                **node,
            }
        )
        oom_total = sum(
            int(row.get("oom_kill") or 0) + int(row.get("oom_group_kill") or 0)
            for row in node["browser_cgroups"]
        )
        final_oom = oom_total
        now = time.monotonic()
        if now >= next_pool:
            pool = collector.collect_pool()
            pool_failures = pool_sample_failures(pool)
            failures.extend(pool_failures)
            terminal_task = collector.collect_task(task_id)
            writer.append(
                {
                    "kind": "workload_pool",
                    "task_id": task_id,
                    "envelope_id": workload["envelope_id"],
                    "task": terminal_task,
                    "failures": pool_failures,
                    **pool,
                }
            )
            status = str(terminal_task.get("status") or "")
            blocked = str(terminal_task.get("blocked_reason") or "")
            if status in TERMINAL_STATUSES or blocked in PRESERVED_BLOCKS:
                break
            next_pool = now + POOL_INTERVAL_SECONDS
        time.sleep(max(0.0, NODE_INTERVAL_SECONDS - (time.monotonic() - now)))
    else:
        failures.append("run_timeout")

    if final_oom > initial_oom:
        failures.append("runner_cgroup_oom_delta")
    if str(terminal_task.get("status") or "") != "succeeded":
        failures.append("task_not_succeeded")
    browser_peak = max(
        int(row["browser_container_working_set_bytes"]) for row in node_samples
    )
    task_peak = max(0, browser_peak - int(baseline["browser_idle_peak_bytes"]))
    return {
        "envelope_id": workload["envelope_id"],
        "workload_code": workload["workload_code"],
        "repetition": workload["repetition"],
        "task_id": task_id,
        "payload_sha256": workload["payload_sha256"],
        "task_peak_bytes": task_peak,
        "valid": not failures and task_peak > 0,
        "failures": sorted(set(failures)),
        "terminal_task": terminal_task,
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.mode == "baseline":
        return _run_baseline(args)
    return _run_workloads(args)
