from __future__ import annotations

import json

import pytest

from scripts.maintenance.browser_resource_capacity_preflight_core.collectors import (
    parse_meminfo,
    parse_memory_events,
    parse_runner_max_inflight,
)
from scripts.maintenance.browser_resource_capacity_preflight_core.commands import (
    ensure_read_only_command,
)
from scripts.maintenance.browser_resource_capacity_preflight_core.policy import (
    CapacityInputs,
    evaluate_capacity,
)
from scripts.maintenance.browser_resource_capacity_preflight_core.cli import (
    load_request_evidence,
)


GIB = 1024 * 1024 * 1024


def _inputs(**overrides: object) -> CapacityInputs:
    values: dict[str, object] = {
        "mode": "pre-resume",
        "required_concurrency": 2,
        "claim_gate_state": "paused",
        "allocatable_bytes": 6 * GIB,
        "request_bytes": 6 * GIB,
        "mem_available_bytes": 9 * GIB,
        "running_count": 1,
        "running_distinct_locks": 1,
        "runnable_distinct_locks": 7,
        "duplicate_running_lock_count": 0,
        "runner_slot_capacity": 9,
        "processing_count": 2,
        "oom_kill_count": 0,
        "oom_group_kill_count": 0,
    }
    values.update(overrides)
    return CapacityInputs(**values)  # type: ignore[arg-type]


def test_current_bootstrap_capacity_blocks_required_two() -> None:
    result = evaluate_capacity(_inputs())

    assert result["verdict"] == "blocked"
    assert result["byte_capacity"] == 1
    assert result["blockers"] == ["byte_capacity_below_required"]


def test_measured_three_gib_request_passes_pre_resume_two() -> None:
    result = evaluate_capacity(_inputs(request_bytes=3 * GIB))

    assert result["verdict"] == "pass"
    assert result["byte_capacity"] == 2
    assert result["blockers"] == []


def test_post_resume_requires_two_distinct_running_tasks() -> None:
    result = evaluate_capacity(
        _inputs(
            mode="post-resume",
            claim_gate_state="open",
            request_bytes=3 * GIB,
            running_count=1,
            running_distinct_locks=1,
            processing_count=1,
        )
    )

    assert result["verdict"] == "blocked"
    assert result["blockers"] == [
        "actual_running_below_required",
        "running_distinct_locks_below_required",
        "processing_count_below_required",
    ]


def test_duplicate_running_profile_lock_is_always_blocked() -> None:
    result = evaluate_capacity(
        _inputs(request_bytes=3 * GIB, duplicate_running_lock_count=1)
    )

    assert result["blockers"] == ["duplicate_running_profile_lock"]


@pytest.mark.parametrize(
    "argv",
    [
        ["docker", "stop", "runner"],
        ["docker", "exec", "redis", "redis-cli", "SET", "key", "value"],
        ["docker", "exec", "postgres", "psql", "-Atc", "DELETE FROM tasks"],
        ["docker", "exec", "runner", "sh", "-lc", "cat /proc/meminfo"],
    ],
)
def test_command_policy_rejects_mutations_and_shells(argv: list[str]) -> None:
    with pytest.raises(ValueError):
        ensure_read_only_command(argv)


def test_command_policy_allows_bounded_reads() -> None:
    ensure_read_only_command(["docker", "info", "--format", "{{.MemTotal}}"])
    ensure_read_only_command(
        ["docker", "exec", "runner", "cat", "/proc/meminfo"]
    )
    ensure_read_only_command(
        ["docker", "exec", "redis", "redis-cli", "GET", "gate"]
    )
    ensure_read_only_command(
        ["docker", "exec", "postgres", "psql", "-Atc", "SELECT 1"]
    )


def test_runtime_parsers_are_strict_and_unit_safe() -> None:
    assert parse_meminfo("MemTotal: 100 kB\nMemAvailable: 40 kB\n") == {
        "total_bytes": 102400,
        "available_bytes": 40960,
    }
    assert parse_memory_events("oom_kill 2\noom_group_kill 1\n") == {
        "oom_kill": 2,
        "oom_group_kill": 1,
    }
    assert parse_runner_max_inflight(
        "LOCAL_CORE_RUNNER_PROFILE=browser\nLOCAL_CORE_RUNNER_MAX_INFLIGHT=3\n"
    ) == 3


def test_request_evidence_requires_three_valid_runs_per_workload(tmp_path) -> None:
    evidence = tmp_path / "summary.json"
    evidence.write_text(
        json.dumps(
            {
                "workloads": [
                    {
                        "workload_code": "ig_analyze_following",
                        "request_bytes": 3 * GIB,
                        "valid_run_count": 3,
                    },
                    {
                        "workload_code": "ig_pin_post_detail",
                        "request_bytes": 2 * GIB,
                        "valid_run_count": 3,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    request_bytes, provenance = load_request_evidence(evidence)

    assert request_bytes == 3 * GIB
    assert provenance["source"] == "calibration_summary"
    assert len(provenance["sha256"]) == 64


def test_request_evidence_rejects_fewer_than_three_runs(tmp_path) -> None:
    evidence = tmp_path / "summary.json"
    evidence.write_text(
        json.dumps(
            {
                "workloads": [
                    {
                        "workload_code": "ig_analyze_following",
                        "request_bytes": 3 * GIB,
                        "valid_run_count": 2,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="three runs"):
        load_request_evidence(evidence)
