#!/usr/bin/env python3
"""
Enqueue rerun-worthy IG batch pin tasks for handles whose latest batch failed
and whose current reference count is still below target.

Default mode is dry-run.
"""

from __future__ import annotations

import argparse
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import create_engine, text


BACKEND_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = BACKEND_ROOT / "app"
for _path in (BACKEND_ROOT, APP_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))


from app.database.config import get_engine_kwargs, get_postgres_url_core
from backend.app.models.workspace import Task, TaskStatus
from backend.app.services.stores.tasks_store import TasksStore
from capabilities.ig.services.auto_analyze import (
    _build_visit_batch_pin_execution_context,
)
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
        description="Rerun latest failed IG batch pin tasks that still have reference gaps."
    )
    parser.add_argument("--workspace-id", required=True, help="Workspace ID")
    parser.add_argument("--limit", type=int, default=None, help="Only rerun the first N matches")
    parser.add_argument(
        "--min-shortfall",
        type=int,
        default=1,
        help="Only include handles with at least this many missing refs",
    )
    parser.add_argument("--apply", action="store_true", help="Actually enqueue reruns")
    parser.add_argument(
        "--sample-limit",
        type=int,
        default=30,
        help="How many sample rows to print",
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


def force_enqueue_batch_pin(
    *,
    workspace_id: str,
    target_handle: str,
    target_count: int,
    user_data_dir: str,
) -> str:
    tasks_store = TasksStore()
    execution_id = str(uuid.uuid4())
    task = Task(
        id=execution_id,
        workspace_id=workspace_id,
        message_id=str(uuid.uuid4()),
        execution_id=execution_id,
        parent_execution_id=None,
        pack_id="ig_batch_pin_references",
        task_type="playbook_execution",
        status=TaskStatus.PENDING,
        execution_context=_build_visit_batch_pin_execution_context(
            execution_id=execution_id,
            workspace_id=workspace_id,
            target_handle=target_handle,
            target_count=max(1, int(target_count)),
            user_data_dir=user_data_dir or "/app/data/ig-browser-profiles/default",
            parent_execution_id=None,
            source_handle=target_handle,
        ),
    )
    tasks_store.create_task(task)
    return execution_id


def select_rerun_candidates(
    *,
    workspace_id: str,
    min_shortfall: int,
) -> list[tuple[LatestBatchTask, int, int]]:
    latest_tasks = load_latest_batch_tasks(workspace_id)
    current_ref_counts = build_current_ref_counts(workspace_id)
    rerun_rows: list[tuple[LatestBatchTask, int, int]] = []
    for task in latest_tasks:
        if task.status != "failed":
            continue
        current_refs = current_ref_counts.get(task.target_handle, 0)
        shortfall = max(0, task.target_count - current_refs)
        if shortfall < min_shortfall:
            continue
        rerun_rows.append((task, current_refs, shortfall))
    rerun_rows.sort(key=lambda item: (-item[2], item[0].created_at_taipei, item[0].target_handle))
    return rerun_rows


def main() -> int:
    args = parse_args()
    rerun_rows = select_rerun_candidates(
        workspace_id=args.workspace_id,
        min_shortfall=max(1, int(args.min_shortfall)),
    )
    if args.limit is not None:
        rerun_rows = rerun_rows[: args.limit]

    print(
        f"workspace={args.workspace_id} "
        f"rerun_candidates={len(rerun_rows)} "
        f"min_shortfall={max(1, int(args.min_shortfall))}"
    )
    for task, current_refs, shortfall in rerun_rows[: args.sample_limit]:
        print(
            f"- handle=@{task.target_handle} "
            f"latest_task={task.task_id} "
            f"created_taipei={task.created_at_taipei} "
            f"target={task.target_count} current_refs={current_refs} shortfall={shortfall} "
            f"user_data_dir={task.user_data_dir or '/app/data/ig-browser-profiles/default'}"
        )

    if not args.apply:
        print("dry_run=true")
        return 0

    enqueued = 0
    skipped = 0
    for task, _current_refs, _shortfall in rerun_rows:
        execution_id = force_enqueue_batch_pin(
            workspace_id=args.workspace_id,
            target_handle=task.target_handle,
            user_data_dir=task.user_data_dir or "/app/data/ig-browser-profiles/default",
            target_count=task.target_count,
        )
        if execution_id:
            enqueued += 1
            print(f"  enqueued handle=@{task.target_handle} execution_id={execution_id}")
        else:
            skipped += 1
            print(f"  skipped handle=@{task.target_handle} reason=no_enqueue_result")

    print(f"dry_run=false total={len(rerun_rows)} enqueued={enqueued} skipped={skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
