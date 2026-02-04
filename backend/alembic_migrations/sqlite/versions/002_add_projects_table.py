"""add_projects_table

Revision ID: 002_add_projects
Revises: add_workspace_execution_mode
Create Date: 2025-12-07

Adds projects table for Project + Flow architecture.
Projects are workspace-based containers for concrete deliverables.

See: docs/core-architecture/implementation-roadmap-detailed.md
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '002_add_projects'
down_revision: Union[str, None] = 'add_workspace_execution_mode'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Create projects table

    Projects table structure:
    - id: Unique project identifier
    - type: Project type (web_page, book, course, campaign, etc.)
    - title: Project title
    - home_workspace_id: Foreign key to workspaces.id
    - flow_id: Playbook flow ID for execution orchestration
    - state: Project state (open, closed, archived)
    - initiator_user_id: User who initiated this project
    - human_owner_user_id: Human PM user ID (optional)
    - ai_pm_id: AI team PM ID (optional)
    - created_at, updated_at: Timestamps
    - metadata: JSON metadata
    """
    op.create_table(
        'projects',
        sa.Column('id', sa.String(255), primary_key=True),
        sa.Column('type', sa.String(100), nullable=False),
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('home_workspace_id', sa.String(255), nullable=False),
        sa.Column('flow_id', sa.String(255), nullable=False),
        sa.Column('state', sa.String(50), nullable=False, server_default='open'),
        sa.Column('initiator_user_id', sa.String(255), nullable=False),
        sa.Column('human_owner_user_id', sa.String(255), nullable=True),
        sa.Column('ai_pm_id', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('updated_at', sa.DateTime, nullable=False),
        sa.Column('metadata', sa.Text, nullable=True),
        sa.ForeignKeyConstraint(['home_workspace_id'], ['workspaces.id'], name='fk_projects_workspace')
    )

    # Create indexes
    op.create_index('idx_projects_workspace', 'projects', ['home_workspace_id'])
    op.create_index('idx_projects_state', 'projects', ['state'])
    op.create_index('idx_projects_created_at', 'projects', ['created_at'])


def downgrade() -> None:
    """
    Drop projects table

    Note: SQLite doesn't support DROP COLUMN, but we can drop the entire table.
    """
    op.drop_index('idx_projects_created_at', table_name='projects')
    op.drop_index('idx_projects_state', table_name='projects')
    op.drop_index('idx_projects_workspace', table_name='projects')
    op.drop_table('projects')

