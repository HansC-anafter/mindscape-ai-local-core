"""Bounded active task projection drift queries and mutation helpers."""

from __future__ import annotations

from sqlalchemy import bindparam, text


_TASK_PROJECTION_CONTROL_DRIFT_PREDICATE = """
ROW(
    tasks.workspace_id::text, tasks.execution_id::text,
    tasks.parent_execution_id::text, tasks.project_id::text,
    tasks.pack_id::text, tasks.task_type::text, tasks.status::text,
    tasks.queue_shard::text, tasks.concurrency_key::text, tasks.error,
    tasks.created_at, tasks.next_eligible_at, tasks.blocked_reason,
    tasks.frontier_state, tasks.frontier_enqueued_at, tasks.started_at,
    tasks.completed_at
) IS DISTINCT FROM ROW(
    projection.workspace_id::text, projection.execution_id::text,
    projection.parent_execution_id::text, projection.project_id::text,
    projection.pack_id::text, projection.task_type, projection.status,
    projection.queue_shard, projection.dedupe_key,
    projection.error_summary, projection.created_at,
    projection.next_eligible_at, projection.blocked_reason,
    projection.frontier_state, projection.frontier_enqueued_at,
    projection.started_at, projection.completed_at
)
"""

_ACTIVE_TASK_TRUTH_DRIFT_SQL = text(
    f"""
    SELECT /* active_task_truth_drift */
        tasks.id::text AS task_id,
        TRUE AS task_exists
    FROM tasks
    LEFT JOIN task_summary_projection AS projection
      ON projection.task_id = tasks.id::text
    WHERE tasks.task_type IN ('playbook_execution', 'tool_execution')
      AND (
          tasks.status = 'running'
          OR (
              tasks.status = 'pending'
              AND tasks.frontier_state = 'ready'
              AND (tasks.blocked_reason IS NULL OR tasks.blocked_reason = '')
          )
      )
      AND (
          projection.task_id IS NULL
          OR {_TASK_PROJECTION_CONTROL_DRIFT_PREDICATE}
      )
    LIMIT :candidate_limit
    """
)

_ACTIVE_PROJECTION_QUEUE_DRIFT_SQL = text(
    f"""
    SELECT /* active_projection_queue_drift */
        projection.task_id,
        tasks.id IS NOT NULL AS task_exists
    FROM task_summary_projection AS projection
    LEFT JOIN tasks ON tasks.id::text = projection.task_id
    WHERE projection.status = 'pending'
      AND projection.task_type IN ('playbook_execution', 'tool_execution')
      AND projection.frontier_state = 'ready'
      AND projection.next_eligible_at IS NOT NULL
      AND (projection.blocked_reason IS NULL OR projection.blocked_reason = '')
      AND (
          tasks.id IS NULL
          OR {_TASK_PROJECTION_CONTROL_DRIFT_PREDICATE}
      )
    LIMIT :candidate_limit
    """
)

_DELETE_ORPHAN_TASK_PROJECTIONS_SQL = text(
    """
    DELETE FROM task_summary_projection AS projection
    WHERE projection.task_id IN :task_ids
      AND NOT EXISTS (
          SELECT 1
          FROM tasks
          WHERE tasks.id::text = projection.task_id
      )
    """
).bindparams(bindparam("task_ids", expanding=True))


def apply_active_projection_reconciliation_budget(conn) -> None:
    if str(getattr(getattr(conn, "dialect", None), "name", "")) != "postgresql":
        return
    conn.execute(text("SELECT set_config('statement_timeout', '2000ms', true)"))
    conn.execute(text("SELECT set_config('lock_timeout', '1000ms', true)"))


def load_active_projection_drift_rows(conn, *, limit: int) -> list[dict]:
    rows_by_id: dict[str, dict] = {}
    for query in (_ACTIVE_TASK_TRUTH_DRIFT_SQL, _ACTIVE_PROJECTION_QUEUE_DRIFT_SQL):
        rows = conn.execute(query, {"candidate_limit": limit + 1}).mappings()
        for row in rows.all():
            item = dict(row)
            rows_by_id[str(item["task_id"])] = item
    return [rows_by_id[key] for key in sorted(rows_by_id)][: limit + 1]


def delete_orphan_task_projections(conn, task_ids: list[str]) -> int:
    if not task_ids:
        return 0
    result = conn.execute(
        _DELETE_ORPHAN_TASK_PROJECTIONS_SQL,
        {"task_ids": task_ids},
    )
    return int(result.rowcount or 0)
