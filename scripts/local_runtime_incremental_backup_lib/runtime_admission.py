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

_RUNNER_HEARTBEAT_COUNTS_LUA = """
local cursor = '0'
local count = 0
local inflight = 0
local capacity = 0
local malformed = 0
repeat
    local page = redis.call(
        'SCAN', cursor, 'MATCH',
        'mindscape:runner_resources:heartbeat:v1:*', 'COUNT', 1000
    )
    cursor = page[1]
    for _, key in ipairs(page[2]) do
        count = count + 1
        local raw = redis.call('GET', key)
        local ok, value = pcall(cjson.decode, raw or '')
        if not ok or type(value) ~= 'table' or type(value.capacity) ~= 'table' then
            malformed = malformed + 1
        else
            inflight = inflight + tonumber(value.capacity.inflight or 0)
            capacity = capacity + tonumber(value.capacity.max_inflight or 0)
        end
    end
until cursor == '0'
return cjson.encode({
    count = count,
    inflight = inflight,
    capacity = capacity,
    malformed = malformed
})
""".strip()


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
    ),
    (
        SELECT COUNT(*)
        FROM tasks
        WHERE status = 'running'
          AND heartbeat_at >= now() - interval '2 minutes'
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
    if len(parts) != 3 or any(not part.isdigit() for part in parts):
        raise RuntimeError("database_workload_counts_invalid")
    return {
        "active_meeting_sessions": int(parts[0]),
        "active_postgres_base_backups": int(parts[1]),
        "active_runner_tasks": int(parts[2]),
    }


def active_runner_heartbeat_counts() -> dict[str, int]:
    """Read aggregate active-runner capacity without exposing runner keys."""

    output = run_text(
        [
            "docker",
            "exec",
            "mindscape-ai-local-core-redis",
            "redis-cli",
            "--raw",
            "EVAL",
            _RUNNER_HEARTBEAT_COUNTS_LUA,
            "0",
        ],
        timeout=10,
    ).strip()
    try:
        payload = json.loads(output)
    except json.JSONDecodeError as exc:
        raise RuntimeError("runner_heartbeat_counts_invalid") from exc
    expected = {"count", "inflight", "capacity", "malformed"}
    if not isinstance(payload, dict) or set(payload) != expected:
        raise RuntimeError("runner_heartbeat_counts_invalid")
    if any(
        isinstance(payload[key], bool)
        or not isinstance(payload[key], int)
        or payload[key] < 0
        for key in expected
    ):
        raise RuntimeError("runner_heartbeat_counts_invalid")
    if payload["malformed"]:
        raise RuntimeError("runner_heartbeat_counts_malformed")
    return {key: int(payload[key]) for key in expected}


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
        runner_task_count = None
    else:
        try:
            database_workloads = active_database_workload_counts()
            meeting_count = database_workloads["active_meeting_sessions"]
            base_backup_count = database_workloads["active_postgres_base_backups"]
            runner_task_count = database_workloads["active_runner_tasks"]
        except Exception as exc:
            meeting_count = None
            base_backup_count = None
            runner_task_count = None
            errors.append(f"database_workload_inspection_failed:{type(exc).__name__}")
    try:
        runner_heartbeats = active_runner_heartbeat_counts()
    except Exception as exc:
        runner_heartbeats = {
            "count": None,
            "inflight": None,
            "capacity": None,
            "malformed": None,
        }
        errors.append(f"runner_heartbeat_inspection_failed:{type(exc).__name__}")
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
    if runner_task_count is not None and runner_task_count > 0:
        blocking_reasons.append("active_runner_tasks")
    if (
        runner_heartbeats["inflight"] is not None
        and runner_heartbeats["inflight"] > 0
    ):
        blocking_reasons.append("active_runner_inflight")
    if receivers["active"]:
        blocking_reasons.append("active_live_media_receivers")
    if errors:
        blocking_reasons.append("backup_runtime_admission_inspection_failed")
    return {
        "schema_version": "backup_runtime_admission.v3",
        "admitted": not blocking_reasons,
        "active_meeting_sessions": meeting_count,
        "active_postgres_base_backups": base_backup_count,
        "active_runner_tasks": runner_task_count,
        "active_runner_heartbeats": runner_heartbeats["count"],
        "active_runner_inflight": runner_heartbeats["inflight"],
        "active_runner_capacity": runner_heartbeats["capacity"],
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
