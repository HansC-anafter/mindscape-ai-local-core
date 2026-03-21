#!/usr/bin/env python3
"""
Prune historical task rows under a conservative retention policy.

Default behavior is a dry-run against historical IG terminal tasks:
- pack_id LIKE 'ig_%' or 'ig.%' or 'ig/%'
- status in succeeded, failed, cancelled_by_user
- older than 30 days

Use --apply to delete rows in batches. Use --vacuum-analyze afterwards to
refresh planner stats, but note this does not reclaim TOAST files back to OS.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


DEFAULT_PACK_PATTERNS = ("ig_%", "ig.%", "ig/%")
DEFAULT_STATUSES = ("succeeded", "failed", "cancelled_by_user")


def _get_engine():
    from app.database.engine import engine_postgres_core

    return engine_postgres_core


def _sqlalchemy():
    from sqlalchemy import bindparam, text

    return bindparam, text


def _format_bytes(num: int | None) -> str:
    if num is None:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(num)
    for unit in units:
        if value < 1024.0 or unit == units[-1]:
            return f"{value:.2f} {unit}"
        value /= 1024.0
    return f"{num} B"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prune historical task rows under a retention policy"
    )
    parser.add_argument(
        "--pack-pattern",
        action="append",
        dest="pack_patterns",
        help=(
            "SQL LIKE pattern for target pack_id. Repeatable. "
            "Defaults to IG patterns."
        ),
    )
    parser.add_argument(
        "--pack-id",
        action="append",
        dest="pack_ids",
        help="Exact target pack_id. Repeatable.",
    )
    parser.add_argument(
        "--status",
        action="append",
        dest="statuses",
        help="Target status. Repeatable. Defaults to terminal statuses.",
    )
    parser.add_argument(
        "--older-than-days",
        type=int,
        default=30,
        help="Only delete rows older than this many days. Default: 30.",
    )
    parser.add_argument(
        "--workspace-id",
        default=None,
        help="Optional workspace filter.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="Delete rows in batches of this size when --apply is set.",
    )
    parser.add_argument(
        "--sample-limit",
        type=int,
        default=25,
        help="How many grouped rows to print in the dry-run summary.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually delete rows. Default is dry-run only.",
    )
    parser.add_argument(
        "--vacuum-analyze",
        action="store_true",
        help="Run VACUUM ANALYZE tasks after deletion.",
    )
    return parser.parse_args(argv)


def _build_where_clause(args: argparse.Namespace) -> tuple[str, dict[str, Any]]:
    conditions = []
    params: dict[str, Any] = {}

    pack_clauses = []
    pack_patterns = tuple(args.pack_patterns or DEFAULT_PACK_PATTERNS)
    for idx, pattern in enumerate(pack_patterns):
        key = f"pack_pattern_{idx}"
        pack_clauses.append(f"pack_id LIKE :{key}")
        params[key] = pattern

    pack_ids = tuple(args.pack_ids or ())
    if pack_ids:
        pack_clauses.append("pack_id IN :pack_ids")
        params["pack_ids"] = pack_ids

    if pack_clauses:
        conditions.append("(" + " OR ".join(pack_clauses) + ")")

    statuses = tuple(args.statuses or DEFAULT_STATUSES)
    conditions.append("status IN :statuses")
    params["statuses"] = statuses

    if args.older_than_days > 0:
        conditions.append(
            "created_at < now() - (:older_than_days * interval '1 day')"
        )
        params["older_than_days"] = args.older_than_days

    if args.workspace_id:
        conditions.append("workspace_id = :workspace_id")
        params["workspace_id"] = args.workspace_id

    return " AND ".join(conditions), params


def _bind_expanding(query, params: dict[str, Any]):
    bindparam, _ = _sqlalchemy()
    bind_names = []
    if "statuses" in params:
        bind_names.append(bindparam("statuses", expanding=True))
    if "pack_ids" in params:
        bind_names.append(bindparam("pack_ids", expanding=True))
    if bind_names:
        query = query.bindparams(*bind_names)
    return query


def _summary_query(where_clause: str):
    _, text = _sqlalchemy()
    return text(
        f"""
        SELECT
            COUNT(*) AS row_count,
            COALESCE(SUM(pg_column_size(execution_context)), 0)::bigint AS execution_context_bytes,
            COALESCE(SUM(pg_column_size(result)), 0)::bigint AS result_bytes
        FROM tasks
        WHERE {where_clause}
        """
    )


def _grouped_rows_query(where_clause: str):
    _, text = _sqlalchemy()
    return text(
        f"""
        SELECT
            pack_id,
            status,
            COUNT(*) AS row_count,
            MIN(created_at) AS oldest,
            MAX(created_at) AS newest,
            COALESCE(SUM(pg_column_size(execution_context)), 0)::bigint AS execution_context_bytes,
            COALESCE(SUM(pg_column_size(result)), 0)::bigint AS result_bytes
        FROM tasks
        WHERE {where_clause}
        GROUP BY pack_id, status
        ORDER BY MIN(created_at) ASC, pack_id ASC, status ASC
        LIMIT :sample_limit
        """
    )


def _delete_batch_query(where_clause: str):
    _, text = _sqlalchemy()
    return text(
        f"""
        WITH batch AS (
            SELECT id
            FROM tasks
            WHERE {where_clause}
            ORDER BY created_at ASC
            LIMIT :batch_size
            FOR UPDATE
        )
        DELETE FROM tasks AS t
        USING batch
        WHERE t.id = batch.id
        RETURNING
            t.id,
            t.pack_id,
            t.status,
            pg_column_size(t.execution_context)::bigint AS execution_context_bytes,
            pg_column_size(t.result)::bigint AS result_bytes
        """
    )


def _table_size_query():
    _, text = _sqlalchemy()
    return text(
        """
        SELECT
            pg_total_relation_size('tasks')::bigint AS total_bytes,
            pg_relation_size('tasks')::bigint AS table_bytes,
            pg_total_relation_size(reltoastrelid)::bigint AS toast_bytes
        FROM pg_class
        WHERE relname = 'tasks'
        """
    )


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, default=str))


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    where_clause, params = _build_where_clause(args)
    engine = _get_engine()

    summary_query = _bind_expanding(_summary_query(where_clause), params)
    grouped_query = _bind_expanding(_grouped_rows_query(where_clause), params)
    delete_query = _bind_expanding(_delete_batch_query(where_clause), params)

    with engine.begin() as conn:
        before_size = conn.execute(_table_size_query()).mappings().first()
        summary = conn.execute(summary_query, params).mappings().first()
        grouped_rows = conn.execute(
            grouped_query,
            {
                **params,
                "sample_limit": args.sample_limit,
            },
        ).mappings()

    payload: dict[str, Any] = {
        "mode": "apply" if args.apply else "dry-run",
        "filters": {
            "pack_patterns": list(args.pack_patterns or DEFAULT_PACK_PATTERNS),
            "pack_ids": list(args.pack_ids or ()),
            "statuses": list(args.statuses or DEFAULT_STATUSES),
            "older_than_days": args.older_than_days,
            "workspace_id": args.workspace_id,
        },
        "before_table_size": {
            "total": _format_bytes(int(before_size["total_bytes"] or 0)),
            "table": _format_bytes(int(before_size["table_bytes"] or 0)),
            "toast": _format_bytes(int(before_size["toast_bytes"] or 0)),
        },
        "candidate_rows": int(summary["row_count"] or 0),
        "candidate_execution_context": _format_bytes(
            int(summary["execution_context_bytes"] or 0)
        ),
        "candidate_result": _format_bytes(int(summary["result_bytes"] or 0)),
        "grouped_rows": [dict(row) for row in grouped_rows],
    }

    if not args.apply:
        _print_json(payload)
        return 0

    deleted_rows = 0
    deleted_execution_context_bytes = 0
    deleted_result_bytes = 0

    while True:
        with engine.begin() as conn:
            batch = conn.execute(
                delete_query,
                {
                    **params,
                    "batch_size": args.batch_size,
                },
            ).mappings().all()
        if not batch:
            break
        deleted_rows += len(batch)
        deleted_execution_context_bytes += sum(
            int(row["execution_context_bytes"] or 0) for row in batch
        )
        deleted_result_bytes += sum(int(row["result_bytes"] or 0) for row in batch)

    if args.vacuum_analyze:
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.execute(text("VACUUM ANALYZE tasks"))

    with engine.begin() as conn:
        after_size = conn.execute(_table_size_query()).mappings().first()

    payload["deleted_rows"] = deleted_rows
    payload["deleted_execution_context"] = _format_bytes(
        deleted_execution_context_bytes
    )
    payload["deleted_result"] = _format_bytes(deleted_result_bytes)
    payload["after_table_size"] = {
        "total": _format_bytes(int(after_size["total_bytes"] or 0)),
        "table": _format_bytes(int(after_size["table_bytes"] or 0)),
        "toast": _format_bytes(int(after_size["toast_bytes"] or 0)),
    }
    payload["notes"] = [
        "VACUUM ANALYZE updates planner stats but does not reclaim TOAST files back to the OS.",
        "Use pg_repack or VACUUM FULL tasks for physical size reclaim after large deletes.",
    ]
    _print_json(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
