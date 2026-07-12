"""CLI composition for controlled browser resource calibration."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any, Sequence

from .collectors import (
    CalibrationCollector,
    CalibrationCommandError,
    pool_sample_failures,
)
from .evidence import JsonlEvidenceWriter, write_immutable_json
from .natural_claim_observer import wait_for_natural_claim
from .parsing import (
    summarize_baseline,
    summarize_node_cadence,
    summarize_task_memory_series,
    summarize_workload_runs,
)
from .workloads import load_workload_manifest, quota_state


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
    workload.add_argument("--max-claim-wait-seconds", type=int, default=43200)
    _add_outputs(workload)
    parser.add_argument("--api-base", default="http://127.0.0.1:8200")
    parser.add_argument("--redis-url", default="redis://127.0.0.1:6379/0")
    parser.add_argument("--browser-container", action="append")
    return parser


def _add_outputs(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--output-jsonl", type=Path, required=True)
    parser.add_argument("--summary-json", type=Path, required=True)


def _collector(args: argparse.Namespace) -> CalibrationCollector:
    return CalibrationCollector(
        browser_containers=tuple(args.browser_container or DEFAULT_BROWSERS),
        api_base=args.api_base,
        redis_url=args.redis_url,
    )


def _run_baseline(args: argparse.Namespace) -> int:
    if args.duration_seconds < 1800:
        raise ValueError("formal baseline must run for at least 1800 seconds")
    collector = _collector(args)
    if collector.count_running_browser_tasks() != 0:
        raise ValueError("baseline requires zero running browser tasks")
    initial_node = collector.collect_node()
    idle_total = int(initial_node["browser_container_working_set_bytes"])
    if any(
        int(row.get("memory_peak_bytes") or 0) > idle_total
        for row in initial_node["browser_cgroups"]
    ):
        raise ValueError("baseline requires fresh idle browser cgroups")
    writer = JsonlEvidenceWriter(args.output_jsonl)
    samples: list[dict[str, Any]] = []
    failures: list[str] = []
    started = time.monotonic()
    next_node_started_at = started
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
            next_node_started_at = max(
                next_node_started_at + NODE_INTERVAL_SECONDS,
                time.monotonic(),
            )
            time.sleep(max(0.0, next_node_started_at - time.monotonic()))
    finally:
        writer.close()
    summary = summarize_baseline(samples, duration_seconds=args.duration_seconds)
    if summary["node_cadence"]["status"] != "pass":
        failures.append(str(summary["node_cadence"]["failure"]))
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
    if args.max_claim_wait_seconds <= 0:
        raise ValueError("max claim wait seconds must be positive")
    manifest = load_workload_manifest(args.manifest)
    baseline_path = Path(manifest["baseline_summary_path"])
    baseline_raw = baseline_path.read_bytes()
    baseline = json.loads(baseline_raw)
    if baseline.get("status") != "pass" or int(baseline.get("duration_seconds") or 0) < 1800:
        raise ValueError("workload calibration requires a passing 30-minute baseline")
    collector = _collector(args)
    writer = JsonlEvidenceWriter(args.output_jsonl)
    run_summaries: list[dict[str, Any]] = []
    outer_failures: list[str] = []
    try:
        while True:
            quota = quota_state(run_summaries, manifest)
            if quota["complete"] or quota["failures"]:
                outer_failures.extend(quota["failures"])
                break
            if collector.count_running_browser_tasks() != 0:
                raise ValueError("sequential calibration found another running browser task")
            prelaunch_node = _wait_for_idle_reset(
                collector=collector,
                writer=writer,
                baseline=baseline,
                timeout_seconds=args.max_claim_wait_seconds,
            )
            pool = collector.collect_pool()
            preflight_failures = pool_sample_failures(pool)
            if preflight_failures:
                raise ValueError(f"pool preflight failed: {preflight_failures}")
            writer.append(
                {
                    "kind": "natural_claim_waiting",
                    "quota": quota,
                    **prelaunch_node,
                }
            )
            observer_started_epoch = time.time()
            print(
                json.dumps(
                    {
                        "state": "waiting_for_natural_claim",
                        "observer_started_epoch": observer_started_epoch,
                        "quota": quota,
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
            observation = wait_for_natural_claim(
                collector,
                observer_started_epoch=observer_started_epoch,
                timeout_seconds=args.max_claim_wait_seconds,
            )
            task = observation["task"]
            workload = observation["classification"]
            task_id = str(task.get("id") or "")
            repetition = 1 + sum(
                1
                for row in run_summaries
                if row.get("envelope_id") == workload.get("envelope_id")
            )
            workload = {**workload, "repetition": repetition}
            writer.append(
                {
                    "kind": "natural_claim_observed",
                    "task": task,
                    "live_owner": observation["live_owner"],
                    "classification": workload,
                }
            )
            print(
                json.dumps(
                    {
                        "state": "natural_claim_observed",
                        "task_id": task_id,
                        "runner_id": task.get("runner_id"),
                        "envelope_id": workload.get("envelope_id"),
                        "classification_failures": workload.get("failures"),
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
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
            print(
                json.dumps(
                    {
                        "state": "natural_task_terminal",
                        "task_id": task_id,
                        "runner_id": task.get("runner_id"),
                        "envelope_id": workload.get("envelope_id"),
                        "valid": run_summary["valid"],
                        "failures": run_summary["failures"],
                        "next": "restart_idle_runner_then_keep_claims_paused",
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
    finally:
        writer.close()
    summary = summarize_workload_runs(run_summaries)
    summary["failures"] = sorted(set(summary["failures"] + outer_failures))
    if summary["failures"]:
        summary["status"] = "blocked"
    summary["run_count"] = len(run_summaries)
    summary["baseline_summary_sha256"] = hashlib.sha256(baseline_raw).hexdigest()
    write_immutable_json(args.summary_json, summary)
    return 0 if summary["status"] == "pass" else 2


def _wait_for_idle_reset(
    *,
    collector: CalibrationCollector,
    writer: JsonlEvidenceWriter,
    baseline: dict[str, Any],
    timeout_seconds: int,
) -> dict[str, Any]:
    deadline = time.monotonic() + int(timeout_seconds)
    idle_total = int(baseline["browser_idle_peak_bytes"])
    while time.monotonic() < deadline:
        try:
            node = collector.collect_node(include_all_containers=False)
        except CalibrationCommandError as exc:
            message = str(exc).lower()
            is_browser_exec = (
                len(exc.argv) >= 3
                and exc.argv[:2] == ("docker", "exec")
                and exc.argv[2] in collector.browser_containers
            )
            is_known_transition = any(
                marker in message
                for marker in ("is not running", "is restarting", "no such container")
            )
            if not is_browser_exec or (exc.stderr and not is_known_transition):
                raise
            time.sleep(NODE_INTERVAL_SECONDS)
            continue
        peaks = [
            int(row.get("memory_peak_bytes") or 0)
            for row in node["browser_cgroups"]
        ]
        if peaks and all(peak <= idle_total for peak in peaks):
            writer.append({"kind": "idle_cgroup_reset_ready", **node})
            return node
        time.sleep(NODE_INTERVAL_SECONDS)
    raise ValueError("idle browser cgroup reset was not observed")


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
    next_node_started_at = started
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
        try:
            node = collector.collect_node(include_all_containers=False)
        except Exception as exc:
            failures.append("node_sample_failed")
            writer.append(
                {
                    "kind": "workload_node",
                    "task_id": task_id,
                    "envelope_id": workload["envelope_id"],
                    "workload_code": workload["workload_code"],
                    "repetition": workload["repetition"],
                    "failures": ["node_sample_failed"],
                    "error_type": type(exc).__name__,
                }
            )
        else:
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
                int(row.get("oom_kill") or 0)
                + int(row.get("oom_group_kill") or 0)
                for row in node["browser_cgroups"]
            )
            final_oom = oom_total
        now = time.monotonic()
        if now >= next_pool:
            pool: dict[str, Any] = {}
            pool_failures: list[str] = []
            pool_error_type: str | None = None
            try:
                pool = collector.collect_pool()
                pool_failures.extend(pool_sample_failures(pool))
            except Exception as exc:
                pool_failures.append("pool_sample_failed")
                pool_error_type = type(exc).__name__
            failures.extend(pool_failures)
            try:
                terminal_task = collector.collect_task(task_id)
            except Exception as exc:
                failures.append("task_sample_failed")
                terminal_task = {}
                pool_failures.append("task_sample_failed")
                if pool_error_type is None:
                    pool_error_type = type(exc).__name__
            pool_row = {
                "kind": "workload_pool",
                "task_id": task_id,
                "envelope_id": workload["envelope_id"],
                "task": terminal_task,
                "failures": sorted(set(pool_failures)),
                **pool,
            }
            if pool_error_type is not None:
                pool_row["error_type"] = pool_error_type
            writer.append(pool_row)
            status = str(terminal_task.get("status") or "")
            blocked = str(terminal_task.get("blocked_reason") or "")
            if status in TERMINAL_STATUSES or blocked in PRESERVED_BLOCKS:
                break
            next_pool = now + POOL_INTERVAL_SECONDS
        next_node_started_at = max(
            next_node_started_at + NODE_INTERVAL_SECONDS,
            time.monotonic(),
        )
        time.sleep(max(0.0, next_node_started_at - time.monotonic()))
    else:
        failures.append("run_timeout")

    if final_oom > initial_oom:
        failures.append("runner_cgroup_oom_delta")
    if str(terminal_task.get("status") or "") != "succeeded":
        failures.append("task_not_succeeded")
    failures.extend(str(value) for value in (workload.get("failures") or []))
    try:
        memory = summarize_task_memory_series(
            node_samples,
            browser_idle_peak_bytes=int(baseline["browser_idle_peak_bytes"]),
        )
    except ValueError as exc:
        failures.append(str(exc))
        memory = {
            "startup_peak_bytes": 0,
            "steady_peak_bytes": 0,
            "startup_settle_seconds": 0.0,
            "sample_count": len(node_samples),
        }
    cadence = summarize_node_cadence(node_samples)
    if cadence["status"] != "pass":
        failures.append(str(cadence["failure"]))
    return {
        "envelope_id": workload["envelope_id"],
        "workload_code": workload["workload_code"],
        "partition": workload.get("partition"),
        "repetition": workload["repetition"],
        "task_id": task_id,
        "payload_sha256": workload["payload_sha256"],
        **memory,
        "node_cadence": cadence,
        "task_peak_bytes": int(memory["startup_peak_bytes"]),
        "valid": (
            not failures
            and int(memory["startup_peak_bytes"]) > 0
            and int(memory["steady_peak_bytes"]) > 0
        ),
        "failures": sorted(set(failures)),
        "terminal_task": terminal_task,
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.mode == "baseline":
        return _run_baseline(args)
    return _run_workloads(args)
