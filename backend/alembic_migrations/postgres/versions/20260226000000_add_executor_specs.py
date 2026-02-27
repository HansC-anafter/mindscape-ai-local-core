"""add executor_specs column to workspaces

Revision ID: 20260226000000
Revises: 20260225100000
Create Date: 2026-02-26 00:00:00.000000

Adds structured executor bindings while keeping executor_runtime for backward compatibility.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260226000000"
down_revision = "20260225100000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workspaces",
        sa.Column(
            "executor_specs",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
            comment="Structured executor bindings for workspace dispatch chain",
        ),
    )

    # Backfill from legacy executor_runtime to a single primary spec.
    op.execute(
        """
        UPDATE workspaces
        SET executor_specs = jsonb_build_array(
            jsonb_build_object(
                'runtime_id', executor_runtime,
                'display_name', executor_runtime,
                'is_primary', true,
                'config', '{}'::jsonb,
                'priority', 0
            )
        )
        WHERE executor_runtime IS NOT NULL
          AND btrim(executor_runtime) <> ''
          AND (
            executor_specs IS NULL
            OR executor_specs = '[]'::jsonb
          )
        """
    )


def downgrade() -> None:
    op.drop_column("workspaces", "executor_specs")
