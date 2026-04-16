"""
Migration: add retry scheduling fields to scene_generation_jobs.

Revision ID: 20260330000003
Revises: 20260330000002
Create Date: 2026-03-30
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260330000003"
down_revision = "20260330000002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "scene_generation_jobs",
        sa.Column("last_attempted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "scene_generation_jobs",
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_scene_generation_jobs_last_attempted_at",
        "scene_generation_jobs",
        ["last_attempted_at"],
        unique=False,
    )
    op.create_index(
        "ix_scene_generation_jobs_next_attempt_at",
        "scene_generation_jobs",
        ["next_attempt_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_scene_generation_jobs_next_attempt_at",
        table_name="scene_generation_jobs",
    )
    op.drop_index(
        "ix_scene_generation_jobs_last_attempted_at",
        table_name="scene_generation_jobs",
    )
    op.drop_column("scene_generation_jobs", "next_attempt_at")
    op.drop_column("scene_generation_jobs", "last_attempted_at")
