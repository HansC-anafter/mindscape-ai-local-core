#!/usr/bin/env python3
"""
Report IG batch-pin tasks whose latest run still appears short of target.

This does not mutate anything. It compares the latest ig_batch_pin_references
task per target handle against the current reference index count for that handle.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import create_engine, text


BACKEND_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = BACKEND_ROOT / "app"
for _path in (BACKEND_ROOT, APP_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))


from app.database.config import get_engine_kwargs, get_postgres_url_core
from capabilities.ig.services.workspace_storage import WorkspaceStorage


@dataclass(frozen=True)
class LatestBatchTask:
    task_id: str
    status: str
    created_at_taipei: str
    target_handle: str
    target_count: int
    source_mode: str
    user_data_dir: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Report rerun-worthy IG batch pin gaps for a workspace."
    )
    parser.add_argument("--workspace-id", required=True, help="Workspace ID")
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Max rows to print for rerun-worthy gaps.",
    )
    return parser.parse_args()


def load_latest_batch_tasks(workspace_id: str) -> list[LatestBatchTask]:
    engine = create_engine(get_postgres_url_core(), **get_engine_kwargs())
    query = text(
        """
        SELECT
            id::text AS task_id,
            status,
            to_char(created_at AT TIME ZONE 'Asia/Taipei', 'YYYY-MM-DD HH24:MI:SS') AS created_at_taipei,
            COALESCE(execution_context->'inputs'->>'target_handle', '') AS target_handle,
            COALESCE(NULLIF(execution_context->'inputs'->>'target_count', ''), '0')::int AS target_count,
            COALESCE(execution_context->'inputs'->>'source_mode', '') AS source_mode,
            COALESCE(execution_context->'inputs'->>'user_data_dir', '') AS user_data_dir
        FROM (
            SELECT DISTINCT ON (COALESCE(execution_context->'inputs'->>'target_handle', ''))
                id,
                status,
                created_at,
                execution_context
            FROM tasks
            WHERE workspace_id = :workspace_id
              AND pack_id = 'ig_batch_pin_references'
              AND COALESCE(execution_context->'inputs'->>'target_handle', '') <> ''
            ORDER BY COALESCE(execution_context->'inputs'->>'target_handle', ''), created_at DESC
        ) latest
        ORDER BY created_at_taipei DESC
        """
    )
    with engine.connect() as conn:
        rows = conn.execute(query, {"workspace_id": workspace_id}).mappings().all()
    return [
        LatestBatchTask(
            task_id=str(row["task_id"]),
            status=str(row["status"]),
            created_at_taipei=str(row["created_at_taipei"]),
            target_handle=str(row["target_handle"]),
            target_count=int(row["target_count"] or 0),
            source_mode=str(row["source_mode"] or ""),
            user_data_dir=str(row["user_data_dir"] or ""),
        )
        for row in rows
    ]


def build_current_ref_counts(workspace_id: str) -> dict[str, int]:
    storage = WorkspaceStorage(workspace_id, "ig")
    refs_path = storage.get_references_path()
    index_path = refs_path / "_index.json"
    if not index_path.exists():
        return {}

    import json

    data = json.loads(index_path.read_text(encoding="utf-8"))
    counts: dict[str, int] = {}
    for entry in (data.get("entries") or {}).values():
        if not isinstance(entry, dict):
            continue
        if entry.get("deleted"):
            continue
        handle = str(entry.get("source_handle") or "").strip().lstrip("@")
        if not handle:
            continue
        counts[handle] = counts.get(handle, 0) + 1
    return counts


def main() -> int:
    args = parse_args()
    latest_tasks = load_latest_batch_tasks(args.workspace_id)
    current_ref_counts = build_current_ref_counts(args.workspace_id)

    rerun_rows: list[tuple[LatestBatchTask, int, int]] = []
    latest_failed = 0
    latest_succeeded = 0
    for task in latest_tasks:
        current_refs = current_ref_counts.get(task.target_handle, 0)
        shortfall = max(0, task.target_count - current_refs)
        if task.status == "failed":
            latest_failed += 1
            if shortfall > 0:
                rerun_rows.append((task, current_refs, shortfall))
        elif task.status == "succeeded":
            latest_succeeded += 1

    rerun_rows.sort(key=lambda item: (-item[2], item[0].created_at_taipei, item[0].target_handle))

    print(
        f"workspace={args.workspace_id} "
        f"latest_handles={len(latest_tasks)} "
        f"latest_failed={latest_failed} "
        f"latest_succeeded={latest_succeeded} "
        f"rerun_worthy={len(rerun_rows)}"
    )
    for task, current_refs, shortfall in rerun_rows[: args.limit]:
        print(
            f"- handle=@{task.target_handle} "
            f"latest_task={task.task_id} "
            f"latest_status={task.status} "
            f"created_taipei={task.created_at_taipei} "
            f"target={task.target_count} "
            f"current_refs={current_refs} "
            f"shortfall={shortfall} "
            f"source_mode={task.source_mode}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
