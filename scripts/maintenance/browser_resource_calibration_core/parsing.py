"""Pure parsers and calibration summary formulas."""

from __future__ import annotations

import json
import hashlib
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
    cgroup_peaks = [
        int(cgroup.get("memory_peak_bytes") or 0)
        for sample in samples
        for cgroup in (sample.get("browser_cgroups") or [])
    ]
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
        "browser_cgroup_peak_ceiling_bytes": max(cgroup_peaks, default=0),
        "mem_available_min_bytes": min(
            int(row["mem_available_bytes"]) for row in samples
        ),
    }


def round_request_bytes(value: int) -> int:
    if value <= 0:
        raise ValueError("request peak must be positive")
    return int(math.ceil(value / ROUNDING_BYTES) * ROUNDING_BYTES)


def round_spacing_seconds(value: float) -> int:
    if value < 0:
        raise ValueError("startup spacing cannot be negative")
    return int(math.ceil(float(value) / 5.0) * 5)


def summarize_task_memory_series(
    samples: list[dict[str, Any]],
    *,
    browser_idle_peak_bytes: int,
) -> dict[str, Any]:
    if len(samples) < 2:
        raise ValueError("task memory series requires at least two samples")
    ordered = sorted(samples, key=lambda row: float(row["captured_at_epoch"]))
    increments = [
        max(
            0,
            int(row["browser_container_working_set_bytes"])
            - int(browser_idle_peak_bytes),
        )
        for row in ordered
    ]
    steady_start = len(increments) // 2
    steady_peak = max(increments[steady_start:])
    startup_peak = max(increments)
    last_above_steady = max(
        (index for index, value in enumerate(increments) if value > steady_peak),
        default=-1,
    )
    settle_index = min(last_above_steady + 1, len(ordered) - 1)
    settled_seconds = max(
        0.0,
        float(ordered[settle_index]["captured_at_epoch"])
        - float(ordered[0]["captured_at_epoch"]),
    )
    return {
        "startup_peak_bytes": startup_peak,
        "steady_peak_bytes": steady_peak,
        "startup_settle_seconds": settled_seconds,
        "sample_count": len(ordered),
        "steady_start_sample_index": steady_start,
    }


def summarize_workload_runs(
    runs: list[dict[str, Any]],
    *,
    expected_repetitions: int = 3,
    required_envelopes: set[str] | None = None,
) -> dict[str, Any]:
    from .envelope_classifier import APPROVED_ENVELOPES, CLASSIFIER_VERSION

    required_ids = set(required_envelopes or APPROVED_ENVELOPES)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for run in runs:
        grouped.setdefault(str(run.get("envelope_id") or ""), []).append(run)
    workloads: list[dict[str, Any]] = []
    failures: list[str] = []
    for envelope_id in sorted(required_ids):
        rows = grouped.get(envelope_id, [])
        valid = [row for row in rows if row.get("valid") is True]
        if len(valid) < expected_repetitions:
            failures.append(f"{envelope_id}:valid_runs={len(valid)}")
            continue
        payload_hashes = {str(row.get("payload_sha256") or "") for row in valid}
        if "" in payload_hashes:
            failures.append(f"{envelope_id}:payload_hash_missing")
            continue
        startup_peak = max(int(row.get("startup_peak_bytes") or 0) for row in valid)
        steady_peak = max(int(row.get("steady_peak_bytes") or 0) for row in valid)
        spacing_seconds = max(
            float(row.get("startup_settle_seconds") or 0) for row in valid
        )
        contract_payload = {
            "classifier_version": CLASSIFIER_VERSION,
            "envelope_id": envelope_id,
            "payload_sha256s": sorted(payload_hashes),
        }
        contract_sha256 = hashlib.sha256(
            json.dumps(contract_payload, separators=(",", ":"), sort_keys=True).encode(
                "utf-8"
            )
        ).hexdigest()
        workloads.append(
            {
                "envelope_id": envelope_id,
                "workload_code": str(valid[0].get("workload_code") or ""),
                "valid_run_count": len(valid),
                "observed_peak_bytes": startup_peak,
                "observed_startup_peak_bytes": startup_peak,
                "observed_steady_peak_bytes": steady_peak,
                "startup_request_bytes": round_request_bytes(startup_peak),
                "steady_request_bytes": round_request_bytes(steady_peak),
                "request_bytes": round_request_bytes(steady_peak),
                "startup_spacing_seconds": round_spacing_seconds(spacing_seconds),
                "payload_sha256s": sorted(payload_hashes),
                "workload_contract_sha256": contract_sha256,
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
    "round_spacing_seconds",
    "summarize_baseline",
    "summarize_task_memory_series",
    "summarize_workload_runs",
]
