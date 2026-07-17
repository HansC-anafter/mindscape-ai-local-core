"""Bounded PostgreSQL and PgBouncer release-budget collectors."""

from __future__ import annotations

import csv
import io
import json
import time
from typing import Any, Callable


RunCommand = Callable[[list[str], float], dict[str, Any]]


_POSTGRES_SQL = """
SELECT json_build_object(
  'in_recovery', pg_is_in_recovery(),
  'read_only', current_setting('transaction_read_only'),
  'wal_bytes', (SELECT wal_bytes::text FROM pg_stat_wal),
  'buffers_checkpoint', (SELECT buffers_checkpoint FROM pg_stat_bgwriter),
  'buffers_clean', (SELECT buffers_clean FROM pg_stat_bgwriter),
  'buffers_backend', (SELECT buffers_backend FROM pg_stat_bgwriter),
  'checkpoints_timed', (SELECT checkpoints_timed FROM pg_stat_bgwriter),
  'checkpoints_req', (SELECT checkpoints_req FROM pg_stat_bgwriter),
  'archived_count', (SELECT archived_count FROM pg_stat_archiver),
  'failed_count', (SELECT failed_count FROM pg_stat_archiver),
  'dead_tuples', (SELECT COALESCE(sum(n_dead_tup), 0) FROM pg_stat_user_tables),
  'hot_updates', (SELECT COALESCE(sum(n_tup_hot_upd), 0) FROM pg_stat_user_tables),
  'updates', (SELECT COALESCE(sum(n_tup_upd), 0) FROM pg_stat_user_tables),
  'autovacuum_count', (SELECT COALESCE(sum(autovacuum_count), 0) FROM pg_stat_user_tables),
  'last_autovacuum', (SELECT max(last_autovacuum) FROM pg_stat_user_tables),
  'wal_stats_reset', (SELECT stats_reset FROM pg_stat_wal),
  'bgwriter_stats_reset', (SELECT stats_reset FROM pg_stat_bgwriter),
  'invalid_indexes', (
    SELECT count(*) FROM pg_index WHERE NOT indisvalid OR NOT indisready
  ),
  'replication_lag_bytes', (
    SELECT COALESCE(max(pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn)), 0)::text
    FROM pg_stat_replication
  )
);
"""


def collect_postgres_metrics(
    run_command: RunCommand,
    timeout_seconds: float,
) -> dict[str, Any]:
    result = run_command(
        [
            "docker",
            "exec",
            "mindscape-ai-local-core-postgres",
            "psql",
            "-U",
            "mindscape",
            "-d",
            "mindscape_core",
            "-At",
            "-c",
            _POSTGRES_SQL,
        ],
        timeout_seconds,
    )
    if not result.get("ok"):
        return {"ok": False, "error_code": "postgres_metrics_unavailable"}
    try:
        metrics = json.loads(result.get("stdout", "").strip())
    except (TypeError, ValueError):
        return {"ok": False, "error_code": "postgres_metrics_invalid"}
    return {"ok": True, "metrics": metrics}


def collect_pgbouncer_metrics(
    run_command: RunCommand,
    timeout_seconds: float,
    *,
    sample_count: int = 1,
    sample_interval_seconds: float = 0,
    sleep=time.sleep,
) -> dict[str, Any]:
    normalized_count = max(1, int(sample_count))
    if normalized_count > 3:
        raise ValueError("pgbouncer_sample_count_must_not_exceed_3")
    interval = max(0.0, float(sample_interval_seconds))
    required_columns = {
        "database",
        "cl_active",
        "cl_waiting",
        "sv_active",
        "sv_idle",
        "sv_used",
        "sv_login",
        "maxwait",
        "maxwait_us",
    }
    rows = []
    for sample_index in range(normalized_count):
        result = run_command(
            [
                "docker",
                "exec",
                "mindscape-ai-local-core-pgbouncer",
                "sh",
                "-ec",
                'export PGPASSWORD="$POSTGRES_CORE_PASSWORD"; exec psql "$@"',
                "psql",
                "-h",
                "127.0.0.1",
                "-p",
                "6432",
                "-U",
                "mindscape",
                "-d",
                "pgbouncer",
                "--csv",
                "-c",
                "SHOW POOLS",
            ],
            timeout_seconds,
        )
        if not result.get("ok"):
            return {
                "ok": False,
                "error_code": "pgbouncer_metrics_unavailable",
                "sample_count": sample_index,
            }
        sample_rows = 0
        try:
            reader = csv.DictReader(io.StringIO(result.get("stdout", "")))
            if not reader.fieldnames or not required_columns.issubset(reader.fieldnames):
                return {
                    "ok": False,
                    "error_code": "pgbouncer_metrics_schema_invalid",
                    "sample_count": sample_index,
                }
            for source in reader:
                if source.get("database") not in {
                    "mindscape_core",
                    "mindscape_vectors",
                }:
                    continue
                rows.append(
                    {
                        "sample_index": sample_index + 1,
                        "database": source["database"],
                        "cl_active": int(source["cl_active"]),
                        "cl_waiting": int(source["cl_waiting"]),
                        "sv_active": int(source["sv_active"]),
                        "sv_idle": int(source["sv_idle"]),
                        "sv_used": int(source["sv_used"]),
                        "sv_login": int(source["sv_login"]),
                        "maxwait": int(source["maxwait"]),
                        "maxwait_us": int(source["maxwait_us"]),
                    }
                )
                sample_rows += 1
        except (KeyError, TypeError, ValueError, csv.Error):
            return {
                "ok": False,
                "error_code": "pgbouncer_metrics_invalid",
                "sample_count": sample_index,
            }
        if sample_rows == 0:
            return {
                "ok": False,
                "error_code": "pgbouncer_metrics_empty",
                "sample_count": sample_index + 1,
            }
        if sample_index + 1 < normalized_count and interval > 0:
            sleep(interval)
    return {
        "ok": bool(rows),
        "rows": rows,
        "sample_count": normalized_count,
        "sample_interval_seconds": interval,
    }
