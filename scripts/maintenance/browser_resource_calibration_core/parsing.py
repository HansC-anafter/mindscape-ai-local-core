"""Pure parsers and calibration summary formulas."""

from __future__ import annotations

import json
import math
import re
from typing import Any

from scripts.maintenance.browser_resource_capacity_preflight_core.collectors import (
    parse_meminfo,
    parse_memory_events,
)


MIB = 1024 * 1024
ROUNDING_BYTES = 64 * MIB
_SIZE_RE = re.compile(r"^([0-9]+(?:\.[0-9]+)?)\s*([A-Za-z]+)$")
_SIZE_FACTORS = {
    "B": 1,
    "KB": 1000,
    "MB": 1000**2,
    "GB": 1000**3,
    "KIB": 1024,
    "MIB": 1024**2,
    "GIB": 1024**3,
}


def parse_size_bytes(raw: str) -> int:
    match = _SIZE_RE.fullmatch(str(raw or "").strip())
    if not match:
        raise ValueError(f"unsupported size: {raw}")
    factor = _SIZE_FACTORS.get(match.group(2).upper())
    if factor is None:
        raise ValueError(f"unsupported size unit: {raw}")
    return int(float(match.group(1)) * factor)


def parse_docker_stats(raw: str) -> dict[str, int]:
    working_sets: dict[str, int] = {}
    for line in raw.splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        name = str(row.get("Name") or "").strip()
        usage = str(row.get("MemUsage") or "").partition("/")[0].strip()
        if not name or not usage:
            raise ValueError("docker stats requires Name and MemUsage")
        working_sets[name] = parse_size_bytes(usage)
    if not working_sets:
        raise ValueError("docker stats returned no containers")
    return working_sets


def build_node_sample(
    *,
    captured_at_epoch: float,
    meminfo_raw: str,
    docker_stats_raw: str,
    browser_containers: tuple[str, ...],
    cgroup_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    memory = parse_meminfo(meminfo_raw)
    working_sets = parse_docker_stats(docker_stats_raw)
    all_containers = sum(working_sets.values())
    browser_total = sum(working_sets.get(name, 0) for name in browser_containers)
    non_browser = max(0, all_containers - browser_total)
    vm_used = max(0, memory["total_bytes"] - memory["available_bytes"])
    return {
        "captured_at_epoch": float(captured_at_epoch),
        "mem_total_bytes": memory["total_bytes"],
        "mem_available_bytes": memory["available_bytes"],
        "vm_used_bytes": vm_used,
        "all_container_working_set_bytes": all_containers,
        "browser_container_working_set_bytes": browser_total,
        "non_browser_container_working_set_bytes": non_browser,
        "vm_overhead_bytes": max(0, vm_used - all_containers),
        "container_working_set_bytes": working_sets,
        "browser_cgroups": cgroup_rows,
    }


def summarize_baseline(
    samples: list[dict[str, Any]],
    *,
    duration_seconds: int,
) -> dict[str, Any]:
    if not samples:
        raise ValueError("baseline requires samples")
    return {
        "status": "pass",
        "duration_seconds": int(duration_seconds),
        "sample_count": len(samples),
        "vm_overhead_peak_bytes": max(
            int(row["vm_overhead_bytes"]) for row in samples
        ),
        "non_browser_peak_bytes": max(
            int(row["non_browser_container_working_set_bytes"])
            for row in samples
        ),
        "browser_idle_peak_bytes": max(
            int(row["browser_container_working_set_bytes"]) for row in samples
        ),
        "mem_available_min_bytes": min(
            int(row["mem_available_bytes"]) for row in samples
        ),
    }


def round_request_bytes(value: int) -> int:
    if value <= 0:
        raise ValueError("request peak must be positive")
    return int(math.ceil(value / ROUNDING_BYTES) * ROUNDING_BYTES)


def summarize_workload_runs(
    runs: list[dict[str, Any]],
    *,
    expected_repetitions: int = 3,
) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for run in runs:
        grouped.setdefault(str(run.get("envelope_id") or ""), []).append(run)
    workloads: list[dict[str, Any]] = []
    failures: list[str] = []
    for envelope_id in sorted(grouped):
        rows = grouped[envelope_id]
        valid = [row for row in rows if row.get("valid") is True]
        if len(valid) != expected_repetitions:
            failures.append(f"{envelope_id}:valid_runs={len(valid)}")
            continue
        payload_hashes = {str(row.get("payload_sha256") or "") for row in valid}
        if len(payload_hashes) != 1 or "" in payload_hashes:
            failures.append(f"{envelope_id}:payload_hash_drift")
            continue
        peak = max(int(row.get("task_peak_bytes") or 0) for row in valid)
        workloads.append(
            {
                "envelope_id": envelope_id,
                "workload_code": str(valid[0].get("workload_code") or ""),
                "valid_run_count": len(valid),
                "observed_peak_bytes": peak,
                "request_bytes": round_request_bytes(peak),
                "payload_sha256": next(iter(payload_hashes)),
            }
        )
    return {
        "status": "pass" if not failures else "blocked",
        "failures": failures,
        "workloads": workloads,
    }


__all__ = [
    "build_node_sample",
    "parse_docker_stats",
    "parse_memory_events",
    "parse_size_bytes",
    "round_request_bytes",
    "summarize_baseline",
    "summarize_workload_runs",
]
