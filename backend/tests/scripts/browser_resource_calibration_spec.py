from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.maintenance.browser_resource_calibration_core.cli import (
    _wait_for_idle_reset,
)
from scripts.maintenance.browser_resource_calibration_core.evidence import evidence_row
from scripts.maintenance.browser_resource_calibration_core.collectors import (
    CalibrationCollector,
    CalibrationCommandError,
    parse_pgbouncer_pools,
)
from scripts.maintenance.browser_resource_calibration_core.envelope_classifier import (
    classify_task_envelope,
)
from scripts.maintenance.browser_resource_calibration_core.http_client import (
    validate_local_request,
)
from scripts.maintenance.browser_resource_calibration_core.natural_claim_observer import (
    NaturalClaimObservationError,
    select_fresh_running_task,
    validate_live_owner,
    wait_for_natural_claim,
)
from scripts.maintenance.browser_resource_calibration_core.parsing import (
    build_node_sample,
    parse_size_bytes,
    round_request_bytes,
    summarize_baseline,
    summarize_node_cadence,
    summarize_task_memory_series,
    summarize_workload_runs,
)
from scripts.maintenance.browser_resource_calibration_core.workloads import (
    load_workload_manifest,
    quota_state,
)
from scripts.maintenance.browser_node_budget_reconcile_core import (
    validate_reconciliation_evidence,
)


GIB = 1024 * 1024 * 1024


def test_idle_reset_waits_through_transient_container_recreation(monkeypatch) -> None:
    class Collector:
        def __init__(self) -> None:
            self.calls = 0

        def collect_node(self, *, include_all_containers):
            assert include_all_containers is False
            self.calls += 1
            if self.calls == 1:
                raise CalibrationCommandError(
                    ["docker", "exec", "runner-browser", "cat", "/proc/meminfo"],
                    1,
                    "",
                )
            return {
                "browser_cgroups": [{"memory_peak_bytes": 100}],
            }

    class Writer:
        def __init__(self) -> None:
            self.rows = []

        def append(self, row) -> None:
            self.rows.append(row)

    monkeypatch.setattr(
        "scripts.maintenance.browser_resource_calibration_core.cli.time.sleep",
        lambda _seconds: None,
    )
    collector = Collector()
    collector.browser_containers = ("runner-browser",)
    writer = Writer()

    node = _wait_for_idle_reset(
        collector=collector,
        writer=writer,
        baseline={"browser_idle_peak_bytes": 100},
        timeout_seconds=1,
    )

    assert collector.calls == 2
    assert node["browser_cgroups"][0]["memory_peak_bytes"] == 100
    assert writer.rows[0]["kind"] == "idle_cgroup_reset_ready"


def test_idle_reset_does_not_hide_non_transient_collector_failure() -> None:
    class Collector:
        def collect_node(self, *, include_all_containers):
            assert include_all_containers is False
            raise RuntimeError("permission denied")

    with pytest.raises(RuntimeError, match="permission denied"):
        _wait_for_idle_reset(
            collector=Collector(),
            writer=type("Writer", (), {"append": lambda self, row: None})(),
            baseline={"browser_idle_peak_bytes": 100},
            timeout_seconds=1,
        )


