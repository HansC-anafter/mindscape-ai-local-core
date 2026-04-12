"""Add grid_posts_json and vision_analysis_json to ig_accounts_flat

Revision ID: 20260311000000
Revises: 20260216000000
Create Date: 2026-03-11 22:45:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "20260311000000"
down_revision = "20260216000000"
branch_labels = None
depends_on = None


def _column_exists(conn, column_name: str) -> bool:
    result = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name='ig_accounts_flat' AND column_name=:col"
        ),
        {"col": column_name},
    ).fetchone()
    return result is not None


def upgrade():
    conn = op.get_bind()

    if not _column_exists(conn, "grid_posts_json"):
        op.add_column(
            "ig_accounts_flat",
            sa.Column("grid_posts_json", sa.Text(), nullable=True),
        )

    if not _column_exists(conn, "vision_analysis_json"):
        op.add_column(
            "ig_accounts_flat",
            sa.Column("vision_analysis_json", sa.Text(), nullable=True),
        )


def downgrade():
    op.drop_column("ig_accounts_flat", "vision_analysis_json")
    op.drop_column("ig_accounts_flat", "grid_posts_json")
