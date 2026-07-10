from __future__ import annotations

import json

import pytest

from scripts.maintenance.browser_resource_capacity_preflight_core.candidate_plan import (
    build_candidate_request_plan,
    normalize_profile_identity,
    summarize_physical_profiles,
)
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
        "required_concurrency": 6,
        "claim_gate_state": "paused",
        "allocatable_bytes": 6 * GIB,
        "reserved_bytes": 6 * GIB,
        "additional_request_bytes": (6 * GIB, 6 * GIB, 6 * GIB),
        "missing_request_workload_count": 0,
        "mem_available_bytes": 9 * GIB,
        "running_count": 1,
        "running_physical_profile_count": 1,
        "runnable_physical_profile_count": 4,
        "duplicate_running_physical_profile_count": 0,
        "selected_candidate_count": 4,
        "runner_slot_capacity": 9,
        "processing_count": 2,
        "oom_kill_count": 0,
        "oom_group_kill_count": 0,
    }
    values.update(overrides)
    return CapacityInputs(**values)  # type: ignore[arg-type]


def test_current_bootstrap_capacity_blocks_required_six_profiles() -> None:
    result = evaluate_capacity(_inputs())

    assert result["verdict"] == "blocked"
    assert result["byte_capacity"] == 1
    assert result["blockers"] == [
        "physical_profile_capacity_below_required",
        "byte_capacity_below_required",
        "mem_available_below_required",
    ]


def test_heterogeneous_request_vector_passes_pre_resume_six() -> None:
    result = evaluate_capacity(
        _inputs(
            reserved_bytes=1 * GIB,
            additional_request_bytes=(
                1 * GIB,
                1 * GIB,
                1 * GIB,
                1 * GIB,
                1 * GIB,
            ),
            mem_available_bytes=5 * GIB,
            runnable_physical_profile_count=6,
            selected_candidate_count=6,
        )
    )

    assert result["verdict"] == "pass"
    assert result["byte_capacity"] == 6
    assert result["projected_reserved_bytes"] == 6 * GIB
    assert result["blockers"] == []


def test_post_resume_requires_six_distinct_physical_profiles() -> None:
    result = evaluate_capacity(
        _inputs(
            mode="post-resume",
            claim_gate_state="open",
            reserved_bytes=1 * GIB,
            additional_request_bytes=(
                1 * GIB,
                1 * GIB,
                1 * GIB,
                1 * GIB,
                1 * GIB,
            ),
            mem_available_bytes=5 * GIB,
            running_count=1,
            running_physical_profile_count=1,
            runnable_physical_profile_count=6,
            selected_candidate_count=6,
            processing_count=1,
        )
    )

    assert result["verdict"] == "blocked"
    assert result["blockers"] == [
        "actual_running_below_required",
        "running_physical_profiles_below_required",
        "processing_count_below_required",
    ]


def test_duplicate_running_physical_profile_is_always_blocked() -> None:
    result = evaluate_capacity(
        _inputs(duplicate_running_physical_profile_count=1)
    )

    assert result["blockers"] == [
        "physical_profile_capacity_below_required",
        "byte_capacity_below_required",
        "mem_available_below_required",
        "duplicate_running_physical_profile",
    ]


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


def test_physical_profile_summary_does_not_count_playbook_keys() -> None:
    summary = summarize_physical_profiles(
        {
            "running_count": 2,
            "candidates": [
                {
                    "task_id": "analyze",
                    "workload_code": "ig_analyze_following",
                    "status": "running",
                    "profile_path": "/profiles/walto/",
                    "concurrency_key": "playbook:analyze:/profiles/walto",
                    "created_at": "2026-07-08T00:00:00+00:00",
                },
                {
                    "task_id": "detail",
                    "workload_code": "ig_pin_post_detail",
                    "status": "running",
                    "profile_path": "/profiles/walto",
                    "concurrency_key": "playbook:detail:/profiles/walto",
                    "created_at": "2026-07-08T00:01:00+00:00",
                },
                {
                    "task_id": "chaos",
                    "workload_code": "ig_pin_post_detail",
                    "status": "pending",
                    "profile_path": "/profiles/chaos",
                    "created_at": "2026-07-08T00:02:00+00:00",
                },
            ],
        }
    )

    assert normalize_profile_identity("/profiles/walto/") == "/profiles/walto"
    assert summary["runnable_physical_profile_count"] == 2
    assert summary["running_physical_profile_count"] == 1
    assert summary["duplicate_running_physical_profile_count"] == 1


def test_candidate_request_plan_uses_per_workload_bytes() -> None:
    tasks = {
        "physical_profile_candidates": [
            {
                "task_id": "running",
                "workload_code": "ig_analyze_following",
                "status": "running",
                "profile_identity": "/profiles/a",
            },
            {
                "task_id": "detail",
                "workload_code": "ig_pin_post_detail",
                "status": "pending",
                "profile_identity": "/profiles/b",
            },
        ]
    }

    plan = build_candidate_request_plan(
        tasks,
        required_concurrency=2,
        default_request_bytes=None,
        workload_request_bytes={
            "ig_analyze_following": 2 * GIB,
            "ig_pin_post_detail": 1 * GIB,
        },
    )

    assert plan["additional_request_bytes"] == [1 * GIB]
    assert plan["missing_request_workloads"] == []
    assert [item["request_bytes"] for item in plan["selected_candidates"]] == [
        2 * GIB,
        1 * GIB,
    ]


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

    assert request_bytes == {
        "ig_analyze_following": 3 * GIB,
        "ig_pin_post_detail": 2 * GIB,
    }
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
