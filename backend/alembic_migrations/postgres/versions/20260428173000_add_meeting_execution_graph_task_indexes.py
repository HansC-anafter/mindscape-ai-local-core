"""Add task lookup indexes for meeting execution graph

Revision ID: 20260428173000
Revises: 20260427090000
Create Date: 2026-04-28 17:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260428173000"
down_revision = "20260427090000"
branch_labels = None
depends_on = None


INDEXES = [
    (
        "idx_tasks_ws_meeting_session_created_at",
        "ON tasks (workspace_id, meeting_session_id, created_at)",
    ),
    (
        "idx_tasks_ws_execctx_meeting_session_created_at",
        "ON tasks (workspace_id, ((execution_context->>'meeting_session_id')), created_at)",
    ),
    (
        "idx_tasks_ws_execctx_thread_created_at",
        "ON tasks (workspace_id, ((execution_context->>'thread_id')), created_at)",
    ),
    (
        "idx_tasks_ws_params_meeting_session_created_at",
        "ON tasks (workspace_id, ((params->>'meeting_session_id')), created_at)",
    ),
    (
        "idx_tasks_ws_params_thread_created_at",
        "ON tasks (workspace_id, ((params->>'thread_id')), created_at)",
    ),
]


def upgrade():
    conn = op.get_bind()
    for index_name, index_body in INDEXES:
        conn.execute(sa.text(f"CREATE INDEX IF NOT EXISTS {index_name} {index_body}"))


def downgrade():
    conn = op.get_bind()
    for index_name, _ in reversed(INDEXES):
        conn.execute(sa.text(f"DROP INDEX IF EXISTS {index_name}"))
