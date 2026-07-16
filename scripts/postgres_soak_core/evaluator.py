"""Pure fail-closed policy for representative runtime soak evidence."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable, Mapping


REQUIRED_WORKLOADS = frozenset(
    {
        "task_lifecycle",
        "queue_fairness",
        "progress_sse_fallback",
        "pack_install_success",
        "pack_install_fault",
        "autovacuum_checkpoint_archive",
        "replica_lag",
        "frontend_visibility",
    }
)


def evaluate_soak(
    *,
    started_at: str,
    now: str,
    samples: Iterable[Mapping[str, Any]],
    workloads: Iterable[str],
) -> dict[str, Any]:
    started = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
    finished = datetime.fromisoformat(now.replace("Z", "+00:00"))
    duration_seconds = max(0.0, (finished - started).total_seconds())
    rows = list(samples)
    failures: list[str] = []
    if duration_seconds < 72 * 3600:
        failures.append("soak_duration_below_72h")
    missing = sorted(REQUIRED_WORKLOADS - set(workloads))
    failures.extend(f"workload_missing:{name}" for name in missing)
    if not rows:
        failures.append("soak_samples_missing")
    timestamps = []
    for index, row in enumerate(rows):
        if not row.get("ok"):
            failures.append(f"sample_failed:{index}")
        captured = row.get("captured_at")
        if not captured:
            failures.append(f"sample_timestamp_missing:{index}")
            continue
        timestamps.append(datetime.fromisoformat(str(captured).replace("Z", "+00:00")))
        gate_failures = set(row.get("failures") or [])
        for failure in sorted(gate_failures):
            failures.append(f"runtime_gate:{failure}")
    for previous, current in zip(timestamps, timestamps[1:]):
        if (current - previous).total_seconds() > 65:
            failures.append("sample_gap_over_65s")
            break
    if timestamps:
        if (timestamps[0] - started).total_seconds() > 65:
            failures.append("sample_start_gap_over_65s")
        if (finished - timestamps[-1]).total_seconds() > 65:
            failures.append("sample_end_gap_over_65s")
    return {
        "ok": not failures,
        "duration_seconds": duration_seconds,
        "sample_count": len(rows),
        "workloads": sorted(set(workloads)),
        "failures": sorted(set(failures)),
    }
