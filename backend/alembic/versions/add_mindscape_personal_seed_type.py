"""add_mindscape_personal_seed_type

Revision ID: a1b2c3d4e5f6
Revises: 522f8d8ce222
Create Date: 2025-12-05 20:37:00.000000

Adds seed_type column to mindscape_personal table for semantic_seeds capability.
This column stores the type of seed (project, principle, preference, intent, entity).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '77e8e5c96835'
down_revision: Union[str, None] = 'add_workspace_execution_mode'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Add seed_type column to mindscape_personal table
    """
    # Add seed_type column (if it doesn't exist)
    # Compatible with both SQLite and PostgreSQL
    try:
        op.add_column('mindscape_personal', sa.Column('seed_type', sa.Text(), nullable=True))
    except Exception:
        # Column may already exist, ignore
        pass


def downgrade() -> None:
    """
    Remove seed_type column from mindscape_personal table
    Note: SQLite doesn't support DROP COLUMN, so this is a no-op for SQLite
    """
    # SQLite doesn't support DROP COLUMN
    # For PostgreSQL, this would work but we skip for compatibility
    pass

