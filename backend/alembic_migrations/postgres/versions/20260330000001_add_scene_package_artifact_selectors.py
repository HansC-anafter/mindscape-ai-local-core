"""
Migration: add scene_package artifact selectors to direction_artifacts.

Revision ID: 20260330000001
Revises: 20260322000001
Create Date: 2026-03-30
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260330000001"
down_revision = "20260322000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE direction_artifact_type "
        "ADD VALUE IF NOT EXISTS 'scene_package'"
    )
    op.add_column(
        "direction_artifacts",
        sa.Column("package_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "direction_artifacts",
        sa.Column("scene_scope", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "direction_artifacts",
        sa.Column("variant_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "direction_artifacts",
        sa.Column("provider_code", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "direction_artifacts",
        sa.Column("artifact_state", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "direction_artifacts",
        sa.Column("generation_mode", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "direction_artifacts",
        sa.Column("supersedes_artifact_id", sa.String(length=64), nullable=True),
    )

    op.create_index(
        "ix_direction_artifacts_session_artifact_scope_variant_state",
        "direction_artifacts",
        ["session_id", "artifact_type", "scene_scope", "variant_id", "artifact_state"],
        unique=False,
    )
    op.create_index(
        "ix_direction_artifacts_session_artifact_package",
        "direction_artifacts",
        ["session_id", "artifact_type", "package_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_direction_artifacts_session_artifact_package",
        table_name="direction_artifacts",
    )
    op.drop_index(
        "ix_direction_artifacts_session_artifact_scope_variant_state",
        table_name="direction_artifacts",
    )
    op.drop_column("direction_artifacts", "supersedes_artifact_id")
    op.drop_column("direction_artifacts", "generation_mode")
    op.drop_column("direction_artifacts", "artifact_state")
    op.drop_column("direction_artifacts", "provider_code")
    op.drop_column("direction_artifacts", "variant_id")
    op.drop_column("direction_artifacts", "scene_scope")
    op.drop_column("direction_artifacts", "package_id")
