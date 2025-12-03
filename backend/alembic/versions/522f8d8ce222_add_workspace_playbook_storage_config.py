"""add_workspace_playbook_storage_config

Revision ID: 522f8d8ce222
Revises: 001_initial
Create Date: 2025-12-03 19:57:53.024321

Adds playbook_storage_config column to workspaces table
for playbook-specific storage configuration management.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '522f8d8ce222'
down_revision: Union[str, None] = '001_initial'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Add playbook_storage_config column to workspaces table
    """
    # Add playbook_storage_config column (if it doesn't exist)
    try:
        op.add_column('workspaces', sa.Column('playbook_storage_config', sa.Text(), nullable=True))
    except Exception:
        # Column may already exist, ignore
        pass


def downgrade() -> None:
    """
    Remove playbook_storage_config column
    Note: SQLite doesn't support DROP COLUMN, so this is a no-op
    """
    # SQLite doesn't support DROP COLUMN
    # To properly remove columns, would need to recreate the table
    pass

