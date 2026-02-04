"""add_web_generation_baselines_tables

Revision ID: 005_add_web_generation_baselines
Revises: 004_add_playbook_flows
Create Date: 2025-12-12

Adds web_generation_baselines and baseline_events tables for Design Snapshot governance.

Tables:
- web_generation_baselines: Baseline configuration (single source of truth)
- baseline_events: Baseline change history for audit trail

See: capabilities/web_generation/docs/ui-engineering-decisions.md
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '005_add_web_generation_baselines'
down_revision: Union[str, None] = '004_add_playbook_flows'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Create web_generation_baselines and baseline_events tables

    web_generation_baselines:
    - Single source of truth for baseline configuration
    - Links workspace/project to design_snapshot artifact
    - Stores lock_mode and bound versions for stale detection

    baseline_events:
    - Audit trail for all baseline changes
    - Records previous/new state, triggered_by, timestamp
    """

    # Create web_generation_baselines table
    op.create_table(
        'web_generation_baselines',
        sa.Column('id', sa.String(255), primary_key=True),
        sa.Column('workspace_id', sa.String(255), nullable=False),
        sa.Column('project_id', sa.String(255), nullable=True),  # NULL = workspace-level default
        sa.Column('snapshot_id', sa.String(255), nullable=False),  # Reference to artifacts.id
        sa.Column('variant_id', sa.String(255), nullable=True),  # UI variant identifier
        sa.Column('lock_mode', sa.String(20), nullable=False, server_default='advisory'),  # 'locked' | 'advisory'
        sa.Column('bound_spec_version', sa.String(100), nullable=True),  # For stale detection
        sa.Column('bound_outline_version', sa.String(100), nullable=True),  # For stale detection
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column('created_by', sa.String(255), nullable=True),  # user_id
        sa.Column('updated_by', sa.String(255), nullable=True),  # user_id
        sa.Column('notes', sa.Text, nullable=True),  # User notes
        sa.CheckConstraint("lock_mode IN ('locked', 'advisory')", name='ck_baseline_lock_mode'),
        sa.UniqueConstraint('workspace_id', 'project_id', name='uq_baseline_workspace_project')
    )

    # Create indexes for web_generation_baselines
    op.create_index('idx_baseline_workspace', 'web_generation_baselines', ['workspace_id'])
    op.create_index('idx_baseline_project', 'web_generation_baselines', ['project_id'])
    op.create_index('idx_baseline_snapshot', 'web_generation_baselines', ['snapshot_id'])

    # Create baseline_events table
    op.create_table(
        'baseline_events',
        sa.Column('id', sa.String(255), primary_key=True),
        sa.Column('event_type', sa.String(50), nullable=False),  # 'set', 'unset', 'lock', 'unlock', 'sync', 'variant_change'
        sa.Column('workspace_id', sa.String(255), nullable=False),
        sa.Column('project_id', sa.String(255), nullable=True),
        sa.Column('snapshot_id', sa.String(255), nullable=False),  # Reference to artifacts.id
        sa.Column('variant_id', sa.String(255), nullable=True),
        sa.Column('previous_state', sa.JSON, nullable=True),  # {snapshot_id, variant_id, lock_mode}
        sa.Column('new_state', sa.JSON, nullable=False),  # {snapshot_id, variant_id, lock_mode}
        sa.Column('reason', sa.Text, nullable=True),  # User notes or system reason
        sa.Column('triggered_by', sa.String(255), nullable=False),  # user_id or 'system'
        sa.Column('triggered_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column('execution_id', sa.String(255), nullable=True)  # If triggered by execution
    )

    # Create indexes for baseline_events
    op.create_index('idx_baseline_events_lookup', 'baseline_events', ['workspace_id', 'project_id', 'triggered_at'])
    op.create_index('idx_baseline_events_snapshot', 'baseline_events', ['snapshot_id', 'triggered_at'])
    op.create_index('idx_baseline_events_type', 'baseline_events', ['event_type', 'triggered_at'])


def downgrade() -> None:
    """
    Drop web_generation_baselines and baseline_events tables
    """
    # Drop indexes first
    op.drop_index('idx_baseline_events_type', table_name='baseline_events')
    op.drop_index('idx_baseline_events_snapshot', table_name='baseline_events')
    op.drop_index('idx_baseline_events_lookup', table_name='baseline_events')
    op.drop_index('idx_baseline_snapshot', table_name='web_generation_baselines')
    op.drop_index('idx_baseline_project', table_name='web_generation_baselines')
    op.drop_index('idx_baseline_workspace', table_name='web_generation_baselines')

    # Drop tables
    op.drop_table('baseline_events')
    op.drop_table('web_generation_baselines')
