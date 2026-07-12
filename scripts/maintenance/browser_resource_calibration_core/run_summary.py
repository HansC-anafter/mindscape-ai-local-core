"""Shared workload run summary construction for live and replay paths."""

from __future__ import annotations

from typing import Any

from .parsing import summarize_node_cadence, summarize_task_memory_series


def _oom_total(node: dict[str, Any]) -> int:
    return sum(
        int(row.get("oom_kill") or 0) + int(row.get("oom_group_kill") or 0)
        for row in node.get("browser_cgroups") or []
    )


def build_run_summary(
    *,
    workload: dict[str, Any],
    task_id: str,
    baseline: dict[str, Any],
    prelaunch_node: dict[str, Any] | None,
    node_samples: list[dict[str, Any]],
    terminal_task: dict[str, Any],
    failures: list[str],
) -> dict[str, Any]:
    collected_failures = list(failures)
    if prelaunch_node is None:
        collected_failures.append("resume_prelaunch_evidence_missing")
    elif node_samples and _oom_total(node_samples[-1]) > _oom_total(prelaunch_node):
        collected_failures.append("runner_cgroup_oom_delta")
    if str(terminal_task.get("status") or "") != "succeeded":
        collected_failures.append("task_not_succeeded")
    collected_failures.extend(str(value) for value in workload.get("failures") or [])
    try:
        memory = summarize_task_memory_series(
            node_samples,
            browser_idle_peak_bytes=int(baseline["browser_idle_peak_bytes"]),
        )
    except ValueError as exc:
        collected_failures.append(str(exc))
        memory = {
            "startup_peak_bytes": 0,
            "steady_peak_bytes": 0,
            "startup_settle_seconds": 0.0,
            "sample_count": len(node_samples),
        }
    cadence = summarize_node_cadence(node_samples)
    if cadence["status"] != "pass":
        collected_failures.append(str(cadence["failure"]))
    unique_failures = sorted(set(collected_failures))
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
            not unique_failures
            and int(memory["startup_peak_bytes"]) > 0
            and int(memory["steady_peak_bytes"]) > 0
        ),
        "failures": unique_failures,
        "terminal_task": terminal_task,
    }


__all__ = ["build_run_summary"]
