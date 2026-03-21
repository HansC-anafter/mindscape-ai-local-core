#!/usr/bin/env python3
"""
Trim oversized duplicated payloads from tasks.execution_context.

Default target is low-risk historical IG workflow rows:
- pack_id in ig_analyze_pinned_reference, ig_analyze_following
- terminal statuses
- older than N days

The script preserves workflow_result and only removes top-level duplicated
result/step_outputs/outputs when workflow_result already exists.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable, Sequence

from sqlalchemy import bindparam, text


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database.engine import engine_postgres_core


DEFAULT_PACK_IDS = (
    "ig_analyze_pinned_reference",
    "ig_analyze_following",
)
DEFAULT_STATUSES = (
    "succeeded",
    "failed",
    "cancelled_by_user",
)


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


def _build_conditions(older_than_days: int, workspace_id: str | None) -> tuple[str, dict]:
    conditions = [
        "execution_context IS NOT NULL",
        "pack_id IN :pack_ids",
        "status IN :statuses",
        "("
        "execution_context::jsonb ? 'conversation_state' "
        "OR (execution_context::jsonb ? 'workflow_result' AND ("
        "execution_context::jsonb ? 'result' "
        "OR execution_context::jsonb ? 'step_outputs' "
        "OR execution_context::jsonb ? 'outputs'"
        "))"
        ")",
    ]
    params: dict = {}
    if older_than_days > 0:
        conditions.append("created_at < now() - (:older_than_days * interval '1 day')")
        params["older_than_days"] = older_than_days
    if workspace_id:
        conditions.append("workspace_id = :workspace_id")
        params["workspace_id"] = workspace_id
    return " AND ".join(conditions), params


def _summary_query(where_clause: str):
    return text(
        f"""
        WITH candidates AS (
            SELECT
                id,
                workspace_id,
                pack_id,
                status,
                created_at,
                pg_column_size(execution_context) AS current_ctx_bytes,
                pg_column_size(
                    CASE
                        WHEN execution_context::jsonb ? 'workflow_result' THEN (
                            execution_context::jsonb
                            - 'result'
                            - 'step_outputs'
                            - 'outputs'
                            - 'conversation_state'
                        )::json
                        ELSE (
                            execution_context::jsonb
                            - 'conversation_state'
                        )::json
                    END
                ) AS trimmed_ctx_bytes
            FROM tasks
            WHERE {where_clause}
        )
        SELECT
            COUNT(*) AS row_count,
            COALESCE(SUM(current_ctx_bytes), 0)::bigint AS current_ctx_bytes,
            COALESCE(SUM(trimmed_ctx_bytes), 0)::bigint AS trimmed_ctx_bytes,
            COALESCE(SUM(current_ctx_bytes - trimmed_ctx_bytes), 0)::bigint AS reclaimable_ctx_bytes
        FROM candidates
        """
    ).bindparams(
        bindparam("pack_ids", expanding=True),
        bindparam("statuses", expanding=True),
    )


def _top_rows_query(where_clause: str):
    return text(
        f"""
        SELECT
            id,
            workspace_id,
            pack_id,
            status,
            created_at,
            pg_column_size(execution_context) AS current_ctx_bytes,
            pg_column_size(
                CASE
                    WHEN execution_context::jsonb ? 'workflow_result' THEN (
                        execution_context::jsonb
                        - 'result'
                        - 'step_outputs'
                        - 'outputs'
                        - 'conversation_state'
                    )::json
                    ELSE (
                        execution_context::jsonb
                        - 'conversation_state'
                    )::json
                END
            ) AS trimmed_ctx_bytes
        FROM tasks
        WHERE {where_clause}
        ORDER BY current_ctx_bytes DESC, created_at ASC
        LIMIT :sample_limit
        """
    ).bindparams(
        bindparam("pack_ids", expanding=True),
        bindparam("statuses", expanding=True),
    )


def _update_query(where_clause: str):
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
        UPDATE tasks AS t
        SET execution_context = CASE
            WHEN t.execution_context::jsonb ? 'workflow_result' THEN (
                t.execution_context::jsonb
                - 'result'
                - 'step_outputs'
                - 'outputs'
                - 'conversation_state'
            )::json
            ELSE (
                t.execution_context::jsonb
                - 'conversation_state'
            )::json
        END
        FROM batch
        WHERE t.id = batch.id
        RETURNING t.id
        """
    ).bindparams(
        bindparam("pack_ids", expanding=True),
        bindparam("statuses", expanding=True),
    )


