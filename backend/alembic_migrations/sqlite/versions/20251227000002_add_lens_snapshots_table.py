"""add_lens_snapshots_table

Revision ID: 20251227000002
Revises: 20251227000001
Create Date: 2025-12-27

Adds lens_snapshots and lens_receipts tables for Mind-Lens observability.

This migration is part of Phase 2 of the Mind-Lens implementation roadmap.
See: docs-internal/mind-lens/implementation/implementation-roadmap.md
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '20251227000002'
down_revision: Union[str, None] = '20251227000001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create lens_snapshots and lens_receipts tables"""

    op.create_table(
        'lens_snapshots',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column('effective_lens_hash', sa.String(16), nullable=False),
        sa.Column('profile_id', sa.String(255), nullable=False),
        sa.Column('workspace_id', sa.String(255), nullable=True),
        sa.Column('session_id', sa.String(255), nullable=True),
        sa.Column('nodes_json', sa.Text(), nullable=False),
        sa.Column('created_at', sa.String(30), nullable=False),
        sa.UniqueConstraint('effective_lens_hash', name='uq_lens_snapshots_hash'),
    )

    op.create_index('idx_lens_snapshots_hash', 'lens_snapshots', ['effective_lens_hash'])
    op.create_index('idx_lens_snapshots_profile', 'lens_snapshots', ['profile_id'])
    op.create_index('idx_lens_snapshots_workspace', 'lens_snapshots', ['workspace_id'])

    op.create_table(
        'lens_receipts',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column('execution_id', sa.String(255), nullable=False),
        sa.Column('workspace_id', sa.String(255), nullable=False),
        sa.Column('effective_lens_hash', sa.String(16), nullable=False),
        sa.Column('triggered_nodes_json', sa.Text(), nullable=True),
        sa.Column('base_output', sa.Text(), nullable=True),
        sa.Column('lens_output', sa.Text(), nullable=True),
        sa.Column('diff_summary', sa.Text(), nullable=True),
        sa.Column('created_at', sa.String(30), nullable=False),
    )

    op.create_index('idx_lens_receipts_execution', 'lens_receipts', ['execution_id'])
    op.create_index('idx_lens_receipts_workspace', 'lens_receipts', ['workspace_id'])
    op.create_index('idx_lens_receipts_hash', 'lens_receipts', ['effective_lens_hash'])


def downgrade() -> None:
    """Drop lens_snapshots and lens_receipts tables"""
    op.drop_index('idx_lens_receipts_hash', table_name='lens_receipts')
    op.drop_index('idx_lens_receipts_workspace', table_name='lens_receipts')
    op.drop_index('idx_lens_receipts_execution', table_name='lens_receipts')
    op.drop_table('lens_receipts')
    op.drop_index('idx_lens_snapshots_workspace', table_name='lens_snapshots')
    op.drop_index('idx_lens_snapshots_profile', table_name='lens_snapshots')
    op.drop_index('idx_lens_snapshots_hash', table_name='lens_snapshots')
    op.drop_table('lens_snapshots')

