"""Add compile_jobs table.

Wave 0: handoff compile job persistence.

Revision ID: 20260328183000
Revises: 20260328003000
Create Date: 2026-03-28T18:30:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260328183000"
down_revision = "20260328003000"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if not inspector.has_table("compile_jobs"):
        op.create_table(
            "compile_jobs",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("workspace_id", sa.String(), nullable=False),
            sa.Column("project_id", sa.String(), nullable=True),
            sa.Column("thread_id", sa.String(), nullable=True),
            sa.Column("profile_id", sa.String(), nullable=True),
            sa.Column("session_id", sa.String(), nullable=True),
            sa.Column("handoff_id", sa.String(), nullable=True),
            sa.Column("source_device_id", sa.String(), nullable=True),
            sa.Column("status", sa.String(32), nullable=False, server_default="accepted"),
            sa.Column(
                "result",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column(
                "metadata",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index(
            "ix_compile_jobs_ws_created",
            "compile_jobs",
            ["workspace_id", "created_at"],
        )
        op.create_index(
            "ix_compile_jobs_session",
            "compile_jobs",
            ["session_id"],
        )
        op.create_index(
            "ix_compile_jobs_status_updated",
            "compile_jobs",
            ["status", "updated_at"],
        )


def downgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if inspector.has_table("compile_jobs"):
        op.drop_index("ix_compile_jobs_status_updated", table_name="compile_jobs", if_exists=True)
        op.drop_index("ix_compile_jobs_session", table_name="compile_jobs", if_exists=True)
        op.drop_index("ix_compile_jobs_ws_created", table_name="compile_jobs", if_exists=True)
        op.drop_table("compile_jobs")
