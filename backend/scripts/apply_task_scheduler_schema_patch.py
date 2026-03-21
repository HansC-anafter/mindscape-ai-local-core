"""Apply the task scheduler schema patch directly to a live Postgres DB.

This is a targeted recovery/deployment helper for environments where the
Alembic history chain is not stamped but the schema already exists.
"""

from __future__ import annotations

import os

from sqlalchemy import create_engine, text


STATEMENTS = [
    "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS next_eligible_at TIMESTAMPTZ",
    "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS blocked_reason TEXT",
    "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS blocked_payload JSON",
    "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS queue_shard TEXT",
    "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS concurrency_key TEXT",
    "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS frontier_state TEXT",
    "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS frontier_enqueued_at TIMESTAMPTZ",
    """
    UPDATE tasks
    SET next_eligible_at = COALESCE(
            CASE
                WHEN execution_context IS NOT NULL
                 AND COALESCE(execution_context->>'resume_after', '') ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T'
                    THEN CAST(execution_context->>'resume_after' AS timestamptz)
                ELSE NULL
            END,
            created_at,
            NOW()
        ),
        blocked_reason = CASE
            WHEN execution_context IS NOT NULL AND execution_context->>'runner_skip_reason' IS NOT NULL
                THEN execution_context->>'runner_skip_reason'
            WHEN execution_context IS NOT NULL AND execution_context->'dependency_hold' IS NOT NULL
                THEN 'dependency_hold'
            ELSE blocked_reason
        END,
        blocked_payload = CASE
            WHEN execution_context IS NOT NULL AND execution_context->'dependency_hold' IS NOT NULL
                THEN json_build_object('dependency_hold', execution_context->'dependency_hold')
            ELSE blocked_payload
        END,
        queue_shard = CASE
            WHEN pack_id = 'ig_analyze_pinned_reference' THEN 'ig_analysis'
            WHEN pack_id IN ('ig_batch_pin_references', 'ig_analyze_following') THEN 'ig_browser'
            ELSE COALESCE(queue_shard, 'default')
        END,
        frontier_state = CASE
            WHEN status = 'running' THEN 'running'
            WHEN status <> 'pending' THEN 'done'
            WHEN task_type NOT IN ('playbook_execution', 'tool_execution') THEN 'cold'
            WHEN execution_context IS NOT NULL AND (
                 execution_context->>'runner_skip_reason' IS NOT NULL
                 OR execution_context->'dependency_hold' IS NOT NULL
            ) THEN 'cold'
            WHEN execution_context IS NOT NULL
                 AND COALESCE(execution_context->>'resume_after', '') ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T'
                 AND CAST(execution_context->>'resume_after' AS timestamptz) > NOW() THEN 'cold'
            ELSE 'ready'
        END
    """,
    "UPDATE tasks SET queue_shard = 'default' WHERE queue_shard IS NULL",
    "UPDATE tasks SET frontier_state = 'cold' WHERE frontier_state IS NULL",
    "UPDATE tasks SET next_eligible_at = COALESCE(next_eligible_at, created_at, NOW()) WHERE next_eligible_at IS NULL",
    "UPDATE tasks SET frontier_enqueued_at = CASE WHEN frontier_state = 'ready' THEN COALESCE(frontier_enqueued_at, created_at) ELSE NULL END",
    "CREATE INDEX IF NOT EXISTS idx_tasks_frontier_cold ON tasks (queue_shard, next_eligible_at, created_at, id) WHERE status = 'pending' AND frontier_state = 'cold'",
    "CREATE INDEX IF NOT EXISTS idx_tasks_frontier_ready ON tasks (queue_shard, frontier_enqueued_at, created_at, id) WHERE status = 'pending' AND frontier_state = 'ready'",
    "CREATE INDEX IF NOT EXISTS idx_tasks_pending_concurrency_key ON tasks (concurrency_key, created_at, id) WHERE status = 'pending' AND concurrency_key IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS idx_tasks_pending_queue_position ON tasks (queue_shard, next_eligible_at, created_at, id) WHERE status = 'pending' AND task_type IN ('playbook_execution', 'tool_execution')",
]


def main() -> None:
    db_url = os.environ.get("DATABASE_URL_CORE") or os.environ.get("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL_CORE or DATABASE_URL is required")

    engine = create_engine(db_url)
    with engine.begin() as conn:
        for stmt in STATEMENTS:
            conn.execute(text(stmt))

    print("TASK_SCHEDULER_SCHEMA_PATCH_OK")


if __name__ == "__main__":
    main()
