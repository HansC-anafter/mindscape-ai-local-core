"""Enforce one running task per concurrency key.

Revision ID: 20260511050000
Revises: 20260511030000
Create Date: 2026-05-11 05:00:00.000000
"""

from alembic import op
from sqlalchemy import text


revision = "20260511050000"
down_revision = "20260511030000"
branch_labels = None
depends_on = None


def _assert_no_running_concurrency_duplicates():
    bind = op.get_bind()
    rows = bind.execute(
        text(
            """
            SELECT concurrency_key, count(*) AS task_count
            FROM tasks
            WHERE status = 'running'
              AND concurrency_key IS NOT NULL
              AND concurrency_key <> ''
            GROUP BY concurrency_key
            HAVING count(*) > 1
            ORDER BY task_count DESC, concurrency_key
            LIMIT 5
            """
        )
    ).fetchall()
    if rows:
        details = ", ".join(
            f"{row.concurrency_key}={row.task_count}" for row in rows
        )
        raise RuntimeError(
            "Cannot create running concurrency key unique index while duplicate "
            f"running tasks exist: {details}"
        )


def upgrade():
    _assert_no_running_concurrency_duplicates()
    with op.get_context().autocommit_block():
        op.execute(
            """
            CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS idx_tasks_running_concurrency_key_unique
            ON tasks (concurrency_key)
            WHERE status = 'running'
              AND concurrency_key IS NOT NULL
              AND concurrency_key <> ''
            """
        )


def downgrade():
    with op.get_context().autocommit_block():
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS idx_tasks_running_concurrency_key_unique"
        )
