"""Replace doer_fallback_to_mindscape with fallback_model

Revision ID: 20260225000000
Revises: 20260224000001
Create Date: 2026-02-25 05:15:00.000000

P0 Fail-Loud: Replace boolean fallback flag with an explicit model name.
When executor_runtime fails, only fall back if fallback_model is explicitly set.
"""

from alembic import op
import sqlalchemy as sa

revision = "20260225000000"
down_revision = "20260224000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("workspaces", "doer_fallback_to_mindscape")
    op.add_column(
        "workspaces",
        sa.Column(
            "fallback_model",
            sa.String(length=128),
            nullable=True,
            comment="Explicit fallback model name when executor_runtime fails. NULL = no fallback.",
        ),
    )


def downgrade() -> None:
    op.drop_column("workspaces", "fallback_model")
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