def test_workload_node_collection_uses_exact_cgroups_without_docker_stats() -> None:
    class Commands:
        def __init__(self):
            self.calls = []
            self.timeouts = []

        def run(self, argv, *, timeout_seconds=5):
            self.calls.append(tuple(argv))
            self.timeouts.append((tuple(argv), timeout_seconds))
            if argv[3] == "python":
                output = json.dumps(
                    {
                        "memory_current_bytes": 1000,
                        "memory_peak_bytes": 1200,
                        "inactive_file_bytes": 100,
                        "oom_kill": 0,
                        "oom_group_kill": 0,
                    }
                )
                return type(
                    "Result",
                    (),
                    {"returncode": 0, "stdout": output, "stderr": ""},
                )()
            path = argv[-1]
            if path == "/proc/meminfo":
                output = "MemTotal: 16384 kB\nMemAvailable: 8192 kB\n"
            else:
                raise AssertionError(argv)
            return type("Result", (), {"returncode": 0, "stdout": output, "stderr": ""})()

    commands = Commands()
    sample = CalibrationCollector(
        browser_containers=("runner-browser",),
        command_runner=commands,
    ).collect_node(include_all_containers=False)

    assert sample["browser_container_working_set_bytes"] == 900
    assert sample["non_browser_container_working_set_bytes"] == 0
    assert sum(call[1] == "exec" for call in commands.calls) == 2
    assert not any(call[1:3] == ("stats", "--no-stream") for call in commands.calls)
    assert [
        timeout
        for call, timeout in commands.timeouts
        if call[3] == "python"
    ] == [8]


def test_pgbouncer_pool_parser_keeps_only_core_vector_wait_gates() -> None:
    row = "|".join(
        [
            "mindscape_core",
            "mindscape",
            "4",
            "0",
            "0",
            "0",
            "0",
            "0",
            "0",
            "3",
            "1",
            "0",
            "0",
            "0",
            "0",
            "transaction",
            "",
        ]
    )
    ignored = row.replace("mindscape_core", "pgbouncer", 1)
    pools = parse_pgbouncer_pools(f"{row}\n{ignored}\n")
    assert pools == [
        {
            "database": "mindscape_core",
            "user": "mindscape",
            "cl_active": "4",
            "cl_waiting": "0",
            "cl_active_cancel_req": "0",
            "cl_waiting_cancel_req": "0",
            "sv_active": "0",
            "sv_active_cancel": "0",
            "sv_being_canceled": "0",
            "sv_idle": "3",
            "sv_used": "1",
            "sv_tested": "0",
            "sv_login": "0",
            "maxwait": "0",
            "maxwait_us": "0",
            "pool_mode": "transaction",
            "load_balance_hosts": "",
        }
    ]


def test_size_and_node_sample_formulas() -> None:
    assert parse_size_bytes("1.5GiB") == int(1.5 * GIB)
    sample = build_node_sample(
        captured_at_epoch=1.0,
        meminfo_raw="MemTotal: 16384 kB\nMemAvailable: 8192 kB\n",
        docker_stats_raw="\n".join(
            [
                json.dumps({"Name": "browser", "MemUsage": "2MiB / 6GiB"}),
                json.dumps({"Name": "postgres", "MemUsage": "1MiB / 16GiB"}),
            ]
        ),
        browser_containers=("browser",),
        cgroup_rows=[],
    )

    assert sample["browser_container_working_set_bytes"] == 2 * 1024 * 1024
    assert sample["non_browser_container_working_set_bytes"] == 1024 * 1024
    assert sample["vm_overhead_bytes"] == 5 * 1024 * 1024


def test_baseline_and_workload_summary_use_maxima_and_rounding() -> None:
    samples = [
        {
            "captured_at_epoch": 0,
            "vm_overhead_bytes": 10,
            "non_browser_container_working_set_bytes": 20,
            "browser_container_working_set_bytes": 30,
            "mem_available_bytes": 100,
        },
        {
            "captured_at_epoch": 5,
            "vm_overhead_bytes": 11,
            "non_browser_container_working_set_bytes": 19,
            "browser_container_working_set_bytes": 31,
            "mem_available_bytes": 90,
        },
    ]
    baseline = summarize_baseline(samples, duration_seconds=1800)
    assert baseline["vm_overhead_peak_bytes"] == 11
    assert baseline["non_browser_peak_bytes"] == 20
    assert baseline["browser_idle_peak_bytes"] == 31
    assert baseline["node_cadence"]["status"] == "pass"
    assert round_request_bytes(65 * 1024 * 1024) == 128 * 1024 * 1024

    runs = [
        {
            "envelope_id": "ig_pin_post_detail",
            "workload_code": "ig_pin_post_detail",
            "valid": True,
            "startup_peak_bytes": peak + 64 * 1024 * 1024,
            "steady_peak_bytes": peak,
            "startup_settle_seconds": 12,
            "payload_sha256": f"hash-{peak}",
        }
        for peak in (65 * 1024 * 1024, 70 * 1024 * 1024, 80 * 1024 * 1024)
    ]
    summary = summarize_workload_runs(
        runs,
        required_envelopes={"ig_pin_post_detail"},
    )
    assert summary["status"] == "pass"
    assert summary["workloads"][0]["request_bytes"] == 128 * 1024 * 1024
    assert summary["workloads"][0]["startup_spacing_seconds"] == 15


