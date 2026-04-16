"""
Migration: create scene_generation_jobs table for performance_direction.

Revision ID: 20260330000002
Revises: 20260330000001
Create Date: 2026-03-30
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260330000002"
down_revision = "20260330000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    status_enum = sa.Enum(
        "queued",
        "uploading",
        "submitted",
        "polling",
        "completed",
        "failed",
        "cancelled",
        name="scene_generation_job_status",
    )
    status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "scene_generation_jobs",
        sa.Column("job_id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("provider_code", sa.String(length=64), nullable=True),
        sa.Column("generation_mode", sa.String(length=32), nullable=False),
        sa.Column("status", status_enum, nullable=False, server_default="queued"),
        sa.Column("scene_scope", sa.String(length=64), nullable=True),
        sa.Column("variant_id", sa.String(length=64), nullable=True),
        sa.Column("capture_bundle_id", sa.String(length=64), nullable=True),
        sa.Column("workspace_artifact_id", sa.String(length=64), nullable=True),
        sa.Column("provider_operation_id", sa.String(length=128), nullable=True),
        sa.Column("result_artifact_id", sa.String(length=64), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("input_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("temp_asset_refs", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["direction_sessions.session_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("job_id"),
    )
    op.create_index(
        "ix_scene_generation_jobs_session_status",
        "scene_generation_jobs",
        ["session_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_scene_generation_jobs_provider_operation",
        "scene_generation_jobs",
        ["provider_code", "provider_operation_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_scene_generation_jobs_provider_operation",
        table_name="scene_generation_jobs",
    )
    op.drop_index(
        "ix_scene_generation_jobs_session_status",
        table_name="scene_generation_jobs",
    )
    op.drop_table("scene_generation_jobs")
    sa.Enum(name="scene_generation_job_status").drop(
        op.get_bind(),
        checkfirst=True,
    )
