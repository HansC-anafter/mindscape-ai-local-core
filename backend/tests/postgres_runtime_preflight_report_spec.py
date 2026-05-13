from backend.scripts.postgres_runtime_preflight_report import evaluate_report


def _base_report():
    return {
        "database": {
            "pg_is_in_recovery": False,
            "shared_preload_libraries": "pg_stat_statements",
            "max_connections": "100",
        },
        "extensions": {
            "installed": ["pg_repack", "pg_stat_statements"],
        },
        "tools": {
            "pg_repack_binary": "/usr/bin/pg_repack",
        },
        "script_paths": {
            "backup_job": {"exists": True},
            "backup_verify": {"exists": True},
            "legacy_compaction": {"exists": True},
            "retention_prune": {"exists": True},
        },
        "activity": {
            "idle_in_transaction": 0,
        },
        "hot_row_budget": {
            "sample": {
                "execution_context_over_budget": 0,
                "result_over_budget": 0,
                "params_over_budget": 0,
            }
        },
        "pg_stat_statements_top": [{"queryid": 1, "calls": 10}],
    }


def test_preflight_report_is_ready_when_all_gates_pass():
    report = evaluate_report(_base_report())

    assert report["readiness"]["ready_for_physical_reclaim"] is True
    assert report["readiness"]["blockers"] == []


def test_preflight_report_blocks_missing_reclaim_and_observability_support():
    raw = _base_report()
    raw["extensions"]["installed"] = []
    raw["tools"]["pg_repack_binary"] = None
    raw["database"]["shared_preload_libraries"] = ""
    raw["pg_stat_statements_top"] = []

    report = evaluate_report(raw)

    assert report["readiness"]["ready_for_physical_reclaim"] is False
    assert "pg_repack_extension_missing" in report["readiness"]["blockers"]
    assert "pg_repack_binary_missing" in report["readiness"]["blockers"]
    assert "pg_stat_statements_extension_missing" in report["readiness"]["blockers"]
    assert "pg_stat_statements_not_preloaded" in report["readiness"]["blockers"]
    assert "pg_stat_statements_top_sql_unavailable" in report["readiness"]["warnings"]


def test_preflight_report_blocks_hot_rows_and_open_transactions():
    raw = _base_report()
    raw["activity"]["idle_in_transaction"] = 1
    raw["hot_row_budget"]["sample"]["result_over_budget"] = 2

    report = evaluate_report(raw)

    assert report["readiness"]["ready_for_physical_reclaim"] is False
    assert "idle_in_transaction_sessions_present" in report["readiness"]["blockers"]
    assert "recent_hot_rows_over_budget" in report["readiness"]["blockers"]