def test_workload_summary_fails_without_three_valid_runs() -> None:
    summary = summarize_workload_runs(
        [
            {
                "envelope_id": "ig_analyze_following",
                "workload_code": "ig_analyze_following",
                "valid": True,
                "startup_peak_bytes": GIB,
                "steady_peak_bytes": GIB,
                "startup_settle_seconds": 0,
                "payload_sha256": "one",
            }
        ],
        required_envelopes={"ig_analyze_following"},
    )
    assert summary["status"] == "blocked"
    assert summary["failures"] == ["ig_analyze_following:valid_runs=1"]


def test_workload_summary_accepts_distinct_natural_task_inputs() -> None:
    summary = summarize_workload_runs(
        [
            {
                "envelope_id": "ig_analyze_following",
                "workload_code": "ig_analyze_following",
                "valid": True,
                "startup_peak_bytes": GIB,
                "steady_peak_bytes": GIB // 2,
                "startup_settle_seconds": 6,
                "payload_sha256": value,
            }
            for value in ("one", "one", "two")
        ],
        required_envelopes={"ig_analyze_following"},
    )
    assert summary["status"] == "pass"
    assert summary["workloads"][0]["payload_sha256s"] == ["one", "two"]


def test_manifest_requires_natural_claim_quota_contract(tmp_path) -> None:
    baseline = tmp_path / "baseline.json"
    baseline.write_text("{}", encoding="utf-8")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "version": 2,
                "baseline_summary_path": str(baseline),
                "required_valid_runs_per_envelope": 3,
                "max_browser_local_runs": 24,
                "max_captured_post_runs": 3,
            }
        ),
        encoding="utf-8",
    )
    manifest = load_workload_manifest(manifest_path)
    assert manifest["version"] == 2
    assert manifest["required_valid_runs_per_envelope"] == 3


def test_http_policy_allows_only_read_evidence_paths() -> None:
    validate_local_request(
        "GET",
        "http://127.0.0.1:8200/api/v1/host-resources/summary?allow_stale=true",
    )
    with pytest.raises(ValueError):
        validate_local_request(
            "POST",
            "http://127.0.0.1:8200/api/v1/playbooks/execute/start?"
            "playbook_code=ig_analyze_following&execution_backend=runner",
        )


@pytest.mark.parametrize(
    ("method", "url"),
    [
        ("POST", "http://127.0.0.1:8200/api/v1/workspaces/x/tasks/y/resume"),
        ("DELETE", "http://127.0.0.1:8200/api/v1/playbooks/execute/start"),
        ("POST", "http://127.0.0.1:8220/api/v1/playbooks/execute/start"),
        ("POST", "https://example.com/api/v1/playbooks/execute/start"),
        (
            "POST",
            "http://127.0.0.1:8200/api/v1/playbooks/execute/start?"
            "playbook_code=unknown&execution_backend=runner",
        ),
    ],
)
def test_http_policy_rejects_every_other_mutation(method: str, url: str) -> None:
    with pytest.raises(ValueError):
        validate_local_request(method, url)


