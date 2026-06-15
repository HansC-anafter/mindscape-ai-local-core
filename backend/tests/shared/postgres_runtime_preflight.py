"""Shared test fixtures for PostgreSQL runtime preflight tests."""

from __future__ import annotations

from typing import Any


def base_preflight_report() -> dict[str, Any]:
    return {
        "database": {
            "connectable": True,
            "pg_is_in_recovery": False,
            "shared_preload_libraries": "pg_stat_statements",
            "max_connections": "100",
            "wal_level": "replica",
            "archive_mode": "on",
            "archive_command": "/usr/local/bin/mindscape-archive-wal %p %f /archive",
            "archiver": {
                "archived_count": 1,
                "last_archived_wal": "000000010000000000000001",
                "last_archived_time": "2026-05-25T00:00:00+00:00",
                "failed_count": 0,
                "last_failed_wal": "",
                "last_failed_time": None,
                "stats_reset": "2026-05-25T00:00:00+00:00",
            },
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
