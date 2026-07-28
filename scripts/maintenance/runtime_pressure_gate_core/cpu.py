"""Quota-aware, multi-sample CPU pressure evidence for runtime runners."""

from __future__ import annotations

import json
import time
from typing import Any, Callable


RunCommand = Callable[[list[str], float], dict[str, Any]]
Sleep = Callable[[float], None]

_CPU_INSPECT_FORMAT = (
    '{"name":{{json .Name}},'
    '"nano_cpus":{{json .HostConfig.NanoCpus}},'
    '"cpu_quota":{{json .HostConfig.CpuQuota}},'
    '"cpu_period":{{json .HostConfig.CpuPeriod}},'
    '"cpuset_cpus":{{json .HostConfig.CpusetCpus}}}'
)


def parse_percent(raw: str) -> float:
    value = str(raw or "").strip().removesuffix("%")
    parsed = float(value or "0")
    if parsed < 0:
        raise ValueError("docker_cpu_percent_negative")
    return parsed


def parse_cpuset_cpu_count(raw: str) -> int | None:
    value = str(raw or "").strip()
    if not value:
        return None
    cpu_ids: set[int] = set()
    for token in value.split(","):
        part = token.strip()
        if not part:
            raise ValueError("docker_cpuset_invalid")
        if "-" not in part:
            cpu_id = int(part)
            if cpu_id < 0:
                raise ValueError("docker_cpuset_invalid")
            cpu_ids.add(cpu_id)
            continue
        start_raw, end_raw = part.split("-", 1)
        start = int(start_raw)
        end = int(end_raw)
        if start < 0 or end < start:
            raise ValueError("docker_cpuset_invalid")
        cpu_ids.update(range(start, end + 1))
    if not cpu_ids:
        raise ValueError("docker_cpuset_invalid")
    return len(cpu_ids)


def _positive_float(value: Any, *, field_name: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name}_invalid") from exc
    if parsed <= 0:
        raise ValueError(f"{field_name}_invalid")
    return parsed


def _non_negative_int(value: Any, *, field_name: str) -> int:
    try:
        parsed = int(value or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name}_invalid") from exc
    if parsed < 0:
        raise ValueError(f"{field_name}_invalid")
    return parsed


def _effective_capacity_row(
    row: dict[str, Any],
    *,
    docker_ncpu: int,
) -> dict[str, Any]:
    name = str(row.get("name") or "").strip().lstrip("/")
    if not name:
        raise ValueError("docker_cpu_capacity_container_missing")
    nano_cpus = _non_negative_int(row.get("nano_cpus"), field_name="nano_cpus")
    cpu_quota = _non_negative_int(row.get("cpu_quota"), field_name="cpu_quota")
    cpu_period = _non_negative_int(row.get("cpu_period"), field_name="cpu_period")
    cpuset_cpus = str(row.get("cpuset_cpus") or "").strip()

    candidates: list[tuple[str, float]] = [("docker_ncpu", float(docker_ncpu))]
    if nano_cpus:
        candidates.append(("nano_cpus", _positive_float(nano_cpus / 1e9, field_name="nano_cpus")))
    if cpu_quota or cpu_period:
        if not cpu_quota or not cpu_period:
            raise ValueError("docker_cpu_quota_pair_invalid")
        candidates.append(
            (
                "cpu_quota",
                _positive_float(
                    float(cpu_quota) / float(cpu_period),
                    field_name="cpu_quota_cores",
                ),
            )
        )
    try:
        cpuset_cpu_count = parse_cpuset_cpu_count(cpuset_cpus)
    except (TypeError, ValueError) as exc:
        raise ValueError("docker_cpuset_invalid") from exc
    if cpuset_cpu_count is not None:
        candidates.append(("cpuset_cpus", float(cpuset_cpu_count)))

    effective_cpu_cores = min(value for _, value in candidates)
    capacity_sources = [
        source
        for source, value in candidates
        if abs(value - effective_cpu_cores) < 1e-9
    ]
    return {
        "container": name,
        "docker_ncpu": docker_ncpu,
        "nano_cpus": nano_cpus,
        "cpu_quota": cpu_quota,
        "cpu_period": cpu_period,
        "cpuset_cpus": cpuset_cpus,
        "cpuset_cpu_count": cpuset_cpu_count,
        "effective_cpu_cores": effective_cpu_cores,
        "effective_capacity_sources": capacity_sources,
        "quota_limited": effective_cpu_cores < float(docker_ncpu),
    }