def test_evidence_rows_are_hash_bound() -> None:
    first = evidence_row({"kind": "node", "value": 1})
    second = evidence_row({"kind": "node", "value": 2})
    assert len(first["evidence_sha256"]) == 64
    assert first["evidence_sha256"] != second["evidence_sha256"]


def test_reconciliation_evidence_derives_rounded_exact_cgroup_peak(
    tmp_path: Path,
) -> None:
    task_id = "task-1"
    container = "runner-browser"
    rows = [
        evidence_row(
            {
                "kind": "natural_claim_observed",
                "classification": {
                    "valid": True,
                    "envelope_id": "ig_analyze_following",
                },
                "task": {"id": task_id, "runner_id": "runner-1"},
            }
        )
    ]
    for epoch, peak in ((0.0, 100), (5.0, 65 * 1024 * 1024), (10.0, 70)):
        rows.append(
            evidence_row(
                {
                    "kind": "workload_node",
                    "task_id": task_id,
                    "envelope_id": "ig_analyze_following",
                    "captured_at_epoch": epoch,
                    "browser_cgroups": [
                        {
                            "container": container,
                            "memory_peak_bytes": peak,
                            "oom_kill": 0,
                            "oom_group_kill": 0,
                        }
                    ],
                }
            )
        )
    rows.append(
        evidence_row(
            {
                "kind": "workload_pool",
                "task_id": task_id,
                "envelope_id": "ig_analyze_following",
                "captured_at_epoch": 5.0,
                "task": {"id": task_id, "status": "running"},
                "failures": [],
                "postgres": "f|off",
                "pgbouncer_pools": [{"cl_waiting": 0, "maxwait": 0}],
            }
        )
    )
    path = tmp_path / "workload.jsonl"
    path.write_text(
        "".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
    )

    result = validate_reconciliation_evidence(
        path,
        task_id=task_id,
        runner_container=container,
        minimum_samples=3,
        minimum_duration_seconds=10,
    )
    assert result.observed_cgroup_peak_bytes == 65 * 1024 * 1024
    assert result.request_bytes == 128 * 1024 * 1024

    path.write_text(path.read_text().replace('"oom_kill":0', '"oom_kill":1', 1))
    with pytest.raises(ValueError, match="evidence_hash_mismatch"):
        validate_reconciliation_evidence(
            path,
            task_id=task_id,
            runner_container=container,
            minimum_samples=3,
            minimum_duration_seconds=10,
        )


def test_task_memory_series_derives_startup_steady_and_settle() -> None:
    samples = [
        {"captured_at_epoch": epoch, "browser_container_working_set_bytes": value}
        for epoch, value in ((0, 100), (5, 500), (10, 300), (15, 250), (20, 260), (25, 240))
    ]
    summary = summarize_task_memory_series(samples, browser_idle_peak_bytes=100)
    assert summary["startup_peak_bytes"] == 400
    assert summary["steady_peak_bytes"] == 160
    assert summary["startup_settle_seconds"] == 15


def test_node_cadence_rejects_collect_then_sleep_drift() -> None:
    passing = summarize_node_cadence(
        [{"captured_at_epoch": value} for value in (0, 5, 10.5, 15.5)]
    )
    blocked = summarize_node_cadence(
        [{"captured_at_epoch": value} for value in (0, 7, 14, 21)]
    )
    assert passing["status"] == "pass"
    assert blocked["failure"] == "node_cadence_violation"


def test_natural_claim_selection_and_live_owner_are_exact() -> None:
    task = {"id": "task", "runner_id": "runner", "started_at_epoch": 11}
    assert select_fresh_running_task([task], observer_started_epoch=10) == task
    assert select_fresh_running_task([task], observer_started_epoch=12) is None
    assert validate_live_owner(
        task,
        {"task_id": "task", "runner_id": "runner", "ttl_seconds_remaining": 30},
    ) == []
    with pytest.raises(NaturalClaimObservationError):
        select_fresh_running_task(
            [task, {**task, "id": "task-2"}],
            observer_started_epoch=10,
        )


