"""Reduce tasks analyze pressure on large payload columns.

Revision ID: 20260511172000
Revises: 20260511163000
Create Date: 2026-05-11 17:20:00.000000
"""

from alembic import op


revision = "20260511172000"
down_revision = "20260511163000"
branch_labels = None
depends_on = None


PAYLOAD_COLUMNS = (
    "params",
    "result",
    "execution_context",
    "storyline_tags",
    "blocked_payload",
)


def upgrade():
    for column in PAYLOAD_COLUMNS:
        op.execute(f"ALTER TABLE tasks ALTER COLUMN {column} SET STATISTICS 0")
    op.execute(
        """
        ALTER TABLE tasks SET (
            autovacuum_vacuum_scale_factor = 0.02,
            autovacuum_vacuum_threshold = 500,
            autovacuum_analyze_scale_factor = 0.10,
            autovacuum_analyze_threshold = 10000
        )
        """
    )


def downgrade():
    for column in PAYLOAD_COLUMNS:
        op.execute(f"ALTER TABLE tasks ALTER COLUMN {column} SET STATISTICS -1")
    op.execute(
        """
        ALTER TABLE tasks SET (
            autovacuum_vacuum_scale_factor = 0.02,
            autovacuum_vacuum_threshold = 500,
            autovacuum_analyze_scale_factor = 0.01,
            autovacuum_analyze_threshold = 500
        )
        """
    )