def collect_runner_cpu_capacity(
    run_command: RunCommand,
    containers: list[str],
    timeout_seconds: float,
) -> dict[str, Any]:
    names = sorted(set(filter(None, (str(item).strip() for item in containers))))
    if not names:
        return {"ok": False, "error_code": "runner_cpu_containers_missing"}

    info = run_command(
        ["docker", "info", "--format", "{{json .NCPU}}"],
        timeout_seconds,
    )
    if not info.get("ok"):
        return {"ok": False, "error_code": "docker_ncpu_unavailable"}
    try:
        docker_ncpu = int(json.loads(str(info.get("stdout") or "").strip()))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {"ok": False, "error_code": "docker_ncpu_invalid"}
    if docker_ncpu <= 0:
        return {"ok": False, "error_code": "docker_ncpu_invalid"}

    inspected = run_command(
        ["docker", "inspect", "--format", _CPU_INSPECT_FORMAT, *names],
        timeout_seconds,
    )
    if not inspected.get("ok"):
        return {"ok": False, "error_code": "runner_cpu_capacity_unavailable"}
    try:
        rows = [
            _effective_capacity_row(json.loads(line), docker_ncpu=docker_ncpu)
            for line in str(inspected.get("stdout") or "").splitlines()
            if line.strip()
        ]
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        return {
            "ok": False,
            "error_code": str(exc) or "runner_cpu_capacity_invalid",
        }
    observed_names = {str(row["container"]) for row in rows}
    if observed_names != set(names):
        return {
            "ok": False,
            "error_code": "runner_cpu_capacity_incomplete",
            "expected_containers": names,
            "observed_containers": sorted(observed_names),
        }
    return {
        "ok": True,
        "docker_ncpu": docker_ncpu,
        "rows": sorted(rows, key=lambda item: str(item["container"])),
    }


def _longest_true_run(values: list[bool]) -> int:
    longest = 0
    current = 0
    for value in values:
        current = current + 1 if value else 0
        longest = max(longest, current)
    return longest


def _series_evidence(
    subject: str,
    ratios: list[float],
    *,
    threshold_ratio: float,
    required_consecutive_samples: int,
) -> dict[str, Any]:
    above_threshold = [ratio > threshold_ratio for ratio in ratios]
    longest = _longest_true_run(above_threshold)
    return {
        "subject": subject,
        "capacity_ratio_samples": ratios,
        "peak_capacity_ratio": max(ratios, default=0.0),
        "mean_capacity_ratio": (
            sum(ratios) / len(ratios) if ratios else 0.0
        ),
        "over_threshold_samples": sum(1 for value in above_threshold if value),
        "longest_consecutive_over_threshold": longest,
        "sustained_over_threshold": longest >= required_consecutive_samples,
    }


