#!/usr/bin/env python3
"""Read-only PostgreSQL runtime preflight report for physical reclaim gates."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = Path(__file__).resolve().parents[1]
for _path in (REPO_ROOT, BACKEND_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from backend.scripts.postgres_runtime_preflight.backup import (  # noqa: E402
    verify_backup as _backup_verification,
)
from backend.scripts.postgres_runtime_preflight.database_probe import (  # noqa: E402
    REQUIRED_EXTENSIONS,
    activity as _activity,
    hot_row_budget as _hot_row_budget,
    installed_extensions as _installed_extensions,
    mapping_all as _mapping_all,
    mapping_one as _mapping_one,
    pg_stat_statements_top as _pg_stat_statements_top,
    relation_sizes as _relation_sizes,
    runner_workload as _runner_workload,
    show_setting as _show_setting,
)
from backend.scripts.postgres_runtime_preflight.readiness import (  # noqa: E402
    evaluate_report,
)
from backend.scripts.postgres_runtime_preflight.runtime_environment import (  # noqa: E402
    compose_runtime_readiness as _compose_runtime_readiness,
    connection_budget as _connection_budget,
    filesystem_capacity as _filesystem_capacity,
    pg_repack_tool_status as _pg_repack_tool_status,
    script_path_status as _script_path_status,
)


DEFAULT_RELATIONS = ("tasks", "artifacts", "ig_accounts_flat")
SCHEMA_VERSION = 1
DEFAULT_CONNECTION_RESERVE = 20
DEFAULT_REPACK_FREE_SPACE_FACTOR = 1.2
DEFAULT_REPACK_FREE_SPACE_RESERVE = 1024 * 1024 * 1024


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00",
        "Z",
    )


def _get_engine():
    from app.database.engine import engine_postgres_core

    return engine_postgres_core


def _runner_claim_gate() -> dict[str, Any]:
    try:
        from backend.app.services.host_resources import get_runner_claim_gate

        gate = get_runner_claim_gate()
        if isinstance(gate, dict):
            return gate
        return {"error": "invalid_runner_claim_gate"}
    except Exception as exc:
        return {"error": str(exc)}


def _unavailable_database_report(
    args: argparse.Namespace,
    exc: Exception,
) -> dict[str, Any]:
    activity = {"error": "database_unavailable", "total_connections": 0}
    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _utc_now(),
        "mode": "read_only",
        "database": {
            "connectable": False,
            "connection_error": str(exc),
            "pg_is_in_recovery": None,
            "shared_preload_libraries": "",
            "max_connections": "",
            "wal_level": "",
            "archive_mode": "",
            "archive_command": "",
            "archiver": {
                "archived_count": 0,
                "last_archived_wal": "",
                "last_archived_time": None,
                "failed_count": 0,
                "last_failed_wal": "",
                "last_failed_time": None,
                "stats_reset": None,
            },
        },
        "extensions": {
            "required": list(REQUIRED_EXTENSIONS),
            "installed": [],
        },
        "tools": _pg_repack_tool_status(args.compose_file),
        "script_paths": _script_path_status(),
        "backup_verification": _backup_verification(
            args.verified_backup_dir,
            verification_mode=args.backup_verification_mode,
        ),
        "activity": activity,
        "connection_budget": _connection_budget(
            compose_file=args.compose_file,
            max_connections="",
            activity=activity,
            connection_reserve=args.connection_reserve,
        ),
        "runtime_readiness": _compose_runtime_readiness(args.compose_file),
        "relations": [],
        "filesystem": _filesystem_capacity(
            postgres_data_paths=args.postgres_data_path,
            relations=[],
            free_space_factor=args.repack_free_space_factor,
            free_space_reserve=args.repack_free_space_reserve,
        ),
        "runner_claim_gate": _runner_claim_gate(),
        "runner_workload": {"error": "database_unavailable"},
        "hot_row_budget": {
            "recent_hours": args.recent_hours,
            "limits": {
                "execution_context": args.execution_context_budget,
                "result": args.result_budget,
                "params": args.params_budget,
                "blocked_payload": args.blocked_payload_budget,
            },
            "sample": {},
        },
        "pg_stat_statements_top": [],
    }
    return evaluate_report(report)


def collect_report(args: argparse.Namespace) -> dict[str, Any]:
    engine = _get_engine()
    try:
        conn_ctx = engine.connect()
    except Exception as exc:
        return _unavailable_database_report(args, exc)

    with conn_ctx as conn:
        pg_is_in_recovery = bool(
            _mapping_one(conn, "SELECT pg_is_in_recovery() AS value").get("value")
        )
        shared_preload_libraries = _show_setting(conn, "shared_preload_libraries")
        max_connections = _show_setting(conn, "max_connections")
        wal_level = _show_setting(conn, "wal_level")
        archive_mode = _show_setting(conn, "archive_mode")
        archive_command = _show_setting(conn, "archive_command")
        archiver = _mapping_one(
            conn,
            """
            SELECT
                archived_count::bigint AS archived_count,
                COALESCE(last_archived_wal, '') AS last_archived_wal,
                last_archived_time,
                failed_count::bigint AS failed_count,
                COALESCE(last_failed_wal, '') AS last_failed_wal,
                last_failed_time,
                stats_reset
            FROM pg_stat_archiver
            """,
        )
        installed_extensions = _installed_extensions(conn)
        pg_stat_statements_installed = "pg_stat_statements" in installed_extensions

        activity = _activity(conn)
        relations = _relation_sizes(conn, args.relation or DEFAULT_RELATIONS)

        runner_workload = _runner_workload(conn)
        hot_row_budget_sample = _hot_row_budget(
            conn,
            recent_hours=args.recent_hours,
            execution_context_budget=args.execution_context_budget,
            result_budget=args.result_budget,
            params_budget=args.params_budget,
            blocked_payload_budget=args.blocked_payload_budget,
        )
        pg_stat_statements_top = _pg_stat_statements_top(
            conn,
            enabled=pg_stat_statements_installed,
            limit=args.statement_limit,
        )

    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _utc_now(),
        "mode": "read_only",
        "database": {
            "connectable": True,
            "pg_is_in_recovery": pg_is_in_recovery,
            "shared_preload_libraries": shared_preload_libraries,
            "max_connections": max_connections,
            "wal_level": wal_level,
            "archive_mode": archive_mode,
            "archive_command": archive_command,
            "archiver": archiver,
        },
        "extensions": {
            "required": list(REQUIRED_EXTENSIONS),
            "installed": sorted(installed_extensions),
        },
        "tools": _pg_repack_tool_status(args.compose_file),
        "script_paths": _script_path_status(),
        "backup_verification": _backup_verification(
            args.verified_backup_dir,
            verification_mode=args.backup_verification_mode,
        ),
        "activity": activity,
        "connection_budget": _connection_budget(
            compose_file=args.compose_file,
            max_connections=max_connections,
            activity=activity,
            connection_reserve=args.connection_reserve,
        ),
        "runtime_readiness": _compose_runtime_readiness(args.compose_file),
        "relations": relations,
        "filesystem": _filesystem_capacity(
            postgres_data_paths=args.postgres_data_path,
            relations=relations,
            free_space_factor=args.repack_free_space_factor,
            free_space_reserve=args.repack_free_space_reserve,
        ),
        "runner_claim_gate": _runner_claim_gate(),
        "runner_workload": runner_workload,
        "hot_row_budget": {
            "recent_hours": args.recent_hours,
            "limits": {
                "execution_context": args.execution_context_budget,
                "result": args.result_budget,
                "params": args.params_budget,
                "blocked_payload": args.blocked_payload_budget,
            },
            "sample": hot_row_budget_sample,
        },
        "pg_stat_statements_top": pg_stat_statements_top,
    }

    return evaluate_report(report)


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
    parser.add_argument("--execution-context-budget", type=int, default=16 * 1024)
    parser.add_argument("--result-budget", type=int, default=16 * 1024)
    parser.add_argument("--params-budget", type=int, default=16 * 1024)
    parser.add_argument("--blocked-payload-budget", type=int, default=16 * 1024)
    parser.add_argument("--statement-limit", type=int, default=10)
    parser.add_argument("--compose-file", type=Path)
    parser.add_argument(
        "--verified-backup-dir",
        type=Path,
        help="Completed backup directory with manifest.json for reclaim readiness.",
    )
    parser.add_argument(
        "--backup-verification-mode",
        choices=("manifest_checksum", "manifest_size"),
        default="manifest_checksum",
        help=(
            "Use manifest_checksum for full SHA256 verification, or manifest_size "
            "when a previously verified large backup only needs a fast recheck."
        ),
    )
    parser.add_argument(
        "--connection-reserve",
        type=int,
        default=DEFAULT_CONNECTION_RESERVE,
    )
    parser.add_argument("--postgres-data-path", type=Path, action="append", default=None)
    parser.add_argument(
        "--repack-free-space-factor",
        type=float,
        default=DEFAULT_REPACK_FREE_SPACE_FACTOR,
    )
    parser.add_argument(
        "--repack-free-space-reserve",
        type=int,
        default=DEFAULT_REPACK_FREE_SPACE_RESERVE,
    )
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
