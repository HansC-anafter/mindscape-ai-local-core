"""add_lens_metrics_tables

Revision ID: 20251228000001
Revises: 20251227000002
Create Date: 2025-12-28

Adds preview_votes table and extends lens_receipts table for Mind-Lens metrics system.

This migration adds support for:
- Preview vote tracking (user choice: base vs lens)
- Convergence metrics (rerun_count, edit_count, time_to_accept_ms)
- Apply target tracking (session_only, workspace, preset)

See: docs-internal/mind-lens/implementation/implementation-roadmap.md
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '20251228000001'
down_revision: Union[str, None] = '20251227000002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create preview_votes table and extend lens_receipts table"""

    # Create preview_votes table for tracking user choices
    op.create_table(
        'preview_votes',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column('preview_id', sa.String(255), nullable=False),  # Links to preview session/execution
        sa.Column('workspace_id', sa.String(255), nullable=False),
        sa.Column('profile_id', sa.String(255), nullable=False),
        sa.Column('session_id', sa.String(255), nullable=True),
        sa.Column('chosen_variant', sa.String(10), nullable=False),  # 'base' or 'lens'
        sa.Column('preview_type', sa.String(50), nullable=True),  # 'rewrite', 'section_pack', etc.
        sa.Column('input_text_hash', sa.String(64), nullable=True),  # Hash of input for deduplication
        sa.Column('created_at', sa.String(30), nullable=False),
    )

    op.create_index('idx_preview_votes_workspace', 'preview_votes', ['workspace_id'])
    op.create_index('idx_preview_votes_profile', 'preview_votes', ['profile_id'])
    op.create_index('idx_preview_votes_session', 'preview_votes', ['session_id'])
    op.create_index('idx_preview_votes_chosen', 'preview_votes', ['chosen_variant'])

    # Extend lens_receipts table with convergence metrics
    op.add_column('lens_receipts', sa.Column('accepted', sa.Boolean(), nullable=True))
    op.add_column('lens_receipts', sa.Column('rerun_count', sa.Integer(), nullable=True))
    op.add_column('lens_receipts', sa.Column('edit_count', sa.Integer(), nullable=True))
    op.add_column('lens_receipts', sa.Column('time_to_accept_ms', sa.Integer(), nullable=True))
    op.add_column('lens_receipts', sa.Column('apply_target', sa.String(20), nullable=True))  # 'session_only', 'workspace', 'preset'
    op.add_column('lens_receipts', sa.Column('anti_goal_violations', sa.Integer(), nullable=True))
    op.add_column('lens_receipts', sa.Column('coverage_emph_triggered', sa.Float(), nullable=True))  # Ratio of emphasized nodes that were triggered

    op.create_index('idx_lens_receipts_accepted', 'lens_receipts', ['accepted'])
    op.create_index('idx_lens_receipts_apply_target', 'lens_receipts', ['apply_target'])


def downgrade() -> None:
    """Drop preview_votes table and remove extended columns from lens_receipts"""
    op.drop_index('idx_lens_receipts_apply_target', table_name='lens_receipts')
    op.drop_index('idx_lens_receipts_accepted', table_name='lens_receipts')
    op.drop_column('lens_receipts', 'coverage_emph_triggered')
    op.drop_column('lens_receipts', 'anti_goal_violations')
    op.drop_column('lens_receipts', 'apply_target')
    op.drop_column('lens_receipts', 'time_to_accept_ms')
    op.drop_column('lens_receipts', 'edit_count')
    op.drop_column('lens_receipts', 'rerun_count')
    op.drop_column('lens_receipts', 'accepted')

    op.drop_index('idx_preview_votes_chosen', table_name='preview_votes')
    op.drop_index('idx_preview_votes_session', table_name='preview_votes')
    op.drop_index('idx_preview_votes_profile', table_name='preview_votes')
    op.drop_index('idx_preview_votes_workspace', table_name='preview_votes')
    op.drop_table('preview_votes')

