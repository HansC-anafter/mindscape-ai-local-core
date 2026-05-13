"""Enable PostgreSQL observability and reclaim extensions.

Revision ID: 20260513203000
Revises: 20260513183000
Create Date: 2026-05-13 20:30:00.000000
"""

from alembic import op


revision = "20260513203000"
down_revision = "20260513183000"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_stat_statements")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_repack")


def downgrade():
    pass
