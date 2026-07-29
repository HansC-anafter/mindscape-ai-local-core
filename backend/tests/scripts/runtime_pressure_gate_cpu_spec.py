from __future__ import annotations

import json

import pytest

from scripts.maintenance.runtime_pressure_gate_core.cpu import (
    collect_runner_cpu_pressure,
    parse_cpuset_cpu_count,
)


def _cpu_probe(
    samples: list[dict[str, float]],
    *,
    docker_ncpu: int = 14,
    host_configs: dict[str, dict[str, object]] | None = None,
):
    names = sorted(samples[0])
    configs = host_configs or {
        name: {
            "nano_cpus": 0,
            "cpu_quota": 0,
            "cpu_period": 0,
            "cpuset_cpus": "",
        }
        for name in names
    }
    sample_cursor = 0

    def _run(command, _timeout_seconds):
        nonlocal sample_cursor
        if command[:2] == ["docker", "info"]:
            return {"ok": True, "stdout": json.dumps(docker_ncpu) + "\n"}
        if command[:2] == ["docker", "inspect"]:
            stdout = "\n".join(
                json.dumps({"name": f"/{name}", **configs[name]})
                for name in names
            )
            return {"ok": True, "stdout": stdout + "\n"}
        if command[:2] == ["docker", "stats"]:
            values = samples[sample_cursor]
            sample_cursor += 1
            stdout = "\n".join(
                json.dumps({"Name": name, "CPUPerc": f"{values[name]}%"})
                for name in names
            )
            return {"ok": True, "stdout": stdout + "\n"}
        raise AssertionError(command)

    return _run, names


def test_cpuset_cpu_count_supports_ranges_and_duplicates():
    assert parse_cpuset_cpu_count("") is None
    assert parse_cpuset_cpu_count("0-3,5,7-8,3") == 7
    with pytest.raises(ValueError, match="cpuset"):
        parse_cpuset_cpu_count("3-1")


@pytest.mark.parametrize(
    ("host_config", "expected_cores", "expected_source"),
    [
        (
            {
                "nano_cpus": 2_500_000_000,
                "cpu_quota": 0,
                "cpu_period": 0,
                "cpuset_cpus": "",
            },
            2.5,
            "nano_cpus",
        ),
        (
            {
                "nano_cpus": 0,
                "cpu_quota": 250_000,
                "cpu_period": 100_000,
                "cpuset_cpus": "",
            },
            2.5,
            "cpu_quota",
        ),
        (
            {
                "nano_cpus": 0,
                "cpu_quota": 0,
                "cpu_period": 0,
                "cpuset_cpus": "0-2",
            },
            3.0,
            "cpuset_cpus",
        ),
    ],
)
def test_each_container_cpu_limit_can_define_effective_capacity(
    host_config,
    expected_cores,
    expected_source,
):
    run_command, names = _cpu_probe(
        [{"runner-browser": 0.0} for _ in range(2)],
        host_configs={"runner-browser": host_config},
    )

    evidence = collect_runner_cpu_pressure(
        run_command,
        names,
        5.0,
        threshold_ratio=0.90,
        sample_count=2,
        required_consecutive_samples=2,
        sample_interval_seconds=0,
        sleep=lambda _seconds: None,
    )

    capacity = evidence["capacity"]["rows"][0]
    assert capacity["effective_cpu_cores"] == expected_cores
    assert capacity["effective_capacity_sources"] == [expected_source]


def test_unlimited_runner_uses_docker_ncpu_and_treats_five_samples_as_bursts():
    percentages = [239.62, 512.23, 401.0, 480.0, 300.0]
    run_command, names = _cpu_probe(
        [{"runner-browser-extra": value} for value in percentages]
    )

    evidence = collect_runner_cpu_pressure(
        run_command,
        names,
        5.0,
        threshold_ratio=0.90,
        sample_count=5,
        required_consecutive_samples=3,
        sample_interval_seconds=2.0,
        sleep=lambda _seconds: None,
    )

    assert evidence["collection_ok"] is True
    assert evidence["ok"] is True
    assert evidence["failures"] == []
    capacity = evidence["capacity"]["rows"][0]
    assert capacity["effective_cpu_cores"] == 14.0
    assert capacity["effective_capacity_sources"] == ["docker_ncpu"]
    ratios = evidence["evaluations"][0]["capacity_ratio_samples"]
    assert ratios[0] == pytest.approx(239.62 / 1400.0)
    assert ratios[1] == pytest.approx(512.23 / 1400.0)


