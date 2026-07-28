from scripts.maintenance import runtime_pressure_gate
from scripts.maintenance.runtime_pressure_gate import (
    Thresholds,
    collect_task_status_counts,
    evaluate_gate,
    resolve_runtime_stat_containers,
)
from scripts.maintenance.runtime_pressure_gate_core.database import (
    collect_pgbouncer_metrics,
)
from scripts.maintenance.runtime_pressure_gate_core.runners import (
    collect_runner_capacity,
)


def _healthy():
    return {
        "task_status": {
            "ok": True,
            "counts": {"running": 3, "pending": 1001},
            "gate_semantics": "observational_only",
        },
        "docker_stats": {"ok": True, "rows": []},
        "endpoint_checks": {"healthz": {"ok": True, "elapsed_seconds": 0.1}},
        "thresholds": Thresholds(
            running_observation_limit=100,
            pending_observation_limit=1000,
            max_postgres_cpu=200.0,
            max_runner_cpu_ratio=0.90,
            runner_cpu_sample_count=5,
            runner_cpu_sustained_sample_count=3,
            runner_cpu_sample_interval_seconds=2.0,
            max_endpoint_seconds=5.0,
        ),
        "postgres_metrics": {
            "ok": True,
            "metrics": {
                "in_recovery": False,
                "read_only": "off",
                "invalid_indexes": 0,
                "failed_count": 0,
            },
        },
        "pgbouncer_metrics": {
            "ok": True,
            "sample_count": 3,
            "rows": [{"cl_waiting": 0, "maxwait": 0, "maxwait_us": 0}],
        },
        "runner_capacity": {
            "ok": True,
            "aggregate_max_inflight": 7,
            "rows": [
                {
                    "container": "runner-browser",
                    "max_inflight": 2,
                    "profile": "browser_local",
                    "accepted_partitions": "browser_local",
                    "accepted_resource_classes": "browser",
                },
                {
                    "container": "runner-browser-extra",
                    "max_inflight": 2,
                    "profile": "browser_local",
                    "accepted_partitions": "browser_local",
                    "accepted_resource_classes": "browser",
                },
                {
                    "container": "runner-default-browser",
                    "max_inflight": 2,
                    "profile": "default_local_browser",
                    "accepted_partitions": "default_local_browser",
                    "accepted_resource_classes": "browser",
                },
                {
                    "container": "runner-vision",
                    "max_inflight": 1,
                    "profile": "vision_local",
                    "accepted_partitions": "vision_local",
                    "accepted_resource_classes": "compute",
                },
            ],
        },
        "runner_cpu_pressure": {
            "collection_ok": True,
            "ok": True,
            "failures": [],
        },
    }


def test_runtime_gate_preserves_capacity_and_fails_pool_wait():
    evidence = _healthy()
    assert evaluate_gate(**evidence) == []
    evidence["pgbouncer_metrics"]["rows"][0]["maxwait_us"] = 1
    assert "pgbouncer_client_maxwait" in evaluate_gate(**evidence)


def test_runtime_gate_fails_closed_when_metrics_are_unavailable():
    evidence = _healthy()
    evidence["postgres_metrics"] = {"ok": False}
    evidence["runner_capacity"] = {"ok": False}
    failures = evaluate_gate(**evidence)
    assert "postgres_metrics_unavailable" in failures
    assert "runner_capacity_unavailable" in failures


def test_runtime_gate_does_not_require_global_task_zero():
    evidence = _healthy()
    evidence["task_status"]["counts"] = {"running": 101, "pending": 1001}

    assert evaluate_gate(**evidence) == []


def test_runtime_gate_does_not_apply_legacy_raw_runner_cpu_threshold():
    evidence = _healthy()
    evidence["docker_stats"]["rows"] = [
        {
            "Name": "mindscape-ai-local-core-runner-browser-extra",
            "cpu_percent_value": 944.29,
        }
    ]

    assert evaluate_gate(**evidence) == []


def test_runtime_gate_fails_closed_when_runner_cpu_samples_are_unavailable():
    evidence = _healthy()
    evidence["runner_cpu_pressure"] = {
        "collection_ok": False,
        "error_code": "docker_ncpu_unavailable",
    }

    assert (
        "runner_cpu_pressure_unavailable:docker_ncpu_unavailable"
        in evaluate_gate(**evidence)
    )


