from __future__ import annotations

import json

import pytest

from scripts.maintenance.browser_resource_capacity_preflight_core.candidate_plan import (
    build_candidate_request_plan,
    normalize_profile_identity,
    summarize_task_candidates,
    workload_envelope_id,
)
from scripts.maintenance.browser_resource_capacity_preflight_core.cli import (
    load_request_evidence,
)
from scripts.maintenance.browser_resource_capacity_preflight_core.collectors import (
    parse_meminfo,
    parse_memory_events,
    parse_runner_max_inflight,
    parse_runner_partitions,
)
from scripts.maintenance.browser_resource_capacity_preflight_core.commands import (
    ensure_read_only_command,
)
from scripts.maintenance.browser_resource_capacity_preflight_core.policy import (
    CapacityInputs,
    evaluate_capacity,
)


GIB = 1024 * 1024 * 1024


def _inputs(**overrides: object) -> CapacityInputs:
    values: dict[str, object] = {
        "mode": "pre-resume",
        "required_concurrency": 6,
        "claim_gate_state": "paused",
        "allocatable_bytes": 6 * GIB,
        "reserved_bytes": 6 * GIB,
        "additional_request_bytes": (6 * GIB,) * 4,
        "missing_request_workload_count": 0,
        "mem_available_bytes": 9 * GIB,
        "running_count": 1,
        "fresh_live_running_count": 0,
        "stale_running_count": 1,
        "eligible_candidate_count": 5,
        "running_lock_conflict_count": 0,
        "selected_candidate_count": 5,
        "runner_slot_capacity": 9,
        "processing_count": 1,
        "oom_kill_count": 0,
        "oom_group_kill_count": 0,
    }
    values.update(overrides)
    return CapacityInputs(**values)  # type: ignore[arg-type]


def test_current_bootstrap_capacity_blocks_required_six_live_tasks() -> None:
    result = evaluate_capacity(_inputs())

    assert result["verdict"] == "blocked"
    assert result["byte_capacity"] == 1
    assert result["blockers"] == [
        "lock_or_partition_capacity_below_required",
        "byte_capacity_below_required",
        "mem_available_below_required",
        "stale_running_tasks",
    ]


def test_heterogeneous_request_vector_passes_pre_resume_six() -> None:
    result = evaluate_capacity(
        _inputs(
            reserved_bytes=1 * GIB,
            additional_request_bytes=(1 * GIB,) * 5,
            mem_available_bytes=5 * GIB,
            fresh_live_running_count=1,
            stale_running_count=0,
            eligible_candidate_count=6,
            selected_candidate_count=6,
        )
    )

    assert result["verdict"] == "pass"
    assert result["byte_capacity"] == 6
    assert result["projected_reserved_bytes"] == 6 * GIB


def test_post_resume_requires_six_fresh_live_tasks() -> None:
    result = evaluate_capacity(
        _inputs(
            mode="post-resume",
            claim_gate_state="open",
            reserved_bytes=6 * GIB,
            additional_request_bytes=(),
            mem_available_bytes=5 * GIB,
            running_count=6,
            fresh_live_running_count=5,
            stale_running_count=1,
            eligible_candidate_count=6,
            selected_candidate_count=6,
            processing_count=6,
        )
    )

    assert result["blockers"] == [
        "stale_running_tasks",
        "fresh_live_running_below_required",
    ]


def test_running_lock_conflict_is_always_blocked() -> None:
    result = evaluate_capacity(
        _inputs(running_lock_conflict_count=1)
    )
    assert "running_lock_conflict" in result["blockers"]


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
        ["docker", "exec", "redis", "redis-cli", "TTL", "gate"]
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
    env = (
        "LOCAL_CORE_RUNNER_ACCEPTED_PARTITIONS=browser_local,ig_browser\n"
        "LOCAL_CORE_RUNNER_MAX_INFLIGHT=3\n"
    )
    assert parse_runner_max_inflight(env) == 3
    assert parse_runner_partitions(env) == ("browser_local", "ig_browser")


def _context(
    *,
    code: str,
    profile: str,
    source_mode: str | None = None,
    target: str | None = None,
    captured_target_lock: bool = False,
) -> dict:
    inputs = {"user_data_dir": profile}
    if source_mode:
        inputs["source_mode"] = source_mode
    if target:
        inputs["target_handle"] = target
    if captured_target_lock:
        concurrency = {
            "lock_key_input": "target_handle",
            "lock_scope": "playbook_input",
        }
    else:
        concurrency = {
            "lock_key_input": "user_data_dir",
            "lock_scope": "playbook_input",
            "lock_aliases": [
                {"lock_key_input": "user_data_dir", "lock_scope": "input"}
            ],
        }
    return {
        "playbook_code": code,
        "inputs": inputs,
        "resource_class": "browser",
        "concurrency": concurrency,
    }


