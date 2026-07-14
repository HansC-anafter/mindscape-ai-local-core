#!/usr/bin/env python3
"""Runtime workload admission for resource-heavy local backups."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .filesystem import (
    resolve_data_host_dir,
    resolve_primary_root,
    resolve_wal_archive_root,
    run_text,
)


ACTIVE_RECEIVER_STATES = frozenset(
    {"starting", "waiting_source", "receiving", "analyzing", "degraded", "stopping"}
)
PENDING_RECEIVER_GRACE_SECONDS = 300


_DATABASE_WORKLOAD_COUNTS_SQL = """
WITH candidates AS (
    SELECT
        status,
        started_at,
        CASE
            WHEN metadata->>'last_round_updated_at' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'
            THEN (metadata->>'last_round_updated_at')::timestamptz
            ELSE NULL
        END AS last_round_updated_at,
        CASE
            WHEN metadata->>'pipeline_stage_updated_at' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'
            THEN (metadata->>'pipeline_stage_updated_at')::timestamptz
            ELSE NULL
        END AS pipeline_stage_updated_at,
        CASE
            WHEN metadata->>'dispatch_updated_at' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'
            THEN (metadata->>'dispatch_updated_at')::timestamptz
            ELSE NULL
        END AS dispatch_updated_at,
        CASE
            WHEN metadata->>'updated_at' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'
            THEN (metadata->>'updated_at')::timestamptz
            ELSE NULL
        END AS metadata_updated_at
    FROM meeting_sessions
    WHERE ended_at IS NULL
      AND status IN ('planned', 'active', 'closing')
),
activity AS (
    SELECT
        status,
        GREATEST(
            started_at,
            COALESCE(last_round_updated_at, started_at),
            COALESCE(pipeline_stage_updated_at, started_at),
            COALESCE(dispatch_updated_at, started_at),
            COALESCE(metadata_updated_at, started_at)
        ) AS last_activity_at
    FROM candidates
)
SELECT
    (
        SELECT COUNT(*)
        FROM activity
        WHERE last_activity_at >= now() - (
            CASE
                WHEN status = 'planned' THEN interval '15 minutes'
                ELSE interval '30 minutes'
            END
        )
    ),
    (
        SELECT COUNT(*)
        FROM pg_stat_activity
        WHERE backend_type = 'walsender'
          AND query ~ '^BASE_BACKUP'
    )
""".strip()


def active_database_workload_counts() -> dict[str, int]:
    """Read bounded meeting and base-backup counts directly from PostgreSQL."""

    output = run_text(
        [
            "docker",
            "exec",
            "mindscape-ai-local-core-postgres",
            "psql",
            "-X",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            "mindscape",
            "-d",
            "mindscape_core",
            "-Atc",
            f"SET statement_timeout = '3s'; {_DATABASE_WORKLOAD_COUNTS_SQL}",
        ],
        timeout=10,
    ).strip()
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    parts = lines[-1].split("|") if lines else []
    if len(parts) != 2 or any(not part.isdigit() for part in parts):
        raise RuntimeError("database_workload_counts_invalid")
    return {
        "active_meeting_sessions": int(parts[0]),
        "active_postgres_base_backups": int(parts[1]),
    }


def _pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _state_is_recent(path: Path, now: datetime) -> bool:
    try:
        age_seconds = now.timestamp() - path.stat().st_mtime
    except OSError:
        return False
    return 0 <= age_seconds <= PENDING_RECEIVER_GRACE_SECONDS


def inspect_live_media_receivers(
    data_host_dir: Path,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return active receiver identities without reading secret descriptors."""

    state_root = data_host_dir / "runtime" / "live-media-receivers"
    observed_at = now or datetime.now(timezone.utc)
    active: list[dict[str, Any]] = []
    errors: list[str] = []
    if not state_root.exists():
        return {"state_root": str(state_root), "active": active, "errors": errors}
    try:
        state_paths = sorted(state_root.glob("*.state.json"))
    except OSError as exc:
        return {
            "state_root": str(state_root),
            "active": active,
            "errors": [f"receiver_state_scan_failed:{type(exc).__name__}"],
        }
    for path in state_paths:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("state_not_object")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"receiver_state_invalid:{path.name}:{type(exc).__name__}")
            continue
        state = str(payload.get("state") or "").strip()
        if state not in ACTIVE_RECEIVER_STATES:
            continue
        try:
            pid = int(payload.get("pid") or 0)
        except (TypeError, ValueError):
            pid = 0
        pid_alive = _pid_is_running(pid)
        pending_start = state == "starting" and pid <= 0 and _state_is_recent(path, observed_at)
        if not pid_alive and not pending_start:
            continue
        active.append(
            {
                "media_session_id": str(payload.get("media_session_id") or "")[:128],
                "workspace_id": str(payload.get("workspace_id") or "")[:128],
                "state": state,
                "pid": pid,
                "pid_alive": pid_alive,
                "updated_at": str(payload.get("updated_at") or "")[:64],
            }
        )
    return {"state_root": str(state_root), "active": active[:20], "errors": errors[:20]}


