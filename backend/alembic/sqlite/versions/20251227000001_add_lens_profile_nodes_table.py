"""add_lens_profile_nodes_table

Revision ID: 20251227000001
Revises: 20251227000000
Create Date: 2025-12-27

Adds lens_profile_nodes and workspace_lens_overrides tables for Mind-Lens unified implementation.

This migration is part of Phase 0 of the Mind-Lens implementation roadmap.
See: docs-internal/mind-lens/implementation/implementation-roadmap.md
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '20251227000001'
down_revision: Union[str, None] = '20251227000000'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create lens_profile_nodes and workspace_lens_overrides tables"""

    op.create_table(
        'lens_profile_nodes',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column('preset_id', sa.String(36), nullable=False),
        sa.Column('node_id', sa.String(36), nullable=False),
        sa.Column('state', sa.String(20), nullable=False, server_default='keep'),
        sa.Column('updated_at', sa.String(30), nullable=False),
        sa.ForeignKeyConstraint(['preset_id'], ['mind_lens_profiles.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['node_id'], ['graph_nodes.id'], ondelete='CASCADE'),
        sa.CheckConstraint("state IN ('off', 'keep', 'emphasize')", name='ck_lens_profile_nodes_state'),
        sa.UniqueConstraint('preset_id', 'node_id', name='uq_lens_profile_nodes'),
    )

    op.create_index('idx_lens_profile_nodes_preset', 'lens_profile_nodes', ['preset_id'])
    op.create_index('idx_lens_profile_nodes_node', 'lens_profile_nodes', ['node_id'])

    op.create_table(
        'workspace_lens_overrides',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column('workspace_id', sa.String(255), nullable=False),
        sa.Column('node_id', sa.String(36), nullable=False),
        sa.Column('state', sa.String(20), nullable=False),
        sa.Column('updated_at', sa.String(30), nullable=False),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['node_id'], ['graph_nodes.id'], ondelete='CASCADE'),
        sa.CheckConstraint("state IN ('off', 'keep', 'emphasize')", name='ck_workspace_lens_overrides_state'),
        sa.UniqueConstraint('workspace_id', 'node_id', name='uq_workspace_lens_overrides'),
    )

    op.create_index('idx_workspace_overrides_ws', 'workspace_lens_overrides', ['workspace_id'])
    op.create_index('idx_workspace_overrides_node', 'workspace_lens_overrides', ['node_id'])


def downgrade() -> None:
    """Drop lens_profile_nodes and workspace_lens_overrides tables"""
    op.drop_index('idx_workspace_overrides_node', table_name='workspace_lens_overrides')
    op.drop_index('idx_workspace_overrides_ws', table_name='workspace_lens_overrides')
    op.drop_table('workspace_lens_overrides')
    op.drop_index('idx_lens_profile_nodes_node', table_name='lens_profile_nodes')
    op.drop_index('idx_lens_profile_nodes_preset', table_name='lens_profile_nodes')
    op.drop_table('lens_profile_nodes')

