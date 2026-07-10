from __future__ import annotations

import json

import pytest

from scripts.maintenance.browser_resource_calibration_core.evidence import evidence_row
from scripts.maintenance.browser_resource_calibration_core.http_client import (
    validate_local_request,
)
from scripts.maintenance.browser_resource_calibration_core.parsing import (
    build_node_sample,
    parse_size_bytes,
    round_request_bytes,
    summarize_baseline,
    summarize_workload_runs,
)
from scripts.maintenance.browser_resource_calibration_core.workloads import (
    build_run_sequence,
    build_start_request,
    load_workload_manifest,
)


GIB = 1024 * 1024 * 1024


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
            "vm_overhead_bytes": 10,
            "non_browser_container_working_set_bytes": 20,
            "browser_container_working_set_bytes": 30,
            "mem_available_bytes": 100,
        },
        {
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
    assert round_request_bytes(65 * 1024 * 1024) == 128 * 1024 * 1024

    runs = [
        {
            "workload_code": "ig_pin_post_detail",
            "valid": True,
            "task_peak_bytes": peak,
            "payload_sha256": "same",
        }
        for peak in (65 * 1024 * 1024, 70 * 1024 * 1024, 80 * 1024 * 1024)
    ]
    summary = summarize_workload_runs(runs)
    assert summary["status"] == "pass"
    assert summary["workloads"][0]["request_bytes"] == 128 * 1024 * 1024


def test_workload_summary_fails_without_three_valid_runs() -> None:
    summary = summarize_workload_runs(
        [
            {
                "workload_code": "ig_analyze_following",
                "valid": True,
                "task_peak_bytes": GIB,
            }
        ]
    )
    assert summary["status"] == "blocked"
    assert summary["failures"] == ["ig_analyze_following:valid_runs=1"]


def test_workload_summary_rejects_payload_hash_drift() -> None:
    summary = summarize_workload_runs(
        [
            {
                "workload_code": "ig_analyze_following",
                "valid": True,
                "task_peak_bytes": GIB,
                "payload_sha256": value,
            }
            for value in ("one", "one", "two")
        ]
    )
    assert summary["status"] == "blocked"
    assert summary["failures"] == ["ig_analyze_following:payload_hash_drift"]


def test_manifest_requires_three_workloads_and_builds_nine_runs(tmp_path) -> None:
    baseline = tmp_path / "baseline.json"
    baseline.write_text("{}", encoding="utf-8")
    manifest_path = tmp_path / "manifest.json"
    workloads = [
        {"workload_code": code, "inputs": {"workspace_id": "workspace", "x": code}}
        for code in (
            "ig_analyze_following",
            "ig_batch_pin_references",
            "ig_pin_post_detail",
        )
    ]
    manifest_path.write_text(
        json.dumps(
            {
                "version": 1,
                "workspace_id": "workspace",
                "baseline_summary_path": str(baseline),
                "workloads": workloads,
            }
        ),
        encoding="utf-8",
    )
    manifest = load_workload_manifest(manifest_path)
    sequence = build_run_sequence(manifest, 3)

    assert len(sequence) == 9
    assert [row["repetition"] for row in sequence[:3]] == [1, 2, 3]
    assert len(sequence[0]["payload_sha256"]) == 64


def test_start_request_uses_only_canonical_runner_api() -> None:
    workload = {
        "workload_code": "ig_analyze_following",
        "inputs": {"workspace_id": "workspace"},
    }
    url, payload = build_start_request(
        api_base="http://127.0.0.1:8200",
        workspace_id="workspace",
        profile_id="profile",
        workload=workload,
    )
    validate_local_request("POST", url)
    assert payload["execution_backend"] == "runner"


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
