"""Add background_routines table

Revision ID: 20260127000002
Revises: 20260127000001
Create Date: 2026-01-27

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260127000002"
down_revision: Union[str, None] = "20260127000001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create background_routines table."""
    op.create_table(
        "background_routines",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.String(64),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("playbook_code", sa.String(128), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("config", sa.Text(), nullable=True),
        sa.Column("last_run_at", sa.DateTime(), nullable=True),
        sa.Column("next_run_at", sa.DateTime(), nullable=True),
        sa.Column("last_status", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("readiness_status", sa.String(64), nullable=True),
        sa.Column("tool_statuses", sa.Text(), nullable=True),
        sa.Column("error_count", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("auto_paused", sa.Boolean(), nullable=True, server_default="false"),
    )

    # Create indexes
    op.create_index(
        "ix_background_routines_workspace_id", "background_routines", ["workspace_id"]
    )
    op.create_index(
        "ix_background_routines_playbook_code", "background_routines", ["playbook_code"]
    )
    op.create_index(
        "ix_background_routines_enabled", "background_routines", ["enabled"]
    )


def downgrade() -> None:
    """Drop background_routines table."""
    op.drop_index("ix_background_routines_enabled", table_name="background_routines")
    op.drop_index(
        "ix_background_routines_playbook_code", table_name="background_routines"
    )
    op.drop_index(
        "ix_background_routines_workspace_id", table_name="background_routines"
    )
    op.drop_table("background_routines")