def _candidate(
    task_id: str,
    context: dict,
    *,
    status: str = "pending",
    partition: str = "browser_local",
    heartbeat_fresh: bool = False,
) -> dict:
    return {
        "task_id": task_id,
        "workload_code": context["playbook_code"],
        "status": status,
        "queue_shard": partition,
        "execution_context": context,
        "concurrency_key": "",
        "heartbeat_fresh": heartbeat_fresh,
        "created_at": f"2026-07-10T00:00:{task_id[-2:]}+00:00",
    }


def _metadata() -> dict:
    base = {
        "resource_class": "browser",
        "resource_requirements": {
            "browser_contexts": 1,
            "ig_profile_lock": "{user_data_dir}",
        },
    }
    return {
        "ig_analyze_following": base,
        "ig_pin_post_detail": base,
        "ig_batch_pin_references": {
            **base,
            "resource_requirement_variants": [
                {
                    "when": {"input": "source_mode", "equals": "captured_posts"},
                    "resource_requirements": {"ig_profile_lock": False},
                }
            ],
        },
    }


def test_four_profile_locks_plus_two_captured_targets_select_six() -> None:
    rows = [
        _candidate(
            f"profile-{index:02d}",
            _context(
                code="ig_analyze_following",
                profile=f"/profiles/{index}/",
            ),
        )
        for index in range(4)
    ]
    rows.extend(
        [
            _candidate(
                f"captured-{index:02d}",
                _context(
                    code="ig_batch_pin_references",
                    profile="/profiles/0",
                    source_mode="captured_posts",
                    target=f"target-{index}",
                    captured_target_lock=True,
                ),
                partition="default_local_browser",
            )
            for index in range(2)
        ]
    )
    summary = summarize_task_candidates(
        {"candidates": rows},
        playbook_metadata=_metadata(),
    )
    plan = build_candidate_request_plan(
        summary,
        required_concurrency=6,
        default_request_bytes=None,
        envelope_request_bytes={
            "ig_analyze_following": GIB,
            "ig_batch_pin_references.captured_posts": GIB // 2,
        },
        slot_capacity_by_partition={
            "browser_local": 6,
            "default_local_browser": 3,
        },
        available_request_bytes=5 * GIB,
    )

    assert normalize_profile_identity("/profiles/0/") == "/profiles/0"
    assert plan["eligible_candidate_count"] == 6
    assert sorted(plan["additional_request_bytes"]) == [
        GIB // 2,
        GIB // 2,
        GIB,
        GIB,
        GIB,
        GIB,
    ]


def test_six_profile_locked_tasks_on_four_profiles_select_only_four() -> None:
    rows = [
        _candidate(
            f"task-{index:02d}",
            _context(
                code="ig_pin_post_detail",
                profile=f"/profiles/{index % 4}",
            ),
            partition="default_local_browser",
        )
        for index in range(6)
    ]
    summary = summarize_task_candidates(
        {"candidates": rows},
        playbook_metadata=_metadata(),
    )
    plan = build_candidate_request_plan(
        summary,
        required_concurrency=6,
        default_request_bytes=GIB,
        envelope_request_bytes={},
        slot_capacity_by_partition={"default_local_browser": 6},
        available_request_bytes=6 * GIB,
    )

    assert plan["eligible_candidate_count"] == 4
    assert plan["lock_blocked_candidate_count"] == 2


def test_older_oversized_candidate_does_not_hide_smaller_valid_vector() -> None:
    rows = [
        _candidate(
            "large-01",
            _context(
                code="ig_batch_pin_references",
                profile="/profiles/large",
                source_mode="browser",
                target="large",
                captured_target_lock=True,
            ),
        ),
        _candidate(
            "small-01",
            _context(
                code="ig_batch_pin_references",
                profile="/profiles/small",
                source_mode="captured_posts",
                target="small",
                captured_target_lock=True,
            ),
            partition="default_local_browser",
        ),
    ]
    summary = summarize_task_candidates(
        {"candidates": rows},
        playbook_metadata=_metadata(),
    )

    plan = build_candidate_request_plan(
        summary,
        required_concurrency=1,
        default_request_bytes=None,
        envelope_request_bytes={
            "ig_batch_pin_references.browser": 2 * GIB,
            "ig_batch_pin_references.captured_posts": GIB,
        },
        slot_capacity_by_partition={
            "browser_local": 6,
            "default_local_browser": 3,
        },
        available_request_bytes=GIB,
    )

    assert plan["selected_candidate_count"] == 1
    assert plan["selected_candidates"][0]["task_id"] == "small-01"
    assert plan["byte_blocked_candidate_count"] == 1


