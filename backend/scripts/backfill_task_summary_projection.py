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


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill task_summary_projection from tasks.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Backfill only the latest N tasks.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    builder = TaskProjectionBuilder()
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
