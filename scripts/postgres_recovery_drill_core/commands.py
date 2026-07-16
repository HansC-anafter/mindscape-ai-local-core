"""Deterministic command sequencing for the isolated drill topology."""

from __future__ import annotations

import json
import hashlib
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .policy import DrillScope
from .receipt import read_role_receipt, write_role_receipt


PRIMARY = "postgres-recovery-drill-primary"
STANDBY = "postgres-recovery-drill-standby"
POOLER = "pgbouncer-recovery-drill"
ROLE_RECEIPT = "role-receipt.json"


def _compose(scope: DrillScope, *args: str, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            "docker",
            "compose",
            "-p",
            scope.project,
            "-f",
            str(scope.compose_file),
            "--profile",
            "postgres-recovery-drill",
            *args,
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def status(scope: DrillScope) -> dict[str, Any]:
    result = _compose(scope, "ps", "--format", "json")
    return {
        "ok": result.returncode == 0,
        "project": scope.project,
        "services": result.stdout.strip(),
        "error": result.stderr.strip()[:500],
    }


def preflight(scope: DrillScope) -> dict[str, Any]:
    config = _compose(scope, "config", "--format", "json")
    if config.returncode != 0:
        raise RuntimeError("drill_compose_config_failed")
    payload = json.loads(config.stdout)
    services = payload.get("services") or {}
    required = {PRIMARY, STANDBY, POOLER}
    if not required.issubset(services):
        raise RuntimeError("drill_services_missing")
    for name in required:
        labels = services[name].get("labels") or {}
        if labels.get("com.mindscape.recovery-drill") != "true":
            raise RuntimeError(f"drill_label_missing:{name}")
    primary = _compose(
        scope,
        "exec",
        "-T",
        PRIMARY,
        "psql",
        "-U",
        "mindscape",
        "-d",
        "mindscape_core",
        "-At",
        "-c",
        "SELECT NOT pg_is_in_recovery() AND EXISTS (SELECT 1 FROM pg_replication_slots WHERE slot_name='mindscape_recovery_drill_slot')",
    )
    standby = _compose(
        scope,
        "exec",
        "-T",
        STANDBY,
        "psql",
        "-U",
        "mindscape",
        "-d",
        "mindscape_core",
        "-At",
        "-c",
        "SELECT pg_is_in_recovery()",
    )
    if primary.returncode != 0 or primary.stdout.strip() != "t":
        raise RuntimeError("drill_primary_or_slot_not_ready")
    if standby.returncode != 0 or standby.stdout.strip() != "t":
        raise RuntimeError("drill_standby_not_in_recovery")
    return {
        "ok": True,
        "project": scope.project,
        "services": sorted(required),
        "primary_slot_ready": True,
        "standby_in_recovery": True,
    }


def _psql(
    scope: DrillScope,
    service: str,
    sql: str,
    *,
    database: str = "mindscape_core",
) -> subprocess.CompletedProcess:
    return _compose(
        scope,
        "exec",
        "-T",
        service,
        "psql",
        "-U",
        "mindscape",
        "-d",
        database,
        "-At",
        "-v",
        "ON_ERROR_STOP=1",
        "-c",
        sql,
    )


def _other_database_service(service: str) -> str:
    if service == PRIMARY:
        return STANDBY
    if service == STANDBY:
        return PRIMARY
    raise RuntimeError("role_receipt_primary_invalid")


def _wait_for_sql_truth(
    scope: DrillScope,
    service: str,
    sql: str,
    *,
    timeout_seconds: float,
    error_code: str,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        result = _psql(scope, service, sql)
        if result.returncode == 0 and result.stdout.strip() == "t":
            return
        time.sleep(1)
    raise RuntimeError(error_code)


def _write_acceptance_row(scope: DrillScope, primary_service: str) -> tuple[str, str]:
    acceptance_id = str(uuid.uuid4())
    acceptance_checksum = hashlib.sha256(acceptance_id.encode("utf-8")).hexdigest()
    result = _psql(
        scope,
        primary_service,
        "CREATE TABLE IF NOT EXISTS recovery_drill_acceptance "
        "(id text PRIMARY KEY, checksum text NOT NULL); "
        f"INSERT INTO recovery_drill_acceptance VALUES ('{acceptance_id}', '{acceptance_checksum}')",
    )
    if result.returncode != 0:
        raise RuntimeError("acceptance_row_write_failed")
    return acceptance_id, acceptance_checksum


def _require_replica_caught_up(scope: DrillScope, primary_service: str) -> None:
    result = _psql(
        scope,
        primary_service,
        "SELECT count(*) > 0 AND "
        "COALESCE(max(pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn)), -1) = 0 "
        "FROM pg_stat_replication",
    )
    if result.returncode != 0 or result.stdout.strip() != "t":
        raise RuntimeError("standby_not_caught_up")


def _fence_primary(
    scope: DrillScope,
    primary_service: str,
    *,
    fence_reason: str,
) -> str:
    stopped = _compose(scope, "stop", primary_service)
    if stopped.returncode != 0:
        raise RuntimeError("old_primary_fence_failed")
    proof = _compose(
        scope,
        "ps",
        "--status",
        "running",
        "--services",
        primary_service,
    )
    if proof.returncode != 0 or primary_service in proof.stdout.splitlines():
        raise RuntimeError("old_primary_fence_not_proven")
    return f"compose-stop+running-set-absent:{fence_reason.strip()}"


def _promote(scope: DrillScope, service: str) -> None:
    promoted = _compose(
        scope,
        "exec",
        "-T",
        service,
        "pg_ctl",
        "-D",
        "/var/lib/postgresql/data/pgdata",
        "promote",
    )
    if promoted.returncode != 0:
        raise RuntimeError("standby_promotion_failed")
    _wait_for_sql_truth(
        scope,
        service,
        "SELECT NOT pg_is_in_recovery()",
        timeout_seconds=30,
        error_code="promoted_primary_not_writable",
    )


def _read_primary_identity(scope: DrillScope, service: str) -> dict[str, str]:
    result = _psql(
        scope,
        service,
        "SELECT json_build_object("
        "'system_identifier', s.system_identifier::text, "
        "'timeline', c.timeline_id::text, "
        "'lsn', pg_current_wal_lsn()::text) "
        "FROM pg_control_system() s CROSS JOIN pg_control_checkpoint() c",
    )
    if result.returncode != 0:
        raise RuntimeError("promoted_primary_identity_unavailable")
    try:
        identity = json.loads(result.stdout.strip())
    except (TypeError, ValueError) as exc:
        raise RuntimeError("promoted_primary_identity_invalid") from exc
    if not all(str(identity.get(key) or "").strip() for key in ("system_identifier", "timeline", "lsn")):
        raise RuntimeError("promoted_primary_identity_incomplete")
    return {key: str(identity[key]) for key in ("system_identifier", "timeline", "lsn")}


def _retarget_pgbouncer(scope: DrillScope, receipt: dict[str, Any]) -> None:
    rendered = scope.receipt_dir / "pgbouncer.ini"
    rendered.write_text(_render_pgbouncer_config(receipt), encoding="utf-8")
    copied = _compose(scope, "cp", str(rendered), f"{POOLER}:/tmp/pgbouncer.next.ini")
    if copied.returncode != 0:
        raise RuntimeError("pgbouncer_config_copy_failed")
    replaced = _compose(
        scope,
        "exec",
        "-T",
        POOLER,
        "mv",
        "/tmp/pgbouncer.next.ini",
        "/tmp/pgbouncer.ini",
    )
    if replaced.returncode != 0:
        raise RuntimeError("pgbouncer_config_replace_failed")
    for command in ("RELOAD", "RECONNECT mindscape_core", "WAIT_CLOSE mindscape_core"):
        applied = _compose(
            scope,
            "exec",
            "-T",
            POOLER,
            "psql",
            "-h",
            "127.0.0.1",
            "-p",
            "6432",
            "-U",
            "mindscape",
            "-d",
            "pgbouncer",
            "-c",
            command,
        )
        if applied.returncode != 0:
            raise RuntimeError(f"pgbouncer_admin_command_failed:{command.split()[0].lower()}")


def _verify_acceptance_via_pooler(
    scope: DrillScope,
    *,
    acceptance_id: str,
    acceptance_checksum: str,
) -> None:
    verified = _compose(
        scope,
        "exec",
        "-T",
        POOLER,
        "psql",
        "-h",
        "127.0.0.1",
        "-p",
        "6432",
        "-U",
        "mindscape",
        "-d",
        "mindscape_core",
        "-At",
        "-c",
        f"SELECT checksum = '{acceptance_checksum}' FROM recovery_drill_acceptance WHERE id = '{acceptance_id}'",
    )
    if verified.returncode != 0 or verified.stdout.strip() != "t":
        raise RuntimeError("promoted_acceptance_row_missing")


def _controlled_switchover(
    scope: DrillScope,
    *,
    current_primary: str,
    target_primary: str,
    operator: str,
    fence_reason: str,
) -> dict[str, Any]:
    started = time.monotonic()
    if not operator.strip() or not fence_reason.strip():
        raise RuntimeError("operator_and_fence_proof_required")
    if target_primary != _other_database_service(current_primary):
        raise RuntimeError("switchover_target_invalid")
    acceptance_id, acceptance_checksum = _write_acceptance_row(scope, current_primary)
    _require_replica_caught_up(scope, current_primary)
    actual_fence_proof = _fence_primary(
        scope,
        current_primary,
        fence_reason=fence_reason,
    )
    _promote(scope, target_primary)
    identity = _read_primary_identity(scope, target_primary)
    receipt_path = scope.receipt_dir / ROLE_RECEIPT
    generation = 1
    if receipt_path.exists():
        generation = int(read_role_receipt(receipt_path).get("generation") or 0) + 1
    receipt = write_role_receipt(
        receipt_path,
        {
            "generation": generation,
            "primary_service": target_primary,
            **identity,
            "promoted_at": datetime.now(timezone.utc).isoformat(),
            "old_primary_service": current_primary,
            "old_primary_fence_proof": actual_fence_proof,
            "operator": operator.strip(),
            "state": "promoted_pooler_pending",
            "acceptance_id": acceptance_id,
            "acceptance_checksum": acceptance_checksum,
        },
    )
    _retarget_pgbouncer(scope, receipt)
    _verify_acceptance_via_pooler(
        scope,
        acceptance_id=acceptance_id,
        acceptance_checksum=acceptance_checksum,
    )
    rto_seconds = round(time.monotonic() - started, 3)
    if rto_seconds > 120:
        raise RuntimeError(f"controlled_switchover_rto_exceeded:{rto_seconds}")
    receipt["state"] = "accepted"
    receipt["rto_seconds"] = rto_seconds
    receipt = write_role_receipt(
        receipt_path,
        {key: value for key, value in receipt.items() if key != "checksum"},
    )
    return {
        "ok": True,
        "receipt": receipt,
        "planned_switchover_rpo": 0,
        "rto_seconds": rto_seconds,
    }


def switchover(
    scope: DrillScope,
    *,
    operator: str,
    fence_proof: str,
) -> dict[str, Any]:
    return _controlled_switchover(
        scope,
        current_primary=PRIMARY,
        target_primary=STANDBY,
        operator=operator,
        fence_reason=fence_proof,
    )


def rebuild_standby(scope: DrillScope) -> dict[str, Any]:
    receipt_path = scope.receipt_dir / ROLE_RECEIPT
    receipt = read_role_receipt(receipt_path)
    current_primary = str(receipt.get("primary_service") or "")
    candidate = _other_database_service(current_primary)
    if receipt.get("state") != "accepted":
        raise RuntimeError("rebuild_requires_accepted_primary")
    removed = _compose(scope, "rm", "-f", "-s", candidate)
    if removed.returncode != 0:
        raise RuntimeError("old_primary_remove_failed")
    slot_name = f"mindscape_recovery_drill_{'primary' if candidate == PRIMARY else 'standby'}_slot"
    rebuild_script = f"""
set -eu
rm -rf "${{PGDATA:?}}"/*
export PGPASSWORD="$POSTGRES_PASSWORD"
psql --host={current_primary} --username="$POSTGRES_USER" --dbname=postgres --set=ON_ERROR_STOP=1 --command="SELECT pg_create_physical_replication_slot('{slot_name}') WHERE NOT EXISTS (SELECT 1 FROM pg_replication_slots WHERE slot_name = '{slot_name}')"
pg_basebackup --host={current_primary} --username="$POSTGRES_USER" --pgdata="$PGDATA" --wal-method=stream --write-recovery-conf --slot={slot_name}
""".strip()
    rebuilt = _compose(
        scope,
        "run",
        "--rm",
        "--no-deps",
        "--entrypoint",
        "sh",
        candidate,
        "-ec",
        rebuild_script,
        timeout=600,
    )
    if rebuilt.returncode != 0:
        raise RuntimeError("old_primary_basebackup_rebuild_failed")
    started = _compose(scope, "up", "-d", "--no-deps", candidate)
    if started.returncode != 0:
        raise RuntimeError("rebuilt_standby_start_failed")
    _wait_for_sql_truth(
        scope,
        candidate,
        "SELECT pg_is_in_recovery()",
        timeout_seconds=120,
        error_code="rebuilt_standby_not_in_recovery",
    )
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        try:
            _require_replica_caught_up(scope, current_primary)
            break
        except RuntimeError:
            time.sleep(1)
    else:
        raise RuntimeError("rebuilt_standby_not_caught_up")
    body = {key: value for key, value in receipt.items() if key != "checksum"}
    body.update(
        {
            "state": "standby_rebuilt_caught_up",
            "standby_service": candidate,
            "standby_slot": slot_name,
            "standby_rebuilt_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    receipt = write_role_receipt(receipt_path, body)
    return {"ok": True, "state": receipt["state"], "receipt": receipt}


def switchback(
    scope: DrillScope,
    *,
    operator: str,
    fence_proof: str,
) -> dict[str, Any]:
    receipt = read_role_receipt(scope.receipt_dir / ROLE_RECEIPT)
    if receipt.get("state") != "standby_rebuilt_caught_up":
        raise RuntimeError("switchback_requires_rebuilt_caught_up_standby")
    current_primary = str(receipt.get("primary_service") or "")
    target_primary = str(receipt.get("standby_service") or "")
    return _controlled_switchover(
        scope,
        current_primary=current_primary,
        target_primary=target_primary,
        operator=operator,
        fence_reason=fence_proof,
    )


def _render_pgbouncer_config(receipt: dict[str, Any]) -> str:
    if receipt.get("primary_service") not in {PRIMARY, STANDBY}:
        raise RuntimeError("role_receipt_primary_invalid")
    return f"""[databases]
mindscape_core = host={receipt['primary_service']} port=5432 dbname=mindscape_core

[pgbouncer]
listen_addr = 0.0.0.0
listen_port = 6432
auth_type = scram-sha-256
auth_file = /tmp/pgbouncer-userlist.txt
admin_users = mindscape
stats_users = mindscape
pool_mode = transaction
max_client_conn = 100
default_pool_size = 20
reserve_pool_size = 5
server_reset_query = DISCARD ALL
ignore_startup_parameters = extra_float_digits
"""
