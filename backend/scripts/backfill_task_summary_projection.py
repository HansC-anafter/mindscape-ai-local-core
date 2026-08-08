"""Backfill task summary projection rows from task control fields."""

from __future__ import annotations

import argparse
import json
from sqlalchemy import text

from backend.app.services.task_projection_builder import TaskProjectionBuilder


def _count_projection_rows(builder: TaskProjectionBuilder) -> int:
    with builder.get_connection() as conn:
        row = conn.execute(
            text("SELECT COUNT(*) AS count FROM task_summary_projection")
        ).fetchone()
        return int(row.count if row is not None else 0)


def _parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill task_summary_projection from tasks.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Backfill the latest N tasks or inspect at most N active drift rows.",
    )
    parser.add_argument(
        "--reconcile-active",
        action="store_true",
        help="Inspect active task/projection drift instead of running a full backfill.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply bounded active reconciliation; default reconcile mode is dry-run.",
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)
    if args.apply and not args.reconcile_active:
        raise SystemExit("--apply requires --reconcile-active")
    builder = TaskProjectionBuilder()
    if args.reconcile_active:
        try:
            result = builder.reconcile_active_task_summary_projection(
                limit=args.limit if args.limit is not None else 1000,
                apply=args.apply,
            )
        except Exception as exc:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "error_code": "active_projection_reconciliation_failed",
                        "error_type": type(exc).__name__,
                        "mode": "apply" if args.apply else "dry_run",
                    },
                    sort_keys=True,
                )
            )
            return 2
        print(json.dumps({"ok": True, **result}, sort_keys=True))
        return 0

    before_count = _count_projection_rows(builder)
    affected_rows = builder.rebuild_task_summary_projection(limit=args.limit)
    after_count = _count_projection_rows(builder)
    print(
        json.dumps(
            {
                "affected_rows": affected_rows,
                "projection_rows_before": before_count,
                "projection_rows_after": after_count,
                "limit": args.limit,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
