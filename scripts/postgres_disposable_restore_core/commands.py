"""Bounded commands for booting and reading a disposable PG16 restore."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from datetime import datetime, timezone
from typing import Any

from .policy import RestoreSource
from .receipt import write_restore_receipt


RESTORE_SERVICE = "postgres-recovery-restore"
APP_PROBE_SERVICE = "postgres-recovery-restore-app-probe"


def _environment(source: RestoreSource) -> dict[str, str]:
    environment = {
        **os.environ,
        "MINDSCAPE_RECOVERY_RESTORE_BASE_DIR": str(source.base_dir),
        "MINDSCAPE_RECOVERY_RESTORE_WAL_DIR": str(source.wal_dir),
        "MINDSCAPE_RECOVERY_TARGET_TIME": source.recovery_target_time,
    }
    environment.pop("MINDSCAPE_RECOVERY_RESTORE_DATA_DIR", None)
    if source.scope.data_dir is not None:
        environment["MINDSCAPE_RECOVERY_RESTORE_DATA_DIR"] = str(
            source.scope.data_dir
        )
    return environment


def _compose(
    source: RestoreSource,
    *args: str,
    timeout: int = 60,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "docker",
            "compose",
            "-p",
            source.scope.project,
            "-f",
            str(source.scope.compose_file),
            "--profile",
            "postgres-recovery-drill",
            *args,
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=_environment(source),
    )


def _query(source: RestoreSource, sql: str) -> subprocess.CompletedProcess[str]:
    return _compose(
        source,
        "exec",
        "-T",
        RESTORE_SERVICE,
        "psql",
        "-U",
        "mindscape",
        "-d",
        "mindscape_core",
        "-At",
        "-v",
        "ON_ERROR_STOP=1",
        "-c",
        sql,
    )


def preflight(source: RestoreSource) -> dict[str, Any]:
    config = _compose(source, "config", "--format", "json")
    if config.returncode != 0:
        raise RuntimeError("restore_compose_config_failed")
    payload = json.loads(config.stdout)
    services = payload.get("services") or {}
    required = {RESTORE_SERVICE, APP_PROBE_SERVICE}
    if not required.issubset(services):
        raise RuntimeError("restore_services_missing")
    for name in required:
        labels = services[name].get("labels") or {}
        if labels.get("com.mindscape.recovery-drill") != "true":
            raise RuntimeError(f"restore_drill_label_missing:{name}")
    return {
        "ok": True,
        "project": source.scope.project,
        "backup_dir": str(source.scope.backup_dir),
        "base_backup_id": str(
            ((source.manifest.get("components") or {}).get("postgres") or {}).get(
                "base_backup_id"
            )
            or ""
        ),
        "base_dir": str(source.base_dir),
        "wal_dir": str(source.wal_dir),
        "required_wal_segment_count": len(source.required_wal_segments),
        "recovery_target_time": source.recovery_target_time,
        "restore_data_dir": (
            str(source.scope.data_dir)
            if source.scope.data_dir is not None
            else "docker_named_volume"
        ),
        "services": sorted(required),
    }


def status(source: RestoreSource) -> dict[str, Any]:
    result = _compose(source, "ps", "--format", "json")
    return {
        "ok": result.returncode == 0,
        "project": source.scope.project,
        "services": result.stdout.strip(),
        "error": result.stderr.strip()[:500],
    }


def _require_clean_project(source: RestoreSource) -> None:
    result = _compose(source, "ps", "-a", "--services")
    if result.returncode != 0:
        raise RuntimeError("restore_project_state_unavailable")
    if any(line.strip() for line in result.stdout.splitlines()):
        raise RuntimeError("restore_project_not_clean_run_cleanup_first")


def _read_json_query(source: RestoreSource, sql: str, error_code: str) -> dict[str, Any]:
    result = _query(source, sql)
    if result.returncode != 0:
        raise RuntimeError(error_code)
    try:
        payload = json.loads(result.stdout.strip())
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"{error_code}_invalid_json") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"{error_code}_invalid_payload")
    return payload


def _critical_database_evidence(source: RestoreSource) -> dict[str, Any]:
    relations = _read_json_query(
        source,
        "SELECT json_build_object("
        "'tasks', to_regclass('public.tasks') IS NOT NULL, "
        "'task_summary_projection', to_regclass('public.task_summary_projection') IS NOT NULL, "
        "'alembic_version', to_regclass('public.alembic_version') IS NOT NULL, "
        "'pack_install_commit_receipts', to_regclass('public.pack_install_commit_receipts') IS NOT NULL)",
        "restore_relation_probe_failed",
    )
    if not all(relations.values()):
        missing = sorted(key for key, present in relations.items() if not present)
        raise RuntimeError(f"restore_critical_relation_missing:{','.join(missing)}")
    evidence = _read_json_query(
        source,
        "SELECT json_build_object("
        "'in_recovery', pg_is_in_recovery(), "
        "'server_version', current_setting('server_version'), "
        "'database_bytes', pg_database_size(current_database()), "
        "'task_count', (SELECT count(*) FROM tasks), "
        "'task_summary_count', (SELECT count(*) FROM task_summary_projection), "
        "'migration_head_count', (SELECT count(*) FROM alembic_version), "
        "'install_commit_receipt_count', (SELECT count(*) FROM pack_install_commit_receipts), "
        "'latest_task_id', (SELECT id::text FROM tasks ORDER BY created_at DESC LIMIT 1))",
        "restore_critical_query_failed",
    )
    if evidence.get("in_recovery") is not False:
        raise RuntimeError("restore_did_not_promote_at_target")
    if int(evidence.get("migration_head_count") or 0) < 24:
        raise RuntimeError("restore_migration_heads_below_24")
    if int(evidence.get("task_count") or 0) <= 0:
        raise RuntimeError("restore_tasks_empty")
    if not str(evidence.get("latest_task_id") or ""):
        raise RuntimeError("restore_latest_task_id_missing")
    return {"relations": relations, **evidence}


def _application_probe(source: RestoreSource) -> dict[str, Any]:
    result = _compose(
        source,
        "run",
        "--rm",
        "--no-deps",
        APP_PROBE_SERVICE,
        timeout=180,
    )
    if result.returncode != 0:
        raise RuntimeError("restore_application_read_probe_failed")
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    try:
        payload = json.loads(lines[-1])
    except (IndexError, TypeError, ValueError) as exc:
        raise RuntimeError("restore_application_read_probe_invalid") from exc
    if payload.get("ok") is not True or payload.get("transaction_read_only") != "on":
        raise RuntimeError("restore_application_read_probe_rejected")
    return payload


def run_restore(source: RestoreSource, *, timeout_seconds: int = 3600) -> dict[str, Any]:
    if timeout_seconds <= 0 or timeout_seconds > 3600:
        raise ValueError("restore_timeout_must_be_between_1_and_3600")
    preflight_evidence = preflight(source)
    _require_clean_project(source)
    started = time.monotonic()
    launched = _compose(source, "up", "-d", RESTORE_SERVICE, timeout=120)
    if launched.returncode != 0:
        raise RuntimeError("restore_service_start_failed")
    deadline = started + timeout_seconds
    while time.monotonic() < deadline:
        ready = _query(source, "SELECT NOT pg_is_in_recovery()")
        if ready.returncode == 0 and ready.stdout.strip() == "t":
            break
        time.sleep(2)
    else:
        raise RuntimeError("restore_replay_timeout")
    database_evidence = _critical_database_evidence(source)
    application_evidence = _application_probe(source)
    rto_seconds = round(time.monotonic() - started, 3)
    if rto_seconds > 3600:
        raise RuntimeError(f"restore_rto_exceeded:{rto_seconds}")
    receipt = write_restore_receipt(
        source.scope.receipt_dir / "restore-receipt.json",
        {
            "schema_version": 1,
            "state": "accepted",
            "accepted_at": datetime.now(timezone.utc).isoformat(),
            "project": source.scope.project,
            "backup_dir": str(source.scope.backup_dir),
            "base_dir": str(source.base_dir),
            "wal_dir": str(source.wal_dir),
            "recovery_target_time": source.recovery_target_time,
            "restore_data_dir": (
                str(source.scope.data_dir)
                if source.scope.data_dir is not None
                else "docker_named_volume"
            ),
            "required_wal_segment_count": len(source.required_wal_segments),
            "rto_seconds": rto_seconds,
            "database_evidence": database_evidence,
            "application_evidence": application_evidence,
        },
    )
    return {
        "ok": True,
        "preflight": preflight_evidence,
        "receipt": receipt,
        "rto_seconds": rto_seconds,
    }


def cleanup(source: RestoreSource) -> dict[str, Any]:
    result = _compose(source, "down", "--volumes", "--remove-orphans", timeout=180)
    if result.returncode != 0:
        raise RuntimeError("restore_cleanup_failed")
    removed_data_dir = False
    if source.scope.data_dir is not None and source.scope.data_dir.exists():
        shutil.rmtree(source.scope.data_dir)
        removed_data_dir = True
    return {
        "ok": True,
        "project": source.scope.project,
        "state": "disposable_runtime_removed_receipt_retained",
        "restore_data_dir_removed": removed_data_dir,
    }
