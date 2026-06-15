#!/usr/bin/env python3
"""Reconcile non-terminal playbook execution status from linked tasks.

Default mode is dry-run. Apply mode requires an exact expected candidate count
so a changing live workload cannot silently widen the mutation set.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text


LOCAL_CORE_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = LOCAL_CORE_ROOT / "backend"
APP_ROOT = BACKEND_ROOT / "app"
for _path in (LOCAL_CORE_ROOT, BACKEND_ROOT, APP_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))


from backend.app.services.stores.tasks_store import TasksStore  # noqa: E402


RECONCILIATION_CTE = """
WITH candidate_executions AS (
    SELECT id, status AS current_status, updated_at AS current_updated_at
    FROM playbook_executions
    WHERE status NOT IN ('done', 'failed')
),
task_rollup AS (
    SELECT
        c.id,
        c.current_status,
        c.current_updated_at,
        COUNT(*) FILTER (WHERE t.status = 'running') AS running_count,
        COUNT(*) FILTER (WHERE t.status = 'pending') AS pending_count,
        COUNT(*) FILTER (WHERE t.status = 'succeeded') AS succeeded_count,
        COUNT(*) FILTER (
            WHERE t.status IN ('failed', 'cancelled_by_user', 'expired')
        ) AS failed_count
    FROM candidate_executions c
    JOIN tasks t ON t.execution_id = c.id
    GROUP BY c.id, c.current_status, c.current_updated_at
),
derived AS (
    SELECT
        id,
        current_status,
        current_updated_at,
        running_count,
        pending_count,
        succeeded_count,
        failed_count,
        CASE
            WHEN running_count > 0 THEN 'running'
            WHEN pending_count > 0 THEN 'queued'
            WHEN succeeded_count > 0 THEN 'done'
            WHEN failed_count > 0 THEN 'failed'
            ELSE NULL
        END AS target_status
    FROM task_rollup
),
mismatches AS (
    SELECT *
    FROM derived
    WHERE target_status IS NOT NULL
      AND current_status <> target_status
)
"""

LIST_QUERY = text(
    RECONCILIATION_CTE
    + """
    SELECT
        id,
        current_status,
        current_updated_at,
        target_status,
        running_count,
        pending_count,
        succeeded_count,
        failed_count
    FROM mismatches
    ORDER BY target_status, id
    """
)

UPDATE_QUERY = text(
    RECONCILIATION_CTE
    + """
    UPDATE playbook_executions p
    SET status = m.target_status,
        updated_at = :updated_at
    FROM mismatches m
    WHERE p.id = m.id
    RETURNING
        p.id,
        m.current_status,
        m.current_updated_at,
        m.target_status,
        m.running_count,
        m.pending_count,
        m.succeeded_count,
        m.failed_count
    """
)


def _row_dict(row: Any) -> dict[str, Any]:
    mapping = getattr(row, "_mapping", row)

    def value(key: str) -> Any:
        if hasattr(mapping, "__getitem__"):
            return mapping[key]
        return getattr(mapping, key)

    return {
        "id": str(value("id")),
        "current_status": str(value("current_status")),
        "current_updated_at": (
            value("current_updated_at").isoformat()
            if hasattr(value("current_updated_at"), "isoformat")
            else str(value("current_updated_at"))
        ),
        "target_status": str(value("target_status")),
        "running_count": int(value("running_count")),
        "pending_count": int(value("pending_count")),
        "succeeded_count": int(value("succeeded_count")),
        "failed_count": int(value("failed_count")),
    }


def load_candidates(store: Any) -> list[dict[str, Any]]:
    with store.get_connection() as conn:
        return [_row_dict(row) for row in conn.execute(LIST_QUERY).fetchall()]


def apply_reconciliation(
    store: Any,
    *,
    expected_count: int,
) -> list[dict[str, Any]]:
    with store.transaction() as conn:
        rows = [
            _row_dict(row)
            for row in conn.execute(
                UPDATE_QUERY,
                {"updated_at": datetime.now(timezone.utc)},
            ).fetchall()
        ]
        if len(rows) != expected_count:
            raise RuntimeError(
                "Candidate count changed during apply: "
                f"expected={expected_count} actual={len(rows)}"
            )
        return rows


def _report(mode: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for row in rows:
        target = row["target_status"]
        counts[target] = counts.get(target, 0) + 1
    return {
        "mode": mode,
        "candidate_count": len(rows),
        "target_counts": counts,
        "candidates": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist reconciliation. Default is dry-run.",
    )
    parser.add_argument(
        "--expected-count",
        type=int,
        help="Required with --apply; must equal the live mutation count.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        help="Optional path for the complete machine-readable report.",
    )
    args = parser.parse_args()
    if args.apply and args.expected_count is None:
        parser.error("--apply requires --expected-count")
    if args.expected_count is not None and args.expected_count < 0:
        parser.error("--expected-count must be non-negative")

    store = TasksStore()
    rows = (
        apply_reconciliation(store, expected_count=args.expected_count)
        if args.apply
        else load_candidates(store)
    )
    report = _report("apply" if args.apply else "dry-run", rows)
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(payload, encoding="utf-8")
    sys.stdout.write(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
