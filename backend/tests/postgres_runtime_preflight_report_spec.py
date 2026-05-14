import hashlib
import json
from types import SimpleNamespace

from backend.scripts.postgres_runtime_preflight_report import (
    _backup_verification,
    collect_report,
    evaluate_report,
)


def _base_report():
    return {
        "database": {
            "connectable": True,
            "pg_is_in_recovery": False,
            "shared_preload_libraries": "pg_stat_statements",
            "max_connections": "100",
            "wal_level": "replica",
            "archive_mode": "on",
            "archive_command": "test ! -f /archive/%f && cp %p /archive/%f",
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
        "backup_verification": {
            "source": "/tmp/backup",
            "source_available": True,
            "verified": True,
            "options": {
                "skip_db": False,
                "skip_files": False,
            },
            "artifact_count": 2,
            "errors": [],
        },
        "activity": {
            "idle_in_transaction": 0,
            "total_connections": 10,
        },
        "connection_budget": {
            "source_available": True,
            "configured_connection_budget": 62,
            "safe_connection_limit": 80,
            "active_connections": 10,
        },
        "runtime_readiness": {
            "source_available": True,
            "pgbouncer_service_defined": True,
            "backend_uses_pgbouncer": True,
            "runner_uses_pgbouncer": True,
            "read_replica_service_defined": True,
            "wal_archive_volume_configured": True,
            "redis_aof_configured": True,
            "redis_persistence_volume_configured": True,
        },
        "filesystem": {
            "source_available": True,
            "free_bytes": 20_000_000_000,
            "required_free_bytes": 12_000_000_000,
        },
        "runner_workload": {
            "running_tasks": 0,
            "runner_owned_running_tasks": 0,
            "ready_pending_tasks": 0,
        },
        "runner_claim_gate": {
            "state": "paused",
            "persisted": True,
            "source": "redis",
        },
        "hot_row_budget": {
            "sample": {
                "execution_context_over_budget": 0,
                "result_over_budget": 0,
                "params_over_budget": 0,
                "blocked_payload_over_budget": 0,
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


def test_preflight_report_requires_verified_backup():
    raw = _base_report()
    raw["backup_verification"] = {
        "source": None,
        "source_available": False,
        "verified": False,
        "errors": ["verified_backup_dir_required"],
    }

    report = evaluate_report(raw)

    assert report["readiness"]["ready_for_physical_reclaim"] is False
    assert "verified_backup_missing" in report["readiness"]["blockers"]


def test_preflight_report_blocks_invalid_backup_and_skip_db():
    raw = _base_report()
    raw["backup_verification"] = {
        "source": "/tmp/backup",
        "source_available": True,
        "verified": False,
        "errors": ["artifact_sha256_mismatch:postgres/core.dump"],
    }

    report = evaluate_report(raw)

    assert report["readiness"]["ready_for_physical_reclaim"] is False
    assert "verified_backup_invalid" in report["readiness"]["blockers"]

    raw = _base_report()
    raw["backup_verification"]["options"]["skip_db"] = True

    report = evaluate_report(raw)

    assert report["readiness"]["ready_for_physical_reclaim"] is False
    assert "verified_backup_skips_database" in report["readiness"]["blockers"]


def test_backup_verification_validates_manifest_artifacts(tmp_path):
    artifact = tmp_path / "postgres" / "core.dump"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"postgres dump")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    manifest = {
        "schema_version": "1.0",
        "backup_name": "runtime-backup",
        "created_at": "2026-05-14T00:00:00Z",
        "options": {
            "skip_db": False,
            "skip_files": False,
        },
        "artifacts": [
            {
                "path": "postgres/core.dump",
                "bytes": artifact.stat().st_size,
                "sha256": digest,
            }
        ],
    }
    (tmp_path / "manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )

    result = _backup_verification(tmp_path)

    assert result["verified"] is True
    assert result["artifact_count"] == 1
    assert result["errors"] == []
    assert result["artifacts"][0]["sha256_checked"] is True


def test_backup_verification_manifest_size_mode_skips_checksum_recompute(tmp_path):
    artifact = tmp_path / "archives" / "app-data.tar.gz"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"large backup placeholder")
    manifest = {
        "schema_version": "1.0",
        "backup_name": "runtime-backup",
        "created_at": "2026-05-14T00:00:00Z",
        "options": {
            "skip_db": False,
            "skip_files": False,
        },
        "artifacts": [
            {
                "path": "archives/app-data.tar.gz",
                "bytes": artifact.stat().st_size,
                "sha256": "preverified-digest",
            }
        ],
    }
    (tmp_path / "manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )

    result = _backup_verification(
        tmp_path,
        verification_mode="manifest_size",
    )
    report = evaluate_report({**_base_report(), "backup_verification": result})

    assert result["verified"] is True
    assert result["artifacts"][0]["sha256_checked"] is False
    assert "artifact_sha256_not_recomputed:archives/app-data.tar.gz" in result[
        "warnings"
    ]
    assert "verified_backup_checksum_not_recomputed" in report["readiness"][
        "warnings"
    ]


def test_collect_report_closes_database_connection_before_backup_verification(
    monkeypatch,
):
    closed = {"value": False}

    class _FakeConnectionContext:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, traceback):
            closed["value"] = True

    class _FakeEngine:
        def connect(self):
            return _FakeConnectionContext()

    def _checked_backup_verification(_backup_dir, **kwargs):
        assert closed["value"] is True
        return _base_report()["backup_verification"]

    monkeypatch.setattr(
        "backend.scripts.postgres_runtime_preflight_report._get_engine",
        lambda: _FakeEngine(),
    )
    monkeypatch.setattr(
        "backend.scripts.postgres_runtime_preflight_report._mapping_one",
        lambda conn, sql, params=None: {"value": False},
    )
    monkeypatch.setattr(
        "backend.scripts.postgres_runtime_preflight_report._show_setting",
        lambda conn, name: _base_report()["database"].get(name, ""),
    )
    monkeypatch.setattr(
        "backend.scripts.postgres_runtime_preflight_report._installed_extensions",
        lambda conn: {"pg_repack", "pg_stat_statements"},
    )
    monkeypatch.setattr(
        "backend.scripts.postgres_runtime_preflight_report._activity",
        lambda conn: _base_report()["activity"],
    )
    monkeypatch.setattr(
        "backend.scripts.postgres_runtime_preflight_report._relation_sizes",
        lambda conn, relations: [],
    )
    monkeypatch.setattr(
        "backend.scripts.postgres_runtime_preflight_report._runner_workload",
        lambda conn: _base_report()["runner_workload"],
    )
    monkeypatch.setattr(
        "backend.scripts.postgres_runtime_preflight_report._hot_row_budget",
        lambda conn, **kwargs: _base_report()["hot_row_budget"]["sample"],
    )
    monkeypatch.setattr(
        "backend.scripts.postgres_runtime_preflight_report._pg_stat_statements_top",
        lambda conn, **kwargs: _base_report()["pg_stat_statements_top"],
    )
    monkeypatch.setattr(
        "backend.scripts.postgres_runtime_preflight_report._pg_repack_tool_status",
        lambda compose_file: _base_report()["tools"],
    )
    monkeypatch.setattr(
        "backend.scripts.postgres_runtime_preflight_report._script_path_status",
        lambda: _base_report()["script_paths"],
    )
    monkeypatch.setattr(
        "backend.scripts.postgres_runtime_preflight_report._backup_verification",
        _checked_backup_verification,
    )
    monkeypatch.setattr(
        "backend.scripts.postgres_runtime_preflight_report._connection_budget",
        lambda **kwargs: _base_report()["connection_budget"],
    )
    monkeypatch.setattr(
        "backend.scripts.postgres_runtime_preflight_report._compose_runtime_readiness",
        lambda compose_file: _base_report()["runtime_readiness"],
    )
    monkeypatch.setattr(
        "backend.scripts.postgres_runtime_preflight_report._filesystem_capacity",
        lambda **kwargs: _base_report()["filesystem"],
    )
    monkeypatch.setattr(
        "backend.scripts.postgres_runtime_preflight_report._runner_claim_gate",
        lambda: _base_report()["runner_claim_gate"],
    )

    report = collect_report(
        SimpleNamespace(
            compose_file=None,
            verified_backup_dir=None,
            backup_verification_mode="manifest_checksum",
            connection_reserve=20,
            relation=None,
            postgres_data_path=None,
            repack_free_space_factor=1.2,
            repack_free_space_reserve=1024,
            recent_hours=24,
            execution_context_budget=16384,
            result_budget=16384,
            params_budget=16384,
            blocked_payload_budget=16384,
            statement_limit=5,
        )
    )

    assert closed["value"] is True
    assert report["readiness"]["ready_for_physical_reclaim"] is True


def test_preflight_report_blocks_hot_rows_and_open_transactions():
    raw = _base_report()
    raw["activity"]["idle_in_transaction"] = 1
    raw["hot_row_budget"]["sample"]["result_over_budget"] = 2
    raw["hot_row_budget"]["sample"]["blocked_payload_over_budget"] = 1

    report = evaluate_report(raw)

    assert report["readiness"]["ready_for_physical_reclaim"] is False
    assert "idle_in_transaction_sessions_present" in report["readiness"]["blockers"]
    assert "recent_hot_rows_over_budget" in report["readiness"]["blockers"]


def test_preflight_report_blocks_active_runner_workload():
    raw = _base_report()
    raw["runner_workload"]["running_tasks"] = 1
    raw["runner_workload"]["runner_owned_running_tasks"] = 1
    raw["runner_workload"]["ready_pending_tasks"] = 3

    report = evaluate_report(raw)

    assert report["readiness"]["ready_for_physical_reclaim"] is False
    assert "runner_workload_active" in report["readiness"]["blockers"]
    assert "ready_pending_tasks_present" in report["readiness"]["warnings"]


def test_preflight_report_requires_runner_claim_gate_pause():
    raw = _base_report()
    raw["runner_claim_gate"] = {
        "state": "open",
        "persisted": False,
        "source": "default",
    }

    report = evaluate_report(raw)

    assert report["readiness"]["ready_for_physical_reclaim"] is False
    assert "runner_claim_gate_not_paused" in report["readiness"]["blockers"]


def test_preflight_report_blocks_memory_only_runner_claim_gate_pause():
    raw = _base_report()
    raw["runner_claim_gate"] = {
        "state": "paused",
        "persisted": False,
        "source": "memory",
    }

    report = evaluate_report(raw)

    assert report["readiness"]["ready_for_physical_reclaim"] is False
    assert "runner_claim_gate_not_persisted" in report["readiness"]["blockers"]


def test_preflight_report_blocks_missing_ha_runtime_readiness():
    raw = _base_report()
    raw["database"]["archive_mode"] = "off"
    raw["database"]["archive_command"] = ""
    raw["runtime_readiness"] = {
        "source_available": True,
        "pgbouncer_service_defined": False,
        "backend_uses_pgbouncer": False,
        "runner_uses_pgbouncer": False,
        "read_replica_service_defined": False,
        "wal_archive_volume_configured": False,
        "redis_aof_configured": False,
        "redis_persistence_volume_configured": False,
    }

    report = evaluate_report(raw)

    blockers = report["readiness"]["blockers"]
    assert "postgres_archive_mode_off" in blockers
    assert "postgres_archive_command_missing" in blockers
    assert "pgbouncer_service_missing" in blockers
    assert "backend_not_routed_through_pgbouncer" in blockers
    assert "runner_not_routed_through_pgbouncer" in blockers
    assert "read_replica_service_missing" in blockers
    assert "wal_archive_volume_missing" in blockers
    assert "redis_aof_disabled" in blockers
    assert "redis_persistence_volume_missing" in blockers


def test_preflight_report_blocks_unsafe_connection_and_disk_budget():
    raw = _base_report()
    raw["connection_budget"]["configured_connection_budget"] = 90
    raw["connection_budget"]["active_connections"] = 81
    raw["filesystem"]["free_bytes"] = 10
    raw["filesystem"]["required_free_bytes"] = 20

    report = evaluate_report(raw)

    assert report["readiness"]["ready_for_physical_reclaim"] is False
    assert (
        "configured_connection_budget_exceeds_safe_limit"
        in report["readiness"]["blockers"]
    )
    assert "active_connections_exceed_safe_limit" in report["readiness"]["blockers"]
    assert "insufficient_postgres_free_space" in report["readiness"]["blockers"]


def test_preflight_report_blocks_unverifiable_runner_and_filesystem_state():
    raw = _base_report()
    raw["connection_budget"]["source_available"] = False
    raw["filesystem"]["source_available"] = False
    raw["runner_workload"] = {"error": "missing status column"}

    report = evaluate_report(raw)

    assert report["readiness"]["ready_for_physical_reclaim"] is False
    assert "connection_budget_unavailable" in report["readiness"]["warnings"]
    assert "postgres_data_path_unavailable" in report["readiness"]["blockers"]
    assert "runner_workload_unavailable" in report["readiness"]["blockers"]


def test_preflight_report_blocks_unavailable_database_without_recovery_claim():
    raw = _base_report()
    raw["database"] = {
        "connectable": False,
        "connection_error": "database is not accepting connections",
        "pg_is_in_recovery": None,
    }

    report = evaluate_report(raw)

    assert report["readiness"]["ready_for_physical_reclaim"] is False
    assert "database_unavailable" in report["readiness"]["blockers"]
    assert "database_in_recovery" not in report["readiness"]["blockers"]
