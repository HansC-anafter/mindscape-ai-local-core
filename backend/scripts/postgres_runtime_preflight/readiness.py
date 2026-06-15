"""Readiness evaluation helpers for PostgreSQL runtime preflight."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping


MANAGED_ARCHIVE_COMMAND = "/usr/local/bin/mindscape-archive-wal"


def _parse_int(value: Any, default: int = 0) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if value is None:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _split_preload_libraries(value: str) -> set[str]:
    return {
        item.strip()
        for item in str(value or "").split(",")
        if item.strip()
    }


def _archiver_currently_failing(archiver: Mapping[str, Any]) -> bool:
    failed_count = _parse_int(archiver.get("failed_count"), 0)
    if failed_count <= 0:
        return False
    last_failed = _parse_datetime(archiver.get("last_failed_time"))
    if last_failed is None:
        return True
    last_archived = _parse_datetime(archiver.get("last_archived_time"))
    return last_archived is None or last_archived < last_failed


def _has_preload(report: Mapping[str, Any], library: str) -> bool:
    database = report.get("database") if isinstance(report.get("database"), dict) else {}
    preload = str(database.get("shared_preload_libraries") or "")
    return library in _split_preload_libraries(preload)


def evaluate_report(report: dict[str, Any]) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []

    database = report.get("database") if isinstance(report.get("database"), dict) else {}
    if database.get("connectable") is False:
        blockers.append("database_unavailable")
    elif database.get("pg_is_in_recovery") is not False:
        blockers.append("database_in_recovery")
    if str(database.get("wal_level") or "").strip().lower() != "replica":
        blockers.append("postgres_wal_level_not_replica")
    if str(database.get("archive_mode") or "").strip().lower() != "on":
        blockers.append("postgres_archive_mode_off")
    archive_command = str(database.get("archive_command") or "").strip()
    if not archive_command:
        blockers.append("postgres_archive_command_missing")
    elif MANAGED_ARCHIVE_COMMAND not in archive_command:
        blockers.append("postgres_archive_command_not_managed")
    archiver = (
        database.get("archiver") if isinstance(database.get("archiver"), dict) else {}
    )
    if _archiver_currently_failing(archiver):
        blockers.append("postgres_archiver_currently_failing")
    elif _parse_int(archiver.get("failed_count"), 0) > 0:
        warnings.append("postgres_archiver_historical_failures_present")

    extensions = (
        report.get("extensions") if isinstance(report.get("extensions"), dict) else {}
    )
    installed = set(extensions.get("installed") or [])
    if "pg_repack" not in installed:
        blockers.append("pg_repack_extension_missing")
    if "pg_stat_statements" not in installed:
        blockers.append("pg_stat_statements_extension_missing")
    if not _has_preload(report, "pg_stat_statements"):
        blockers.append("pg_stat_statements_not_preloaded")

    tools = report.get("tools") if isinstance(report.get("tools"), dict) else {}
    if not tools.get("pg_repack_binary"):
        blockers.append("pg_repack_binary_missing")

    script_paths = (
        report.get("script_paths")
        if isinstance(report.get("script_paths"), dict)
        else {}
    )
    for key, payload in script_paths.items():
        if not isinstance(payload, dict) or not payload.get("exists"):
            blockers.append(f"{key}_script_missing")

    backup_verification = (
        report.get("backup_verification")
        if isinstance(report.get("backup_verification"), dict)
        else {}
    )
    if not backup_verification.get("source"):
        blockers.append("verified_backup_missing")
    elif backup_verification.get("errors") or not backup_verification.get("verified"):
        blockers.append("verified_backup_invalid")
    else:
        if backup_verification.get("verification_mode") != "manifest_checksum":
            warnings.append("verified_backup_checksum_not_recomputed")
        backup_options = (
            backup_verification.get("options")
            if isinstance(backup_verification.get("options"), dict)
            else {}
        )
        if backup_options.get("skip_db") is True:
            blockers.append("verified_backup_skips_database")
        if backup_options.get("skip_files") is True:
            warnings.append("verified_backup_skips_files")

    activity = report.get("activity") if isinstance(report.get("activity"), dict) else {}
    idle_in_transaction = int(activity.get("idle_in_transaction") or 0)
    if idle_in_transaction > 0:
        blockers.append("idle_in_transaction_sessions_present")

    hot_row_budget = (
        report.get("hot_row_budget")
        if isinstance(report.get("hot_row_budget"), dict)
        else {}
    )
    sample = (
        hot_row_budget.get("sample")
        if isinstance(hot_row_budget.get("sample"), dict)
        else {}
    )
    over_budget = {
        "execution_context": int(sample.get("execution_context_over_budget") or 0),
        "result": int(sample.get("result_over_budget") or 0),
        "params": int(sample.get("params_over_budget") or 0),
        "blocked_payload": int(sample.get("blocked_payload_over_budget") or 0),
    }
    if any(count > 0 for count in over_budget.values()):
        blockers.append("recent_hot_rows_over_budget")

    runner_workload = (
        report.get("runner_workload")
        if isinstance(report.get("runner_workload"), dict)
        else {}
    )
    if runner_workload.get("error"):
        blockers.append("runner_workload_unavailable")
    else:
        running_tasks = int(runner_workload.get("running_tasks") or 0)
        runner_owned_running_tasks = int(
            runner_workload.get("runner_owned_running_tasks") or 0
        )
        ready_pending_tasks = int(runner_workload.get("ready_pending_tasks") or 0)
        if running_tasks > 0 or runner_owned_running_tasks > 0:
            blockers.append("runner_workload_active")
        if ready_pending_tasks > 0:
            warnings.append("ready_pending_tasks_present")

    runner_claim_gate = (
        report.get("runner_claim_gate")
        if isinstance(report.get("runner_claim_gate"), dict)
        else {}
    )
    if runner_claim_gate.get("error"):
        blockers.append("runner_claim_gate_unavailable")
    elif runner_claim_gate.get("state") != "paused":
        blockers.append("runner_claim_gate_not_paused")
    elif not runner_claim_gate.get("persisted"):
        blockers.append("runner_claim_gate_not_persisted")

    connection_budget = (
        report.get("connection_budget")
        if isinstance(report.get("connection_budget"), dict)
        else {}
    )
    safe_connection_limit = int(connection_budget.get("safe_connection_limit") or 0)
    if not connection_budget.get("source_available"):
        warnings.append("connection_budget_unavailable")
    elif safe_connection_limit > 0:
        configured_budget = int(
            connection_budget.get("configured_connection_budget") or 0
        )
        active_connections = int(connection_budget.get("active_connections") or 0)
        if configured_budget > safe_connection_limit:
            blockers.append("configured_connection_budget_exceeds_safe_limit")
        if active_connections > safe_connection_limit:
            blockers.append("active_connections_exceed_safe_limit")

    runtime_readiness = (
        report.get("runtime_readiness")
        if isinstance(report.get("runtime_readiness"), dict)
        else {}
    )
    if not runtime_readiness.get("source_available"):
        warnings.append("runtime_compose_unavailable")
    else:
        required_runtime_flags = {
            "pgbouncer_service_defined": "pgbouncer_service_missing",
            "backend_uses_pgbouncer": "backend_not_routed_through_pgbouncer",
            "runner_uses_pgbouncer": "runner_not_routed_through_pgbouncer",
            "read_replica_service_defined": "read_replica_service_missing",
            "wal_archive_volume_configured": "wal_archive_volume_missing",
            "redis_aof_configured": "redis_aof_disabled",
            "redis_persistence_volume_configured": "redis_persistence_volume_missing",
        }
        for flag, blocker in required_runtime_flags.items():
            if not runtime_readiness.get(flag):
                blockers.append(blocker)

    filesystem = (
        report.get("filesystem") if isinstance(report.get("filesystem"), dict) else {}
    )
    if not filesystem.get("source_available"):
        blockers.append("postgres_data_path_unavailable")
    else:
        free_bytes = int(filesystem.get("free_bytes") or 0)
        required_free_bytes = int(filesystem.get("required_free_bytes") or 0)
        if free_bytes < required_free_bytes:
            blockers.append("insufficient_postgres_free_space")

    top_statements = report.get("pg_stat_statements_top")
    if not top_statements:
        warnings.append("pg_stat_statements_top_sql_unavailable")
    elif (
        isinstance(top_statements, list)
        and top_statements
        and top_statements[0].get("error")
    ):
        warnings.append("pg_stat_statements_top_sql_failed")

    evaluated = dict(report)
    evaluated["readiness"] = {
        "ready_for_physical_reclaim": not blockers,
        "blockers": blockers,
        "warnings": warnings,
    }
    return evaluated
