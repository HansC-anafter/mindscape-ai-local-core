"""add_workspace_execution_mode

Revision ID: add_workspace_execution_mode
Revises: 522f8d8ce222
Create Date: 2025-12-03

Adds execution_mode, expected_artifacts, and execution_priority columns
to workspaces table for Workspace Execution Mode feature.

See: docs-internal/architecture/workspace-llm-agent-execution-mode.md
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_workspace_execution_mode'
down_revision: Union[str, None] = '522f8d8ce222'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Add execution mode columns to workspaces table

    - execution_mode: 'qa' | 'execution' | 'hybrid', default 'qa'
    - expected_artifacts: JSON array of artifact types
    - execution_priority: 'low' | 'medium' | 'high', default 'medium'
    """
    try:
        op.add_column('workspaces', sa.Column(
            'execution_mode',
            sa.String(),
            nullable=True,
            server_default='qa'
        ))
    except Exception:
        pass

    try:
        op.add_column('workspaces', sa.Column(
            'expected_artifacts',
            sa.Text(),
            nullable=True
        ))
    except Exception:
        pass

    try:
        op.add_column('workspaces', sa.Column(
            'execution_priority',
            sa.String(),
            nullable=True,
            server_default='medium'
        ))
    except Exception:
        pass


def downgrade() -> None:
    """
    Remove execution mode columns
    Note: SQLite doesn't support DROP COLUMN, so this is a no-op
    """
    pass