def inspect_backup_runtime_admission(
    *,
    data_host_dir: Path | None = None,
    wal_archive_root: Path | None = None,
) -> dict[str, Any]:
    """Fail closed when a live practice workload cannot be ruled out."""

    errors: list[str] = []
    resolved_wal_root = wal_archive_root or resolve_wal_archive_root(resolve_primary_root(None))
    base_backup_lock = resolved_wal_root / ".pg_basebackup.lock.d"
    database_inspection_skipped = base_backup_lock.is_dir()
    if database_inspection_skipped:
        meeting_count = None
        base_backup_count = 1
    else:
        try:
            database_workloads = active_database_workload_counts()
            meeting_count = database_workloads["active_meeting_sessions"]
            base_backup_count = database_workloads["active_postgres_base_backups"]
        except Exception as exc:
            meeting_count = None
            base_backup_count = None
            errors.append(f"database_workload_inspection_failed:{type(exc).__name__}")
    try:
        receivers = inspect_live_media_receivers(data_host_dir or resolve_data_host_dir())
        errors.extend(receivers["errors"])
    except Exception as exc:
        receivers = {"state_root": "", "active": [], "errors": []}
        errors.append(f"receiver_inspection_failed:{type(exc).__name__}")

    blocking_reasons: list[str] = []
    if meeting_count is not None and meeting_count > 0:
        blocking_reasons.append("active_meeting_sessions")
    if base_backup_count is not None and base_backup_count > 0:
        blocking_reasons.append("postgres_basebackup_already_running")
    if receivers["active"]:
        blocking_reasons.append("active_live_media_receivers")
    if errors:
        blocking_reasons.append("backup_runtime_admission_inspection_failed")
    return {
        "schema_version": "backup_runtime_admission.v1",
        "admitted": not blocking_reasons,
        "active_meeting_sessions": meeting_count,
        "active_postgres_base_backups": base_backup_count,
        "base_backup_lock_path": str(base_backup_lock),
        "database_inspection_skipped": database_inspection_skipped,
        "active_live_media_receivers": receivers["active"],
        "receiver_state_root": receivers["state_root"],
        "blocking_reasons": blocking_reasons,
        "inspection_errors": errors,
    }


def require_backup_runtime_admission(
    *,
    data_host_dir: Path | None = None,
    wal_archive_root: Path | None = None,
) -> dict[str, Any]:
    admission = inspect_backup_runtime_admission(
        data_host_dir=data_host_dir,
        wal_archive_root=wal_archive_root,
    )
    if not admission["admitted"]:
        raise SystemExit(
            "Backup runtime admission deferred: "
            + ", ".join(admission["blocking_reasons"])
        )
    return admission
