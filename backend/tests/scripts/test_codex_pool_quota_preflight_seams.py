from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_DIR = REPO_ROOT / "scripts" / "e2e"
FACADE_PATH = SCRIPT_DIR / "codex_pool_quota_preflight.py"
SOURCE_PATHS = [
    FACADE_PATH,
    SCRIPT_DIR / "codex_pool_quota_preflight_env.py",
    SCRIPT_DIR / "codex_pool_quota_preflight_runtime.py",
    SCRIPT_DIR / "codex_pool_quota_preflight_runner.py",
    SCRIPT_DIR / "codex_pool_quota_preflight_output.py",
]


def _load_facade():
    spec = importlib.util.spec_from_file_location(
        "mindscape_codex_pool_quota_preflight_seam_test",
        FACADE_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_facade_preserves_callable_contract():
    module = _load_facade()

    assert callable(module.run_preflight)
    assert callable(module.run_account_home_audit)
    assert callable(module.parse_args)
    assert callable(module._compact_result)
    assert callable(module.main)


def test_parser_defaults_are_preserved(monkeypatch):
    module = _load_facade()
    monkeypatch.setattr(
        sys,
        "argv",
        ["codex_pool_quota_preflight.py", "--workspace-id", "ws-test"],
    )

    args = module.parse_args()

    assert args.workspace_id == "ws-test"
    assert args.max_runtime_probes == 8
    assert args.timeout_seconds == 90.0
    assert args.stall_timeout_seconds == 30.0
    assert args.required_login_email == ""
    assert args.exclude_runtime_id == []
    assert args.target_successes == 1
    assert args.continue_after_success is False
    assert args.audit_all_account_homes is False
    assert args.compact_output is False


def test_host_reachable_database_url_rewrites_only_postgres_host(monkeypatch):
    module = _load_facade()
    raw = "postgresql://mindscape:secret@postgres:5432/mindscape?sslmode=disable"

    monkeypatch.delenv("PD_E2E_USE_DOCKER_NETWORK_DB_HOST", raising=False)
    monkeypatch.delenv("PD_E2E_POSTGRES_HOST_PORT", raising=False)

    assert (
        module._host_reachable_database_url(raw)
        == "postgresql://mindscape:secret@localhost:5433/mindscape?sslmode=disable"
    )
    assert (
        module._host_reachable_database_url("postgresql://u:p@127.0.0.1:5432/db")
        == "postgresql://u:p@127.0.0.1:5432/db"
    )

    monkeypatch.setenv("PD_E2E_USE_DOCKER_NETWORK_DB_HOST", "true")
    assert module._host_reachable_database_url(raw) == raw


def test_compact_result_preserves_aggregate_fields_and_truncates_attempts():
    module = _load_facade()
    result = {
        "status": "failed",
        "workspace_id": "ws-test",
        "target_successes": 2,
        "successful_runtime_count": 1,
        "successful_quota_scope_count": 1,
        "successful_runtime_ids": ["rt-ok"],
        "successful_quota_scope_keys": ["account:ok"],
        "codex_cli_binary": "/usr/local/bin/codex",
        "codex_cli_version": "0.40.0",
        "minimum_supported_codex_cli_version": "0.39.0",
        "required_flags_supported": {"--output-last-message": True},
        "codex_cli_compatible": True,
        "runtime_pool_summary": {
            "pool_enabled_runtime_count": 4,
            "runnable_runtime_count": 3,
            "probe_available_runtime_count": 2,
            "active_cooldown_count": 1,
            "probe_state_counts": {"available": 2},
            "failure_counts": {"quota_exceeded": 1},
            "next_cooldown_until": "2026-06-21T00:00:00Z",
        },
        "attempts": [
            {
                "attempt": 1,
                "status": "failed",
                "selected_runtime_id": "rt-1",
                "runtime_account_identity": {
                    "login_email": "codex@example.com",
                    "account_key": "ak-1",
                },
                "quota_scope_key": "account:ak-1",
                "counted_quota_scope_key": "account:ak-1",
                "fault_kind": "quota",
                "error_code": "quota_exceeded",
                "probe": {
                    "success": False,
                    "returncode": 1,
                    "error": "e" * 400,
                    "output": "o" * 250,
                },
            }
        ],
    }

    compact = module._compact_result(result)

    assert compact["status"] == "failed"
    assert compact["workspace_id"] == "ws-test"
    assert compact["successful_runtime_ids"] == ["rt-ok"]
    assert compact["attempt_count"] == 1
    assert compact["failure_counts"] == {"quota_exceeded": 1}
    assert compact["pool_summary"]["runnable_runtime_count"] == 3
    attempt = compact["attempts"][0]
    assert attempt["runtime_id"] == "rt-1"
    assert attempt["login_email"] == "codex@example.com"
    assert attempt["error_code"] == "quota_exceeded"
    assert len(attempt["probe_error"]) == 300
    assert len(attempt["probe_output"]) == 200


def test_source_split_does_not_add_parallel_resource_paths():
    source_by_name = {path.name: path.read_text(encoding="utf-8") for path in SOURCE_PATHS}
    combined = "\n".join(source_by_name.values())

    assert combined.count("def main(") == 1
    assert combined.count('if __name__ == "__main__"') == 1
    assert source_by_name["codex_pool_quota_preflight_env.py"].count("subprocess.run(") == 2
    assert all(
        "subprocess.run(" not in source
        for name, source in source_by_name.items()
        if name != "codex_pool_quota_preflight_env.py"
    )
    assert source_by_name["codex_pool_quota_preflight_runtime.py"].count("_get_db()") == 1
    assert source_by_name["codex_pool_quota_preflight_runtime.py"].count("db.close()") == 1
    assert all(
        "_get_db()" not in source and "db.close()" not in source
        for name, source in source_by_name.items()
        if name != "codex_pool_quota_preflight_runtime.py"
    )
    assert (
        source_by_name["codex_pool_quota_preflight_runtime.py"].count(
            "run_codex_cli_subprocess"
        )
        == 2
    )
    assert all(
        "run_codex_cli_subprocess" not in source
        for name, source in source_by_name.items()
        if name != "codex_pool_quota_preflight_runtime.py"
    )
    assert "APIRouter" not in combined
    assert "@router" not in combined
    assert "Thread(" not in combined
    assert "Process(" not in combined
    assert "setInterval" not in combined
    assert "pgbouncer" not in combined.lower()
