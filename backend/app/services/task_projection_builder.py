"""Task control-plane projection builder."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text

from app.services.stores.postgres_base import PostgresStoreBase
from backend.app.services.task_projection_adapters import build_task_display_inputs
from backend.app.services.task_projection_reconciliation import (
    apply_active_projection_reconciliation_budget,
    delete_orphan_task_projections,
    load_active_projection_drift_rows,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _mapping(value) -> dict:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except ValueError:
            return {}
        return dict(parsed) if isinstance(parsed, Mapping) else {}
    return {}


class TaskProjectionBuilder(PostgresStoreBase):
    """Build compact read models from task control fields and events."""

    def upsert_task_summary_from_task_id(
        self,
        task_id: str,
        *,
        conn=None,
        refresh_compact_inputs: bool = False,
    ) -> bool:
        if conn is None and refresh_compact_inputs:
            with self.transaction() as owned_conn:
                return self.upsert_task_summary_from_task_id(
                    task_id,
                    conn=owned_conn,
                    refresh_compact_inputs=True,
                )
        compact_inputs: dict = {}
        active_conn = conn
        if refresh_compact_inputs:

            def _load(source_conn):
                row = source_conn.execute(
                    text(
                        """
                        SELECT id, workspace_id, pack_id, params, execution_context, created_at
                        FROM tasks
                        WHERE id = :task_id
                        """
                    ),
                    {"task_id": task_id},
                ).mappings().first()
                if row is None:
                    return {}
                task = dict(row)
                task["params"] = _mapping(task.get("params"))
                task["execution_context"] = _mapping(task.get("execution_context"))
                return build_task_display_inputs(task=task)

            if active_conn is not None:
                compact_inputs = _load(active_conn)
        params = {
            "task_id": task_id,
            "updated_at": _utc_now(),
            "compact_inputs": json.dumps(compact_inputs, ensure_ascii=False),
            "refresh_compact_inputs": bool(refresh_compact_inputs),
        }
        query = text(
            f"""
            INSERT INTO task_summary_projection (
                task_id,
                workspace_id,
                execution_id,
                parent_execution_id,
                project_id,
                pack_id,
                task_type,
                status,
                queue_shard,
                priority,
                dedupe_key,
                summary,
                error_summary,
                compact_inputs,
                created_at,
                next_eligible_at,
                blocked_reason,
                frontier_state,
                frontier_enqueued_at,
                started_at,
                completed_at,
                updated_at,
                last_event_at,
                schema_version
            )
            SELECT
                tasks.id,
                tasks.workspace_id,
                tasks.execution_id,
                tasks.parent_execution_id,
                tasks.project_id,
                tasks.pack_id,
                tasks.task_type,
                tasks.status,
                tasks.queue_shard,
                0,
                tasks.concurrency_key,
                NULL,
                tasks.error,
                CAST(:compact_inputs AS JSONB),
                tasks.created_at,
                tasks.next_eligible_at,
                tasks.blocked_reason,
                tasks.frontier_state,
                tasks.frontier_enqueued_at,
                tasks.started_at,
                tasks.completed_at,
                :updated_at,
                COALESCE(
                    (
                        SELECT MAX(task_events.occurred_at)
                        FROM task_events
                        WHERE task_events.task_id = tasks.id
                    ),
                    :updated_at
                ),
                1
            FROM tasks
            WHERE tasks.id = :task_id
            ON CONFLICT (task_id)
            DO UPDATE SET
                workspace_id = EXCLUDED.workspace_id,
                execution_id = EXCLUDED.execution_id,
                parent_execution_id = EXCLUDED.parent_execution_id,
                project_id = EXCLUDED.project_id,
                pack_id = EXCLUDED.pack_id,
                task_type = EXCLUDED.task_type,
                status = EXCLUDED.status,
                queue_shard = EXCLUDED.queue_shard,
                priority = EXCLUDED.priority,
                dedupe_key = EXCLUDED.dedupe_key,
                summary = EXCLUDED.summary,
                error_summary = EXCLUDED.error_summary,
                compact_inputs = CASE
                    WHEN :refresh_compact_inputs
                    THEN EXCLUDED.compact_inputs
                    ELSE task_summary_projection.compact_inputs
                END,
                created_at = EXCLUDED.created_at,
                next_eligible_at = EXCLUDED.next_eligible_at,
                blocked_reason = EXCLUDED.blocked_reason,
                frontier_state = EXCLUDED.frontier_state,
                frontier_enqueued_at = EXCLUDED.frontier_enqueued_at,
                started_at = EXCLUDED.started_at,
                completed_at = EXCLUDED.completed_at,
                updated_at = EXCLUDED.updated_at,
                last_event_at = EXCLUDED.last_event_at,
                schema_version = EXCLUDED.schema_version
            """
        )
        if active_conn is not None:
            result = active_conn.execute(query, params)
            return result.rowcount > 0
        with self.transaction() as owned_conn:
            result = owned_conn.execute(query, params)
            return result.rowcount > 0

    def append_workspace_run_feed(
        self,
        *,
        feed_id: str,
        workspace_id: str,
        run_id: str,
        task_id: Optional[str],
        execution_id: Optional[str],
        pack_id: Optional[str],
        status: str,
        summary: Optional[str] = None,
        occurred_at: Optional[datetime] = None,
        conn=None,
    ) -> str:
        params = {
            "feed_id": feed_id,
            "workspace_id": workspace_id,
            "run_id": run_id,
            "task_id": task_id,
            "execution_id": execution_id,
            "pack_id": pack_id,
            "status": status,
            "summary": summary,
            "occurred_at": occurred_at or _utc_now(),
        }
        query = text(
            """
            INSERT INTO workspace_run_feed (
                feed_id,
                workspace_id,
                run_id,
                task_id,
                execution_id,
                pack_id,
                status,
                summary,
                occurred_at
            )
            VALUES (
                :feed_id,
                :workspace_id,
                :run_id,
                :task_id,
                :execution_id,
                :pack_id,
                :status,
                :summary,
                :occurred_at
            )
            ON CONFLICT (feed_id) DO NOTHING
            """
        )
        active_conn = conn
        if active_conn is not None:
            active_conn.execute(query, params)
            return feed_id
        with self.transaction() as owned_conn:
            owned_conn.execute(query, params)
        return feed_id

    def rebuild_task_summary_projection(
        self,
        *,
        limit: Optional[int] = None,
        conn=None,
    ) -> int:
        params = {"updated_at": _utc_now()}
        limit_clause = ""
        if limit is not None:
            params["limit"] = max(1, int(limit))
            limit_clause = "LIMIT :limit"
        query = text(
            f"""
            WITH source_tasks AS (
                SELECT id
                FROM tasks
                ORDER BY created_at DESC, id DESC
                {limit_clause}
            )
            INSERT INTO task_summary_projection (
                task_id,
                workspace_id,
                execution_id,
                parent_execution_id,
                project_id,
                pack_id,
                task_type,
                status,
                queue_shard,
                priority,
                dedupe_key,
                summary,
                error_summary,
                compact_inputs,
                created_at,
                next_eligible_at,
                blocked_reason,
                frontier_state,
                frontier_enqueued_at,
                started_at,
                completed_at,
                updated_at,
                last_event_at,
                schema_version
            )
            SELECT
                tasks.id,
                tasks.workspace_id,
                tasks.execution_id,
                tasks.parent_execution_id,
                tasks.project_id,
                tasks.pack_id,
                tasks.task_type,
                tasks.status,
                tasks.queue_shard,
                0,
                tasks.concurrency_key,
                NULL,
                tasks.error,
                COALESCE(
                    (
                        SELECT existing.compact_inputs
                        FROM task_summary_projection AS existing
                        WHERE existing.task_id = tasks.id
                    ),
                    '{{}}'::jsonb
                ),
                tasks.created_at,
                tasks.next_eligible_at,
                tasks.blocked_reason,
                tasks.frontier_state,
                tasks.frontier_enqueued_at,
                tasks.started_at,
                tasks.completed_at,
                :updated_at,
                COALESCE(
                    (
                        SELECT MAX(task_events.occurred_at)
                        FROM task_events
                        WHERE task_events.task_id = tasks.id
                    ),
                    :updated_at
                ),
                1
            FROM tasks
            JOIN source_tasks ON source_tasks.id = tasks.id
            ON CONFLICT (task_id)
            DO UPDATE SET
                workspace_id = EXCLUDED.workspace_id,
                execution_id = EXCLUDED.execution_id,
                parent_execution_id = EXCLUDED.parent_execution_id,
                project_id = EXCLUDED.project_id,
                pack_id = EXCLUDED.pack_id,
                task_type = EXCLUDED.task_type,
                status = EXCLUDED.status,
                queue_shard = EXCLUDED.queue_shard,
                priority = EXCLUDED.priority,
                dedupe_key = EXCLUDED.dedupe_key,
                summary = EXCLUDED.summary,
                error_summary = EXCLUDED.error_summary,
                compact_inputs = task_summary_projection.compact_inputs,
                created_at = EXCLUDED.created_at,
                next_eligible_at = EXCLUDED.next_eligible_at,
                blocked_reason = EXCLUDED.blocked_reason,
                frontier_state = EXCLUDED.frontier_state,
                frontier_enqueued_at = EXCLUDED.frontier_enqueued_at,
                started_at = EXCLUDED.started_at,
                completed_at = EXCLUDED.completed_at,
                updated_at = EXCLUDED.updated_at,
                last_event_at = EXCLUDED.last_event_at,
                schema_version = EXCLUDED.schema_version
            """
        )
        active_conn = conn
        if active_conn is not None:
            result = active_conn.execute(query, params)
            return int(result.rowcount or 0)
        with self.transaction() as owned_conn:
            result = owned_conn.execute(query, params)
            return int(result.rowcount or 0)

    def reconcile_active_task_summary_projection(
        self,
        *,
        limit: int = 1000,
        apply: bool = False,
    ) -> dict:
        """Inspect or repair bounded active projection drift."""

        normalized_limit = min(1000, max(1, int(limit)))

        def _run(conn) -> dict:
            apply_active_projection_reconciliation_budget(conn)
            rows = load_active_projection_drift_rows(
                conn,
                limit=normalized_limit,
            )
            selected = rows[:normalized_limit]
            existing_ids = [
                str(row["task_id"])
                for row in selected
                if bool(row.get("task_exists"))
            ]
            orphan_ids = [
                str(row["task_id"])
                for row in selected
                if not bool(row.get("task_exists"))
            ]
            upserted = 0
            deleted_orphans = 0
            if apply:
                for task_id in existing_ids:
                    if self.upsert_task_summary_from_task_id(task_id, conn=conn):
                        upserted += 1
                deleted_orphans = delete_orphan_task_projections(conn, orphan_ids)
                post_rows = load_active_projection_drift_rows(
                    conn,
                    limit=normalized_limit,
                )
            else:
                post_rows = rows
            return {
                "mode": "apply" if apply else "dry_run",
                "limit": normalized_limit,
                "examined": len(selected),
                "existing_task_drift": len(existing_ids),
                "orphan_projection_drift": len(orphan_ids),
                "truncated": len(rows) > normalized_limit,
                "upserted": upserted,
                "deleted_orphans": deleted_orphans,
                "post_check_drift": len(post_rows[:normalized_limit]),
                "post_check_truncated": len(post_rows) > normalized_limit,
            }

        context = self.transaction() if apply else self.get_connection()
        with context as conn:
            return _run(conn)