def test_stale_running_task_never_becomes_fresh_live() -> None:
    context = _context(
        code="ig_analyze_following",
        profile="/profiles/a",
    )
    summary = summarize_task_candidates(
        {
            "candidates": [
                _candidate(
                    "running-01",
                    context,
                    status="running",
                    heartbeat_fresh=False,
                )
            ]
        },
        playbook_metadata=_metadata(),
        processing_task_ids={"running-01"},
        reservation_owner_ids={"runner:running-01"},
    )

    assert summary["running_count"] == 1
    assert summary["fresh_live_running_count"] == 0
    assert summary["stale_running_count"] == 1


def test_exact_live_owner_overrides_stale_db_heartbeat() -> None:
    context = _context(
        code="ig_analyze_following",
        profile="/profiles/a",
    )
    summary = summarize_task_candidates(
        {
            "candidates": [
                {
                    **_candidate(
                        "running-01",
                        context,
                        status="running",
                        heartbeat_fresh=False,
                    ),
                    "runner_id": "runner-01",
                }
            ]
        },
        playbook_metadata=_metadata(),
        processing_task_ids={"running-01"},
        reservation_owner_ids={"runner-01:running-01"},
        live_owners={
            "running-01": {
                "task_id": "running-01",
                "runner_id": "runner-01",
                "ttl_seconds_remaining": 60,
            }
        },
    )

    candidate = summary["task_candidates"][0]
    assert candidate["db_heartbeat_fresh"] is False
    assert candidate["live_owner_fresh"] is True
    assert candidate["fresh_live"] is True
    assert summary["fresh_live_running_count"] == 1
    assert summary["stale_running_count"] == 0


@pytest.mark.parametrize(
    ("live_owner", "processing_ids", "reservation_ids"),
    [
        (
            {
                "task_id": "running-01",
                "runner_id": "runner-other",
                "ttl_seconds_remaining": 60,
            },
            {"running-01"},
            {"runner-01:running-01"},
        ),
        (
            {
                "task_id": "running-01",
                "runner_id": "runner-01",
                "ttl_seconds_remaining": 0,
            },
            {"running-01"},
            {"runner-01:running-01"},
        ),
        (
            {
                "task_id": "running-01",
                "runner_id": "runner-01",
                "ttl_seconds_remaining": 60,
            },
            set(),
            {"runner-01:running-01"},
        ),
        (
            {
                "task_id": "running-01",
                "runner_id": "runner-01",
                "ttl_seconds_remaining": 60,
            },
            {"running-01"},
            set(),
        ),
    ],
)
def test_live_owner_requires_exact_runtime_conjunction(
    live_owner: dict[str, object],
    processing_ids: set[str],
    reservation_ids: set[str],
) -> None:
    summary = summarize_task_candidates(
        {
            "candidates": [
                {
                    **_candidate(
                        "running-01",
                        _context(
                            code="ig_analyze_following",
                            profile="/profiles/a",
                        ),
                        status="running",
                        heartbeat_fresh=True,
                    ),
                    "runner_id": "runner-01",
                }
            ]
        },
        playbook_metadata=_metadata(),
        processing_task_ids=processing_ids,
        reservation_owner_ids=reservation_ids,
        live_owners={"running-01": live_owner},
    )

    assert summary["fresh_live_running_count"] == 0
    assert summary["stale_running_count"] == 1


def test_workload_envelope_distinguishes_batch_source_modes() -> None:
    assert workload_envelope_id(
        "ig_batch_pin_references", {"source_mode": "browser"}
    ) == "ig_batch_pin_references.browser"
    assert workload_envelope_id(
        "ig_batch_pin_references", {"source_mode": "captured_posts"}
    ) == "ig_batch_pin_references.captured_posts"


def test_request_evidence_requires_three_valid_runs_per_envelope(tmp_path) -> None:
    evidence = tmp_path / "summary.json"
    evidence.write_text(
        json.dumps(
            {
                "workloads": [
                    {
                        "envelope_id": "ig_batch_pin_references.browser",
                        "request_bytes": 3 * GIB,
                        "valid_run_count": 3,
                    },
                    {
                        "envelope_id": "ig_batch_pin_references.captured_posts",
                        "request_bytes": GIB,
                        "valid_run_count": 3,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    request_bytes, provenance = load_request_evidence(evidence)
    assert request_bytes == {
        "ig_batch_pin_references.browser": 3 * GIB,
        "ig_batch_pin_references.captured_posts": GIB,
    }
    assert provenance["source"] == "calibration_summary"


def test_request_evidence_rejects_fewer_than_three_runs(tmp_path) -> None:
    evidence = tmp_path / "summary.json"
    evidence.write_text(
        json.dumps(
            {
                "workloads": [
                    {
                        "envelope_id": "ig_analyze_following",
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
