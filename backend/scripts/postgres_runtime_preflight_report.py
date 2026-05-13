#!/usr/bin/env python3
"""Read-only PostgreSQL runtime preflight report for physical reclaim gates."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from sqlalchemy import text


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = Path(__file__).resolve().parents[1]
for _path in (REPO_ROOT, BACKEND_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))


SCHEMA_VERSION = 1
DEFAULT_RELATIONS = ("tasks", "artifacts", "ig_accounts_flat")
REQUIRED_EXTENSIONS = ("pg_repack", "pg_stat_statements")
SCRIPT_PATHS = {
    "backup_job": "scripts/local_runtime_backup_job.py",
    "backup_verify": "scripts/verify_local_runtime_backup.sh",
    "legacy_compaction": "scripts/maintenance/compact_legacy_task_workflow_results.py",
    "retention_prune": "backend/scripts/prune_tasks_retention.py",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00",
        "Z",
    )


def _format_bytes(value: Any) -> str:
    try:
        size = float(value or 0)
    except (TypeError, ValueError):
        size = 0.0
    units = ("B", "KB", "MB", "GB", "TB")
    for unit in units:
        if size < 1024.0 or unit == units[-1]:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{int(value or 0)} B"


def _get_engine():
    from app.database.engine import engine_postgres_core

    return engine_postgres_core


def _mapping_one(
    conn,
    sql: str,
    params: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    row = conn.execute(text(sql), dict(params or {})).mappings().first()
    return dict(row or {})


def _mapping_all(
    conn,
    sql: str,
    params: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in conn.execute(text(sql), dict(params or {})).mappings()
    ]


def _show_setting(conn, name: str) -> str:
    row = conn.execute(text(f"SHOW {name}")).first()
    if not row:
        return ""
    return str(row[0] or "")


def _split_preload_libraries(value: str) -> set[str]:
    return {
        item.strip()
        for item in str(value or "").split(",")
        if item.strip()
    }


def _relation_sizes(conn, relations: Iterable[str]) -> list[dict[str, Any]]:
    rows = _mapping_all(
        conn,
        """
        SELECT
            relname,
            pg_total_relation_size(relid)::bigint AS total_bytes,
            pg_relation_size(relid)::bigint AS heap_bytes,
            pg_indexes_size(relid)::bigint AS index_bytes,
            (
                pg_total_relation_size(relid)
                - pg_relation_size(relid)
                - pg_indexes_size(relid)
            )::bigint AS toast_bytes
        FROM pg_catalog.pg_statio_user_tables
        WHERE relname = ANY(:relations)
        ORDER BY pg_total_relation_size(relid) DESC
        """,
        {"relations": list(relations)},
    )
    for row in rows:
        for key in ("total_bytes", "heap_bytes", "index_bytes", "toast_bytes"):
            row[f"{key}_pretty"] = _format_bytes(row.get(key))
    return rows


def _hot_row_budget(
    conn,
    *,
    recent_hours: int,
    execution_context_budget: int,
    result_budget: int,
    params_budget: int,
) -> dict[str, Any]:
    return _mapping_one(
        conn,
        """
        SELECT
            COUNT(*)::bigint AS recent_rows,
            COUNT(*) FILTER (
                WHERE octet_length(coalesce(execution_context::text, ''))
                      > :execution_context_budget
            )::bigint AS execution_context_over_budget,
            COUNT(*) FILTER (
                WHERE octet_length(coalesce(result::text, '')) > :result_budget
            )::bigint AS result_over_budget,
            COUNT(*) FILTER (
                WHERE octet_length(coalesce(params::text, '')) > :params_budget
            )::bigint AS params_over_budget,
            COALESCE(MAX(octet_length(coalesce(execution_context::text, ''))), 0)::bigint
                AS max_execution_context_bytes,
            COALESCE(MAX(octet_length(coalesce(result::text, ''))), 0)::bigint
                AS max_result_bytes,
            COALESCE(MAX(octet_length(coalesce(params::text, ''))), 0)::bigint
                AS max_params_bytes
        FROM tasks
        WHERE created_at >= now() - (:recent_hours * interval '1 hour')
        """,
        {
            "recent_hours": recent_hours,
            "execution_context_budget": execution_context_budget,
            "result_budget": result_budget,
            "params_budget": params_budget,
        },
    )


def _activity(conn) -> dict[str, Any]:
    states = _mapping_all(
        conn,
        """
        SELECT state, COUNT(*)::bigint AS count
        FROM pg_stat_activity
        GROUP BY state
        ORDER BY state NULLS FIRST
        """,
    )
    state_counts = {
        str(row.get("state") or "backend"): int(row.get("count") or 0)
        for row in states
    }
    idle_in_transaction = int(state_counts.get("idle in transaction", 0))
    samples = _mapping_all(
        conn,
        """
        SELECT
            datname,
            application_name,
            state,
            wait_event_type,
            COUNT(*)::bigint AS count
        FROM pg_stat_activity
        GROUP BY datname, application_name, state, wait_event_type
        ORDER BY count DESC, state NULLS FIRST, application_name
        LIMIT 20
        """,
    )
    return {
        "state_counts": state_counts,
        "idle_in_transaction": idle_in_transaction,
        "samples": samples,
    }


def _installed_extensions(conn) -> set[str]:
    rows = _mapping_all(
        conn,
        """
        SELECT extname
        FROM pg_extension
        WHERE extname = ANY(:extensions)
        ORDER BY extname
        """,
        {"extensions": list(REQUIRED_EXTENSIONS)},
    )
    return {str(row["extname"]) for row in rows if row.get("extname")}


def _pg_stat_statements_top(conn, *, enabled: bool, limit: int) -> list[dict[str, Any]]:
    if not enabled:
        return []
    try:
        return _mapping_all(
            conn,
            """
            SELECT
                queryid,
                calls,
                total_exec_time,
                mean_exec_time,
                rows,
                left(query, 500) AS query
            FROM pg_stat_statements
            ORDER BY total_exec_time DESC
            LIMIT :limit
            """,
            {"limit": limit},
        )
    except Exception as exc:
        return [{"error": str(exc)}]


def collect_report(args: argparse.Namespace) -> dict[str, Any]:
    engine = _get_engine()
    with engine.connect() as conn:
        pg_is_in_recovery = bool(
            _mapping_one(conn, "SELECT pg_is_in_recovery() AS value").get("value")
        )
        shared_preload_libraries = _show_setting(conn, "shared_preload_libraries")
        max_connections = _show_setting(conn, "max_connections")
        installed_extensions = _installed_extensions(conn)
        pg_stat_statements_installed = "pg_stat_statements" in installed_extensions

        report = {
            "schema_version": SCHEMA_VERSION,
            "generated_at": _utc_now(),
            "mode": "read_only",
            "database": {
                "pg_is_in_recovery": pg_is_in_recovery,
                "shared_preload_libraries": shared_preload_libraries,
                "max_connections": max_connections,
            },
            "extensions": {
                "required": list(REQUIRED_EXTENSIONS),
                "installed": sorted(installed_extensions),
            },
            "tools": {
                "pg_repack_binary": shutil.which("pg_repack"),
            },
            "script_paths": {
                key: {
                    "path": value,
                    "exists": (REPO_ROOT / value).is_file(),
                }
                for key, value in SCRIPT_PATHS.items()
            },
            "activity": _activity(conn),
            "relations": _relation_sizes(conn, args.relation or DEFAULT_RELATIONS),
            "hot_row_budget": {
                "recent_hours": args.recent_hours,
                "limits": {
                    "execution_context": args.execution_context_budget,
                    "result": args.result_budget,
                    "params": args.params_budget,
                },
                "sample": _hot_row_budget(
                    conn,
                    recent_hours=args.recent_hours,
                    execution_context_budget=args.execution_context_budget,
                    result_budget=args.result_budget,
                    params_budget=args.params_budget,
                ),
            },
            "pg_stat_statements_top": _pg_stat_statements_top(
                conn,
                enabled=pg_stat_statements_installed,
                limit=args.statement_limit,
            ),
        }

    return evaluate_report(report)


def _has_preload(report: Mapping[str, Any], library: str) -> bool:
    database = report.get("database") if isinstance(report.get("database"), dict) else {}
    preload = str(database.get("shared_preload_libraries") or "")
    return library in _split_preload_libraries(preload)


def evaluate_report(report: dict[str, Any]) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []

    database = report.get("database") if isinstance(report.get("database"), dict) else {}
    if database.get("pg_is_in_recovery") is not False:
        blockers.append("database_in_recovery")

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
    }
    if any(count > 0 for count in over_budget.values()):
        blockers.append("recent_hot_rows_over_budget")

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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a read-only PostgreSQL runtime preflight report"
    )
    parser.add_argument(
        "--relation",
        action="append",
        default=None,
        help="Relation name to include in size sampling. Repeatable.",
    )
    parser.add_argument("--recent-hours", type=int, default=24)
    parser.add_argument("--execution-context-budget", type=int, default=512 * 1024)
    parser.add_argument("--result-budget", type=int, default=256 * 1024)
    parser.add_argument("--params-budget", type=int, default=512 * 1024)
    parser.add_argument("--statement-limit", type=int, default=10)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--pretty", action="store_true")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with code 2 when blockers are present.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    report = collect_report(args)
    output = json.dumps(
        report,
        indent=2 if args.pretty else None,
        sort_keys=True,
        default=str,
    )
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(output + "\n", encoding="utf-8")
    print(output)
    if args.strict and report["readiness"]["blockers"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