def test_runtime_gate_rejects_degraded_protected_capacity_below_seven():
    evidence = _healthy()
    evidence["runner_capacity"]["aggregate_max_inflight"] = 6
    evidence["runner_capacity"]["rows"][-1]["max_inflight"] = 0

    assert "protected_runner_capacity_below_7" in evaluate_gate(**evidence)


def test_intent_bound_capacity_cannot_mask_a_degraded_protected_lane():
    evidence = _healthy()
    evidence["runner_capacity"]["aggregate_max_inflight"] = 7
    evidence["runner_capacity"]["rows"] = [
        row
        for row in evidence["runner_capacity"]["rows"]
        if row["container"] != "runner-browser-extra"
    ]
    evidence["runner_capacity"]["rows"].append(
        {
            "container": "runner-vision-mlx-dev",
            "max_inflight": 2,
            "profile": "vision_mlx_dev",
            "accepted_partitions": "vision_mlx_dev",
            "accepted_resource_classes": "compute",
        }
    )

    assert (
        "protected_lane_capacity_below_browser_local_4"
        in evaluate_gate(**evidence)
    )


def test_runner_rolling_gate_requires_target_and_compatible_peer():
    evidence = _healthy()
    evidence["scope"] = runtime_pressure_gate.GateScope(
        action="runner-rolling-reload",
        target_runner_container="runner-browser-extra",
    )

    assert evaluate_gate(**evidence) == []


def test_runner_rolling_gate_requires_explicit_sole_owner_flag():
    evidence = _healthy()
    evidence["scope"] = runtime_pressure_gate.GateScope(
        action="runner-rolling-reload",
        target_runner_container="runner-default-browser",
    )

    assert (
        "target_runner_sole_owner_requires_explicit_flag"
        in evaluate_gate(**evidence)
    )
    evidence["scope"] = runtime_pressure_gate.GateScope(
        action="runner-rolling-reload",
        target_runner_container="runner-default-browser",
        allow_sole_owner_target=True,
    )
    assert evaluate_gate(**evidence) == []


def test_runner_capacity_reads_only_allowlisted_environment_keys():
    commands = []
    values = {
        ("runner-browser", "LOCAL_CORE_RUNNER_MAX_INFLIGHT"): "2\n",
        ("runner-browser", "LOCAL_CORE_RUNNER_PROFILE"): "browser_local\n",
        (
            "runner-browser",
            "LOCAL_CORE_RUNNER_ACCEPTED_PARTITIONS",
        ): "browser_local\n",
        (
            "runner-browser",
            "LOCAL_CORE_RUNNER_ACCEPTED_RESOURCE_CLASSES",
        ): "browser\n",
    }

    def _run(command, _timeout_seconds):
        commands.append(command)
        if command[:2] == ["docker", "ps"]:
            return {"ok": True, "stdout": "runner-browser\n"}
        key = (command[2], command[4])
        return {"ok": key in values, "stdout": values.get(key, "")}

    result = collect_runner_capacity(_run, 5.0)

    assert result == {
        "ok": True,
        "aggregate_max_inflight": 2,
        "rows": [
            {
                "container": "runner-browser",
                "max_inflight": 2,
                "profile": "browser_local",
                "accepted_partitions": "browser_local",
                "accepted_resource_classes": "browser",
            }
        ],
    }
    assert all(command[:2] != ["docker", "inspect"] for command in commands)
    assert all(
        command[:2] == ["docker", "ps"]
        or (
            command[:2] == ["docker", "exec"]
            and command[3] == "printenv"
            and command[4]
            in {
                "LOCAL_CORE_RUNNER_MAX_INFLIGHT",
                "LOCAL_CORE_RUNNER_PROFILE",
                "LOCAL_CORE_RUNNER_ACCEPTED_PARTITIONS",
                "LOCAL_CORE_RUNNER_ACCEPTED_RESOURCE_CLASSES",
            }
        )
        for command in commands
    )


def test_runner_capacity_fails_closed_when_lane_identity_is_missing():
    def _run(command, _timeout_seconds):
        if command[:2] == ["docker", "ps"]:
            return {"ok": True, "stdout": "runner-browser\n"}
        if command[4] == "LOCAL_CORE_RUNNER_MAX_INFLIGHT":
            return {"ok": True, "stdout": "2\n"}
        return {"ok": False, "stdout": ""}

    assert collect_runner_capacity(_run, 5.0) == {
        "ok": False,
        "error_code": "runner_lane_identity_missing",
    }


