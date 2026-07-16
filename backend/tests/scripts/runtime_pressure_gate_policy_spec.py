from scripts.maintenance import runtime_pressure_gate
from scripts.maintenance.runtime_pressure_gate import (
    Thresholds,
    collect_task_status_counts,
    evaluate_gate,
)
from scripts.maintenance.runtime_pressure_gate_core.database import (
    collect_pgbouncer_metrics,
)


def _healthy():
    return {
        "task_status": {"ok": True, "counts": {"running": 0, "pending": 0}},
        "docker_stats": {"ok": True, "rows": []},
        "endpoint_checks": {"healthz": {"ok": True, "elapsed_seconds": 0.1}},
        "thresholds": Thresholds(0, 1000, 200.0, 400.0, 5.0),
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
        "runner_capacity": {"ok": True, "aggregate_max_inflight": 7},
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
        max_running=0,
        max_pending=1000,
    )

    sql = captured["command"][-1]
    assert "status = 'running' limit 1" in sql
    assert "status = 'pending' limit 1001" in sql
    assert result["counts"] == {"pending": 1001, "running": 1}
