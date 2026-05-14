"""Task control-plane projection builder."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text

from app.services.stores.postgres_base import PostgresStoreBase


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TaskProjectionBuilder(PostgresStoreBase):
    """Build compact read models from task control fields and events."""

    def upsert_task_summary_from_task_id(
        self,
        task_id: str,
        *,
        conn=None,
    ) -> bool:
        params = {"task_id": task_id, "updated_at": _utc_now()}
        query = text(
            """
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
                created_at,
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
                tasks.created_at,
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
                created_at = EXCLUDED.created_at,
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
                created_at,
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
                tasks.created_at,
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
                created_at = EXCLUDED.created_at,
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