def collect_runner_cpu_pressure(
    run_command: RunCommand,
    containers: list[str],
    timeout_seconds: float,
    *,
    threshold_ratio: float,
    sample_count: int,
    required_consecutive_samples: int,
    sample_interval_seconds: float,
    sleep: Sleep = time.sleep,
) -> dict[str, Any]:
    if not 0 < threshold_ratio <= 1:
        return {"collection_ok": False, "error_code": "runner_cpu_ratio_invalid"}
    if sample_count < 2:
        return {"collection_ok": False, "error_code": "runner_cpu_sample_count_invalid"}
    if not 2 <= required_consecutive_samples <= sample_count:
        return {
            "collection_ok": False,
            "error_code": "runner_cpu_sustained_sample_count_invalid",
        }
    if sample_interval_seconds < 0:
        return {
            "collection_ok": False,
            "error_code": "runner_cpu_sample_interval_invalid",
        }

    capacity = collect_runner_cpu_capacity(
        run_command,
        containers,
        timeout_seconds,
    )
    if not capacity.get("ok"):
        return {
            "collection_ok": False,
            "error_code": capacity.get("error_code")
            or "runner_cpu_capacity_unavailable",
            "capacity": capacity,
        }
    capacity_by_container = {
        str(row["container"]): row for row in capacity.get("rows") or []
    }
    names = sorted(capacity_by_container)
    samples: list[dict[str, Any]] = []
    per_container_ratios: dict[str, list[float]] = {
        name: [] for name in names
    }
    aggregate_ratios: list[float] = []

    for sample_index in range(1, sample_count + 1):
        stats = run_command(
            [
                "docker",
                "stats",
                "--no-stream",
                "--format",
                "{{json .}}",
                *names,
            ],
            timeout_seconds,
        )
        if not stats.get("ok"):
            return {
                "collection_ok": False,
                "error_code": "runner_cpu_stats_unavailable",
                "capacity": capacity,
                "samples": samples,
            }
        try:
            raw_rows = [
                json.loads(line)
                for line in str(stats.get("stdout") or "").splitlines()
                if line.strip()
            ]
        except json.JSONDecodeError:
            return {
                "collection_ok": False,
                "error_code": "runner_cpu_stats_invalid",
                "capacity": capacity,
                "samples": samples,
            }
        rows_by_name = {
            str(row.get("Name") or "").strip().lstrip("/"): row
            for row in raw_rows
        }
        if set(rows_by_name) != set(names):
            return {
                "collection_ok": False,
                "error_code": "runner_cpu_stats_incomplete",
                "capacity": capacity,
                "samples": samples,
                "expected_containers": names,
                "observed_containers": sorted(rows_by_name),
            }

        sample_rows: list[dict[str, Any]] = []
        aggregate_cpu_percent = 0.0
        try:
            for name in names:
                cpu_percent = parse_percent(rows_by_name[name].get("CPUPerc", "0%"))
                effective_cpu_cores = float(
                    capacity_by_container[name]["effective_cpu_cores"]
                )
                capacity_ratio = cpu_percent / (effective_cpu_cores * 100.0)
                per_container_ratios[name].append(capacity_ratio)
                aggregate_cpu_percent += cpu_percent
                sample_rows.append(
                    {
                        "container": name,
                        "cpu_percent": cpu_percent,
                        "effective_cpu_cores": effective_cpu_cores,
                        "capacity_ratio": capacity_ratio,
                    }
                )
        except (TypeError, ValueError, ZeroDivisionError):
            return {
                "collection_ok": False,
                "error_code": "runner_cpu_stats_invalid",
                "capacity": capacity,
                "samples": samples,
            }
        aggregate_ratio = aggregate_cpu_percent / (
            float(capacity["docker_ncpu"]) * 100.0
        )
        aggregate_ratios.append(aggregate_ratio)
        samples.append(
            {
                "sample_index": sample_index,
                "containers": sample_rows,
                "aggregate": {
                    "cpu_percent": aggregate_cpu_percent,
                    "effective_cpu_cores": float(capacity["docker_ncpu"]),
                    "capacity_ratio": aggregate_ratio,
                },
            }
        )
        if sample_index < sample_count and sample_interval_seconds:
            sleep(sample_interval_seconds)

    evaluations = [
        _series_evidence(
            name,
            per_container_ratios[name],
            threshold_ratio=threshold_ratio,
            required_consecutive_samples=required_consecutive_samples,
        )
        for name in names
    ]
    evaluations.append(
        _series_evidence(
            "runner_aggregate",
            aggregate_ratios,
            threshold_ratio=threshold_ratio,
            required_consecutive_samples=required_consecutive_samples,
        )
    )
    failures = [
        (
            "runner_cpu_capacity_ratio_sustained:"
            f"{row['subject']}:ratio>{threshold_ratio}:"
            f"consecutive={row['longest_consecutive_over_threshold']}/"
            f"{sample_count}:peak={row['peak_capacity_ratio']:.6f}"
        )
        for row in evaluations
        if row["sustained_over_threshold"]
    ]
    return {
        "collection_ok": True,
        "ok": not failures,
        "gate_semantics": "effective_capacity_ratio_and_sustained_samples",
        "threshold_ratio": threshold_ratio,
        "sample_count": sample_count,
        "required_consecutive_samples": required_consecutive_samples,
        "sample_interval_seconds": sample_interval_seconds,
        "capacity": capacity,
        "samples": samples,
        "evaluations": evaluations,
        "failures": failures,
    }