def test_natural_claim_discovery_uses_live_owner_then_one_exact_task_read() -> None:
    task_id = "11111111-1111-1111-1111-111111111111"

    class Collector:
        db_scans = 0
        exact_reads = 0

        def list_live_browser_owners(self):
            return [{"task_id": task_id, "runner_id": "runner-1"}]

        def collect_running_browser_task(self, observed_task_id):
            self.exact_reads += 1
            assert observed_task_id == task_id
            return {
                "id": task_id,
                "pack_id": "ig_analyze_following",
                "status": "running",
                "queue_shard": "browser_local",
                "runner_id": "runner-1",
                "started_at_epoch": 20,
                "execution_context": {
                    "inputs": {"user_data_dir": "/profile"},
                    "resource_requirements": {
                        "ig_profile_lock": "{user_data_dir}"
                    },
                },
            }

        def read_live_owner(self, observed_task_id):
            assert observed_task_id == task_id
            return {
                "task_id": task_id,
                "runner_id": "runner-1",
                "ttl_seconds_remaining": 60,
            }

        def list_running_browser_tasks_started_after(self, _epoch):
            self.db_scans += 1
            raise AssertionError("per-second DB scan is forbidden")

    collector = Collector()
    observed = wait_for_natural_claim(
        collector,
        observer_started_epoch=10,
        timeout_seconds=1,
        poll_interval_seconds=0.01,
    )
    assert observed["task"]["id"] == task_id
    assert observed["classification"]["valid"] is True
    assert collector.exact_reads == 1
    assert collector.db_scans == 0


def test_envelope_classifier_enforces_partition_and_lock_contracts() -> None:
    captured = classify_task_envelope(
        {
            "pack_id": "ig_batch_pin_references",
            "queue_shard": "default_local_browser",
            "concurrency_key": "concurrency:ig_batch_pin_target:workspace:target",
            "execution_context": {
                "inputs": {"source_mode": "captured_posts", "target_handle": "target"},
                "resource_requirements": {"ig_profile_lock": False},
            },
        }
    )
    assert captured["valid"] is True
    assert captured["envelope_id"] == "ig_batch_pin_references.captured_posts"

    invalid = classify_task_envelope(
        {
            "pack_id": "ig_analyze_following",
            "queue_shard": "default_local_browser",
            "execution_context": {
                "inputs": {"user_data_dir": "/profile"},
                "resource_requirements": {"ig_profile_lock": "{user_data_dir}"},
            },
        }
    )
    assert invalid["valid"] is False
    assert invalid["failures"] == ["browser_local_partition_mismatch"]


def test_envelope_classifier_reads_admitted_profile_lock_contract() -> None:
    following = classify_task_envelope(
        {
            "pack_id": "ig_analyze_following",
            "queue_shard": "browser_local",
            "concurrency_key": "concurrency:playbook_input:ig_analyze_following:/profile",
            "execution_context": {
                "inputs": {"user_data_dir": "/profile"},
                "resource_admission": {
                    "requirements": {"ig_profile_lock": "/profile"},
                },
            },
        }
    )

    assert following["valid"] is True
    assert following["envelope_id"] == "ig_analyze_following"


def test_quota_state_counts_valid_envelopes_and_partition_limits() -> None:
    manifest = {
        "required_valid_runs_per_envelope": 3,
        "max_browser_local_runs": 24,
        "max_captured_post_runs": 3,
    }
    runs = [
        {
            "envelope_id": "ig_batch_pin_references.captured_posts",
            "partition": "default_local_browser",
            "valid": False,
        }
        for _ in range(3)
    ]
    state = quota_state(runs, manifest)
    assert state["complete"] is False
    assert state["failures"] == ["captured_post_run_limit_reached"]
