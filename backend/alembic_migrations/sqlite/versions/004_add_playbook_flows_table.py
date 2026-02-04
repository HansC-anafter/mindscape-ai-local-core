"""add_playbook_flows_table

Revision ID: 004_add_playbook_flows
Revises: 003_add_artifact_registry
Create Date: 2025-12-07

Adds playbook_flows table for defining flow orchestration structures.
Flows define sequences of playbook executions with dependencies.

See: docs/core-architecture/implementation-roadmap-detailed.md
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '004_add_playbook_flows'
down_revision: Union[str, None] = '003_add_artifact_registry'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Create playbook_flows table

    Playbook Flows table structure:
    - id: Unique flow identifier
    - name: Flow display name
    - description: Flow description (optional)
    - flow_definition: JSON definition containing nodes and edges
    - created_at, updated_at: Timestamps
    """
    op.create_table(
        'playbook_flows',
        sa.Column('id', sa.String(255), primary_key=True),
        sa.Column('name', sa.String(500), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('flow_definition', sa.Text, nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('updated_at', sa.DateTime, nullable=False)
    )

    # Create indexes
    op.create_index('idx_playbook_flows_name', 'playbook_flows', ['name'])
    op.create_index('idx_playbook_flows_created_at', 'playbook_flows', ['created_at'])


def downgrade() -> None:
    """
    Drop playbook_flows table
    """
    op.drop_index('idx_playbook_flows_created_at', table_name='playbook_flows')
    op.drop_index('idx_playbook_flows_name', table_name='playbook_flows')
    op.drop_table('playbook_flows')