def _print_summary(row) -> None:
    print(
        json.dumps(
            {
                "candidate_rows": int(row.row_count or 0),
                "current_ctx_bytes": int(row.current_ctx_bytes or 0),
                "trimmed_ctx_bytes": int(row.trimmed_ctx_bytes or 0),
                "reclaimable_ctx_bytes": int(row.reclaimable_ctx_bytes or 0),
                "current_ctx_human": _format_bytes(int(row.current_ctx_bytes or 0)),
                "trimmed_ctx_human": _format_bytes(int(row.trimmed_ctx_bytes or 0)),
                "reclaimable_ctx_human": _format_bytes(
                    int(row.reclaimable_ctx_bytes or 0)
                ),
            },
            indent=2,
        )
    )


def _rows_to_dicts(rows: Iterable) -> list[dict]:
    items: list[dict] = []
    for row in rows:
        current_ctx_bytes = int(row.current_ctx_bytes or 0)
        trimmed_ctx_bytes = int(row.trimmed_ctx_bytes or 0)
        items.append(
            {
                "id": row.id,
                "workspace_id": row.workspace_id,
                "pack_id": row.pack_id,
                "status": row.status,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "current_ctx_bytes": current_ctx_bytes,
                "trimmed_ctx_bytes": trimmed_ctx_bytes,
                "reclaimable_ctx_bytes": current_ctx_bytes - trimmed_ctx_bytes,
                "current_ctx_human": _format_bytes(current_ctx_bytes),
                "trimmed_ctx_human": _format_bytes(trimmed_ctx_bytes),
                "reclaimable_ctx_human": _format_bytes(
                    current_ctx_bytes - trimmed_ctx_bytes
                ),
            }
        )
    return items


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Trim duplicated heavy payloads from tasks.execution_context"
    )
    parser.add_argument(
        "--pack-id",
        action="append",
        dest="pack_ids",
        help="Target pack_id. Repeatable. Defaults to IG heavy packs.",
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
        default=1,
        help="Only touch rows older than this many days. Use 0 for all ages.",
    )
    parser.add_argument(
        "--workspace-id",
        default=None,
        help="Optional workspace_id filter.",
    )
    parser.add_argument(
        "--sample-limit",
        type=int,
        default=10,
        help="How many largest candidate rows to print in the summary.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=250,
        help="Rows to update per batch when --apply is set.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually update rows. Default is dry-run.",
    )
    parser.add_argument(
        "--vacuum-analyze",
        action="store_true",
        help="Run VACUUM ANALYZE tasks after apply.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if engine_postgres_core is None:
        print("PostgreSQL core engine is not initialized.", file=sys.stderr)
        return 2

    pack_ids = tuple(args.pack_ids or DEFAULT_PACK_IDS)
    statuses = tuple(args.statuses or DEFAULT_STATUSES)
    where_clause, extra_params = _build_conditions(
        older_than_days=args.older_than_days,
        workspace_id=args.workspace_id,
    )

    params = {
        "pack_ids": pack_ids,
        "statuses": statuses,
        **extra_params,
    }

    with engine_postgres_core.connect() as conn:
        summary_row = conn.execute(_summary_query(where_clause), params).fetchone()
        top_rows = conn.execute(
            _top_rows_query(where_clause),
            {**params, "sample_limit": args.sample_limit},
        ).fetchall()

    print(
        json.dumps(
            {
                "mode": "apply" if args.apply else "dry-run",
                "pack_ids": list(pack_ids),
                "statuses": list(statuses),
                "older_than_days": args.older_than_days,
                "workspace_id": args.workspace_id,
            },
            indent=2,
        )
    )
    if summary_row:
        _print_summary(summary_row)
    print(json.dumps({"largest_rows": _rows_to_dicts(top_rows)}, indent=2))

    if not args.apply:
        print("Dry run only. Re-run with --apply to update rows.")
        return 0

    total_updated = 0
    while True:
        with engine_postgres_core.begin() as conn:
            updated_rows = conn.execute(
                _update_query(where_clause),
                {**params, "batch_size": args.batch_size},
            ).fetchall()
        batch_count = len(updated_rows)
        total_updated += batch_count
        print(json.dumps({"batch_updated": batch_count, "total_updated": total_updated}))
        if batch_count < args.batch_size:
            break

    with engine_postgres_core.connect() as conn:
        post_row = conn.execute(_summary_query(where_clause), params).fetchone()
    print(json.dumps({"post_apply_summary": True}, indent=2))
    if post_row:
        _print_summary(post_row)

    if args.vacuum_analyze:
        with engine_postgres_core.connect().execution_options(
            isolation_level="AUTOCOMMIT"
        ) as conn:
            conn.execute(text("VACUUM ANALYZE tasks"))
        print("VACUUM ANALYZE tasks completed.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
