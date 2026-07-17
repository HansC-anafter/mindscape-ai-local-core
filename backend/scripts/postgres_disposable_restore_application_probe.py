#!/usr/bin/env python3
"""Read-only application seam probe for a disposable PostgreSQL restore."""

from __future__ import annotations

import json

from sqlalchemy import text

from backend.app.database.engine import engine_postgres_core
from backend.app.services.stores.tasks_store import TasksStore


def main() -> int:
    if engine_postgres_core is None:
        raise RuntimeError("restore_probe_engine_unavailable")
    with engine_postgres_core.connect() as conn:
        transaction_read_only = conn.execute(
            text("SHOW transaction_read_only")
        ).scalar_one()
        source = (
            conn.execute(
                text(
                    """
                    SELECT id, workspace_id, COALESCE(execution_id, id) AS execution_id
                    FROM tasks
                    ORDER BY created_at DESC
                    LIMIT 1
                    """
                )
            )
            .mappings()
            .first()
        )
    if transaction_read_only != "on":
        raise RuntimeError("restore_probe_not_read_only")
    if source is None:
        raise RuntimeError("restore_probe_task_missing")
    task = TasksStore().get_progress_task_control(str(source["execution_id"]))
    if task is None or str(task.id) != str(source["id"]):
        raise RuntimeError("restore_probe_progress_read_failed")
    print(
        json.dumps(
            {
                "ok": True,
                "transaction_read_only": transaction_read_only,
                "latest_task_id": str(task.id),
                "workspace_id": str(task.workspace_id),
                "execution_id": str(task.execution_id or task.id),
                "task_status": str(task.status),
                "reader": "TasksStore.get_progress_task_control",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
