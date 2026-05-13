"""Add artifact playbook/type lookup index.

Revision ID: 20260513010000
Revises: 20260512103000
Create Date: 2026-05-13 01:00:00.000000
"""

from alembic import op


revision = "20260513010000"
down_revision = "20260512103000"
branch_labels = None
depends_on = None


def upgrade():
    with op.get_context().autocommit_block():
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_artifacts_workspace_playbook_type_updated
            ON artifacts (workspace_id, playbook_code, artifact_type, updated_at DESC, id DESC)
            """
        )


def downgrade():
    with op.get_context().autocommit_block():
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS idx_artifacts_workspace_playbook_type_updated"
        )
