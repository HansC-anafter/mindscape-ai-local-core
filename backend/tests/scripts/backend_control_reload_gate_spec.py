from pathlib import Path

from scripts.maintenance import backend_control_reload_gate


def _healthy_postgres():
    return {
        "ok": True,
        "metrics": {
            "in_recovery": False,
            "read_only": "off",
            "invalid_indexes": 0,
            "failed_count": 0,
        },
    }


def _healthy_pgbouncer():
    return {
        "ok": True,
        "sample_count": 3,
        "rows": [
            {
                "database": "mindscape_core",
                "cl_waiting": 0,
                "maxwait": 0,
                "maxwait_us": 0,
            },
            {
                "database": "mindscape_vectors",
                "cl_waiting": 0,
                "maxwait": 0,
                "maxwait_us": 0,
            },
        ],
    }


def _healthy_endpoints():
    return {
        "backend_control": {"ok": True, "status": 200},
        "execution_backend": {"ok": True, "status": 200},
    }


def test_control_only_reload_ignores_execution_task_frontier():
    failures = backend_control_reload_gate.evaluate_backend_control_reload_gate(
        control_plane_state={
            "ok": True,
            "state": {
                "active_install_jobs": 0,
                "incomplete_commit_receipts": 0,
                "database_lock_waits": 0,
            },
        },
        endpoint_checks=_healthy_endpoints(),
        postgres_metrics=_healthy_postgres(),
        pgbouncer_metrics=_healthy_pgbouncer(),
    )

    assert failures == []
    source = Path(backend_control_reload_gate.__file__).read_text(encoding="utf-8")
    assert "FROM tasks" not in source


def test_control_only_reload_blocks_active_install_or_incomplete_commit():
    failures = backend_control_reload_gate.evaluate_backend_control_reload_gate(
        control_plane_state={
            "ok": True,
            "state": {
                "active_install_jobs": 1,
                "incomplete_commit_receipts": 1,
                "database_lock_waits": 0,
            },
        },
        endpoint_checks=_healthy_endpoints(),
        postgres_metrics=_healthy_postgres(),
        pgbouncer_metrics=_healthy_pgbouncer(),
    )

    assert failures == [
        "active_install_jobs_present",
        "incomplete_commit_receipts_present",
    ]


def test_control_only_reload_blocks_db_or_pool_pressure():
    postgres = _healthy_postgres()
    postgres["metrics"]["read_only"] = "on"
    pgbouncer = _healthy_pgbouncer()
    pgbouncer["rows"][0]["cl_waiting"] = 1

    failures = backend_control_reload_gate.evaluate_backend_control_reload_gate(
        control_plane_state={
            "ok": True,
            "state": {
                "active_install_jobs": 0,
                "incomplete_commit_receipts": 0,
                "database_lock_waits": 1,
            },
        },
        endpoint_checks=_healthy_endpoints(),
        postgres_metrics=postgres,
        pgbouncer_metrics=pgbouncer,
    )

    assert failures == [
        "database_lock_waits_present",
        "postgres_read_only",
        "pgbouncer_client_waiting",
    ]