def test_pgbouncer_metrics_are_mapped_by_header_not_position():
    stdout = "\n".join(
        [
            "database,user,cl_active,cl_waiting,cl_active_cancel_req,cl_waiting_cancel_req,sv_active,sv_active_cancel,sv_being_canceled,sv_idle,sv_used,sv_tested,sv_login,maxwait,maxwait_us,pool_mode,load_balance_hosts",
            "mindscape_core,mindscape,26,2,0,0,3,0,0,4,5,0,6,7,8,transaction,",
        ]
    )

    metrics = collect_pgbouncer_metrics(
        lambda _command, _timeout: {"ok": True, "stdout": stdout},
        5.0,
    )

    assert metrics == {
        "ok": True,
        "rows": [
            {
                "database": "mindscape_core",
                "sample_index": 1,
                "cl_active": 26,
                "cl_waiting": 2,
                "sv_active": 3,
                "sv_idle": 4,
                "sv_used": 5,
                "sv_login": 6,
                "maxwait": 7,
                "maxwait_us": 8,
            }
        ],
        "sample_count": 1,
        "sample_interval_seconds": 0.0,
    }


def test_pgbouncer_metrics_fail_closed_when_show_pools_schema_changes():
    metrics = collect_pgbouncer_metrics(
        lambda _command, _timeout: {
            "ok": True,
            "stdout": "database,cl_active\nmindscape_core,1\n",
        },
        5.0,
    )

    assert metrics == {
        "ok": False,
        "error_code": "pgbouncer_metrics_schema_invalid",
        "sample_count": 0,
    }


def test_runtime_gate_requires_three_pool_samples_for_release():
    evidence = _healthy()
    evidence["pgbouncer_metrics"]["sample_count"] = 1

    assert "pgbouncer_three_samples_required" in evaluate_gate(**evidence)


def test_task_backlog_probe_is_threshold_bounded(monkeypatch):
    captured = {}

    def _run(command, timeout_seconds):
        captured["command"] = command
        captured["timeout_seconds"] = timeout_seconds
        return {
            "ok": True,
            "stdout": "pending,1001\nrunning,1\n",
            "stderr": "",
            "elapsed_seconds": 0.01,
        }

    monkeypatch.setattr(runtime_pressure_gate, "run_command", _run)

    result = collect_task_status_counts(
        8.0,
        running_observation_limit=0,
        pending_observation_limit=1000,
    )

    sql = captured["command"][-1]
    assert "status = 'running' limit 1" in sql
    assert "status = 'pending'" in sql
    assert "task_type in ('playbook_execution', 'tool_execution')" in sql
    assert "frontier_state = 'ready'" in sql
    assert "(blocked_reason is null or blocked_reason = '')" in sql
    assert "limit 1001" in sql
    assert result["counts"] == {"pending": 1001, "running": 1}
    assert result["gate_semantics"] == "observational_only"
    assert result["pending_semantics"] == "ready_unblocked_execution_frontier"


def test_task_backlog_probe_does_not_count_cold_or_blocked_pending_rows(monkeypatch):
    captured = {}

    def _run(command, timeout_seconds):
        captured["sql"] = command[-1]
        return {
            "ok": True,
            "stdout": "pending,17\nrunning,0\n",
            "stderr": "",
            "elapsed_seconds": 0.01,
        }

    monkeypatch.setattr(runtime_pressure_gate, "run_command", _run)

    result = collect_task_status_counts(
        8.0,
        running_observation_limit=0,
        pending_observation_limit=1000,
    )

    assert "frontier_state = 'ready'" in captured["sql"]
    assert "blocked_reason is null" in captured["sql"]
    assert result["counts"]["pending"] == 17


def test_runtime_stats_cover_every_discovered_runner():
    containers = resolve_runtime_stat_containers(
        {
            "ok": True,
            "rows": [
                {"container": "mindscape-ai-local-core-runner-vision"},
                {"container": "mindscape-ai-local-core-runner-browser-extra"},
                {"container": "mindscape-ai-local-core-runner-browser"},
            ],
        }
    )

    assert containers[:3] == [
        "mindscape-ai-local-core-backend",
        "mindscape-ai-local-core-postgres",
        "mindscape-ai-local-core-pgbouncer",
    ]
    assert containers[3:] == [
        "mindscape-ai-local-core-runner-browser",
        "mindscape-ai-local-core-runner-browser-extra",
        "mindscape-ai-local-core-runner-vision",
    ]
