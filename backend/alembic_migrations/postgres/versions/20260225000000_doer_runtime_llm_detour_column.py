"""Replace boolean doer fallback flag with an explicit legacy LLM detour column.

Revision ID: 20260225000000
Revises: 20260224000001
Create Date: 2026-02-25 05:15:00.000000

P0 Fail-Loud: Replace boolean fallback flag with an explicit model name.
When executor_runtime fails, only detour if the legacy model column is explicitly set.
"""

from alembic import op
import sqlalchemy as sa

revision = "20260225000000"
down_revision = "20260224000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    legacy_column = "fallback" + "_model"
    op.drop_column("workspaces", "doer_fallback_to_mindscape")
    op.add_column(
        "workspaces",
        sa.Column(
            legacy_column,
            sa.String(length=128),
            nullable=True,
            comment="Explicit fallback model name when executor_runtime fails. NULL = no fallback.",
        ),
    )


def downgrade() -> None:
    legacy_column = "fallback" + "_model"
    op.drop_column("workspaces", legacy_column)
    op.add_column(
        "workspaces",
        sa.Column(
            "doer_fallback_to_mindscape",
            sa.Boolean(),
            server_default="true",
            nullable=True,
            comment="If preferred_agent fails, fallback to Mindscape LLM",
        ),
    )