def test_effective_capacity_uses_smallest_quota_or_cpuset_limit():
    samples = [{"runner-browser": value} for value in (185.0, 190.0, 195.0, 10.0, 10.0)]
    run_command, names = _cpu_probe(
        samples,
        host_configs={
            "runner-browser": {
                "nano_cpus": 3_000_000_000,
                "cpu_quota": 200_000,
                "cpu_period": 100_000,
                "cpuset_cpus": "0-3",
            }
        },
    )

    evidence = collect_runner_cpu_pressure(
        run_command,
        names,
        5.0,
        threshold_ratio=0.90,
        sample_count=5,
        required_consecutive_samples=3,
        sample_interval_seconds=0,
        sleep=lambda _seconds: None,
    )

    capacity = evidence["capacity"]["rows"][0]
    assert capacity["effective_cpu_cores"] == 2.0
    assert capacity["effective_capacity_sources"] == ["cpu_quota"]
    assert capacity["quota_limited"] is True
    assert evidence["ok"] is False
    assert evidence["evaluations"][0]["longest_consecutive_over_threshold"] == 3
    assert evidence["failures"][0].startswith(
        "runner_cpu_capacity_ratio_sustained:runner-browser"
    )


def test_non_consecutive_runner_spikes_do_not_count_as_sustained_pressure():
    run_command, names = _cpu_probe(
        [
            {"runner-browser-extra": value}
            for value in (1300.0, 100.0, 1300.0, 100.0, 1300.0)
        ]
    )

    evidence = collect_runner_cpu_pressure(
        run_command,
        names,
        5.0,
        threshold_ratio=0.90,
        sample_count=5,
        required_consecutive_samples=3,
        sample_interval_seconds=0,
        sleep=lambda _seconds: None,
    )

    assert evidence["ok"] is True
    assert evidence["evaluations"][0]["over_threshold_samples"] == 3
    assert (
        evidence["evaluations"][0]["longest_consecutive_over_threshold"]
        == 1
    )


def test_aggregate_runner_pressure_is_evaluated_against_docker_capacity():
    run_command, names = _cpu_probe(
        [
            {"runner-browser": 700.0, "runner-browser-extra": 700.0}
            for _ in range(5)
        ]
    )

    evidence = collect_runner_cpu_pressure(
        run_command,
        names,
        5.0,
        threshold_ratio=0.90,
        sample_count=5,
        required_consecutive_samples=3,
        sample_interval_seconds=0,
        sleep=lambda _seconds: None,
    )

    assert evidence["evaluations"][0]["sustained_over_threshold"] is False
    assert evidence["evaluations"][1]["sustained_over_threshold"] is False
    aggregate = evidence["evaluations"][2]
    assert aggregate["subject"] == "runner_aggregate"
    assert aggregate["peak_capacity_ratio"] == pytest.approx(1.0)
    assert aggregate["sustained_over_threshold"] is True
    assert evidence["ok"] is False


def test_runner_cpu_collection_fails_closed_when_any_sample_is_unavailable():
    base_run, names = _cpu_probe(
        [{"runner-browser-extra": 100.0} for _ in range(5)]
    )
    stats_calls = 0

    def _run(command, timeout_seconds):
        nonlocal stats_calls
        if command[:2] == ["docker", "stats"]:
            stats_calls += 1
            if stats_calls == 3:
                return {"ok": False, "stderr": "sample unavailable"}
        return base_run(command, timeout_seconds)

    evidence = collect_runner_cpu_pressure(
        _run,
        names,
        5.0,
        threshold_ratio=0.90,
        sample_count=5,
        required_consecutive_samples=3,
        sample_interval_seconds=0,
        sleep=lambda _seconds: None,
    )

    assert evidence["collection_ok"] is False
    assert evidence["error_code"] == "runner_cpu_stats_unavailable"
    assert len(evidence["samples"]) == 2
