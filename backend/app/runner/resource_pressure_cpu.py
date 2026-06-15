"""CPU cgroup sampling helpers for runner resource pressure."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

_CPU_SAMPLES_BY_ROOT: dict[str, dict[str, Any]] = {}


def _read_text(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception:
        return None


def _read_int(path: Path) -> Optional[int]:
    raw = _read_text(path)
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _parse_limit(raw: Optional[str]) -> Optional[int]:
    if raw is None:
        return None
    raw = str(raw).strip().lower()
    if not raw or raw == "max":
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    if value <= 0 or value >= 2**60:
        return None
    return value


def _parse_cpu_max(raw: Optional[str]) -> tuple[Optional[int], Optional[int]]:
    if raw is None:
        return None, None
    parts = raw.split()
    if len(parts) < 2:
        return None, None
    quota = _parse_limit(parts[0])
    try:
        period = int(parts[1])
    except (TypeError, ValueError):
        period = None
    return quota, period if period and period > 0 else None


def _read_key_value_stat(path: Path) -> dict[str, int]:
    raw = _read_text(path)
    stats: dict[str, int] = {}
    if not raw:
        return stats
    for line in raw.splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        try:
            stats[parts[0]] = int(parts[1])
        except (TypeError, ValueError):
            continue
    return stats


def _quota_cores(quota_usec: Optional[int], period_usec: Optional[int]) -> Optional[float]:
    if quota_usec is None or period_usec is None or period_usec <= 0:
        try:
            cpu_count = os.cpu_count()
        except Exception:
            cpu_count = None
        return float(cpu_count) if cpu_count and cpu_count > 0 else None
    return max(float(quota_usec) / float(period_usec), 0.01)


def read_cpu_counters(cgroup_root: str | Path = "/sys/fs/cgroup") -> dict[str, Any]:
    root = Path(cgroup_root)

    cpu_stat = _read_key_value_stat(root / "cpu.stat")
    usage_usec = cpu_stat.get("usage_usec")
    quota_usec, period_usec = _parse_cpu_max(_read_text(root / "cpu.max"))

    if usage_usec is None:
        usage_nsec = _read_int(root / "cpuacct" / "cpuacct.usage")
        if usage_nsec is not None:
            usage_usec = int(usage_nsec / 1000)
    if quota_usec is None:
        quota_usec = _parse_limit(_read_text(root / "cpu" / "cpu.cfs_quota_us"))
    if period_usec is None:
        period_usec = _parse_limit(_read_text(root / "cpu" / "cpu.cfs_period_us"))
    if not cpu_stat:
        cpu_stat = _read_key_value_stat(root / "cpu" / "cpu.stat")

    return {
        "usage_usec": usage_usec,
        "quota_usec": quota_usec,
        "period_usec": period_usec,
        "quota_cores": _quota_cores(quota_usec, period_usec),
        "nr_periods": cpu_stat.get("nr_periods"),
        "nr_throttled": cpu_stat.get("nr_throttled"),
        "throttled_usec": cpu_stat.get("throttled_usec"),
    }


def build_cpu_delta_snapshot(
    *,
    cgroup_root: str | Path,
    now_epoch: float,
    counters: dict[str, Any],
) -> dict[str, Any]:
    usage_usec = counters.get("usage_usec")
    quota_cores = counters.get("quota_cores")
    root_key = str(Path(cgroup_root))
    previous = _CPU_SAMPLES_BY_ROOT.get(root_key)
    _CPU_SAMPLES_BY_ROOT[root_key] = {
        "captured_at_epoch": now_epoch,
        "usage_usec": usage_usec,
        "nr_periods": counters.get("nr_periods"),
        "nr_throttled": counters.get("nr_throttled"),
    }

    usage_ratio = None
    throttled_ratio = None
    if (
        previous
        and isinstance(usage_usec, int)
        and isinstance(previous.get("usage_usec"), int)
        and isinstance(quota_cores, (int, float))
        and quota_cores > 0
    ):
        elapsed_seconds = max(0.001, now_epoch - float(previous["captured_at_epoch"]))
        usage_delta_seconds = max(
            0.0,
            float(usage_usec - previous["usage_usec"]) / 1_000_000.0,
        )
        usage_ratio = max(
            0.0,
            min(usage_delta_seconds / (elapsed_seconds * float(quota_cores)), 10.0),
        )

    nr_periods = counters.get("nr_periods")
    nr_throttled = counters.get("nr_throttled")
    if (
        previous
        and isinstance(nr_periods, int)
        and isinstance(nr_throttled, int)
        and isinstance(previous.get("nr_periods"), int)
        and isinstance(previous.get("nr_throttled"), int)
    ):
        period_delta = max(0, nr_periods - previous["nr_periods"])
        throttled_delta = max(0, nr_throttled - previous["nr_throttled"])
        if period_delta > 0:
            throttled_ratio = max(
                0.0,
                min(float(throttled_delta) / float(period_delta), 1.0),
            )

    return {
        "available": isinstance(usage_usec, int),
        "usage_usec": usage_usec,
        "quota_usec": counters.get("quota_usec"),
        "period_usec": counters.get("period_usec"),
        "quota_cores": quota_cores,
        "usage_ratio": usage_ratio,
        "nr_periods": nr_periods,
        "nr_throttled": nr_throttled,
        "throttled_usec": counters.get("throttled_usec"),
        "throttled_ratio": throttled_ratio,
    }


def reset_cpu_samples_for_tests() -> None:
    _CPU_SAMPLES_BY_ROOT.clear()
