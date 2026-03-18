"""Initial Expert Network schema

Revision ID: 20260319000000
Revises:
Create Date: 2026-03-19 00:00:00.000000

Creates initial Expert Network schema with 5 tables:
- expert_profiles: Expert asset data (L1)
- channel_configs: Channel positioning (L2)
- channel_expert_links: Expert ↔ Channel junction (L2)
- weekly_plans: Weekly content plans (L3)
- trust_gate_results: Trust gate evaluation results (L4)
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20260319000000'
down_revision = None
branch_labels = ('expert_network',)
depends_on = None


def upgrade():
    """
    Create Expert Network schema and tables.
    All tables use workspace_id (string) for multi-workspace support.
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    # L1: Expert Asset Layer
    if 'expert_profiles' not in existing_tables:
        op.create_table(
            'expert_profiles',
            sa.Column('id', sa.String(36), primary_key=True, nullable=False),
            sa.Column('workspace_id', sa.String(255), nullable=False),
            sa.Column('name', sa.String(255), nullable=False),
            sa.Column('title', sa.String(255), nullable=True),
            sa.Column('bio', sa.Text(), nullable=True),
            sa.Column('avatar_url', sa.String(500), nullable=True),
            sa.Column('credentials', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default='[]'),
            sa.Column('topic_scope', postgresql.ARRAY(sa.String), nullable=True),
            sa.Column('forbidden_zones', postgresql.ARRAY(sa.String), nullable=True),
            sa.Column('liability_scope', sa.String(50), nullable=False, server_default='general_education'),
            sa.Column('tone_profile', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column('representative_viewpoints', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default='[]'),
            sa.Column('authorization_level', sa.String(50), nullable=False, server_default='review_only'),
            sa.Column('knowledge_assets', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default='[]'),
            sa.Column('status', sa.String(50), nullable=False, server_default='draft'),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
            sa.Column('created_by', sa.String(255), nullable=True),
        )
        op.create_index('ix_expert_profiles_workspace', 'expert_profiles', ['workspace_id'])
        op.create_index('ix_expert_profiles_status', 'expert_profiles', ['status'])
        op.create_index('ix_expert_profiles_auth_level', 'expert_profiles', ['authorization_level'])
        op.create_index('ix_expert_profiles_liability', 'expert_profiles', ['liability_scope'])

    # L2: Channel Intent Layer
    if 'channel_configs' not in existing_tables:
        op.create_table(
            'channel_configs',
            sa.Column('id', sa.String(36), primary_key=True, nullable=False),
            sa.Column('workspace_id', sa.String(255), nullable=False),
            sa.Column('name', sa.String(255), nullable=False),
            sa.Column('host_profile', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column('audience_persona', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column('content_pillars', postgresql.ARRAY(sa.String), nullable=True),
            sa.Column('conversion_funnel', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column('status', sa.String(50), nullable=False, server_default='draft'),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        )
        op.create_index('ix_channel_configs_workspace', 'channel_configs', ['workspace_id'])

    # L2: Channel ↔ Expert junction
    if 'channel_expert_links' not in existing_tables:
        op.create_table(
            'channel_expert_links',
            sa.Column('id', sa.String(36), primary_key=True, nullable=False),
            sa.Column('channel_id', sa.String(36), nullable=False),
            sa.Column('expert_id', sa.String(36), nullable=False),
            sa.Column('role', sa.String(100), nullable=True),
            sa.Column('joined_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
            sa.ForeignKeyConstraint(['channel_id'], ['channel_configs.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['expert_id'], ['expert_profiles.id'], ondelete='CASCADE'),
        )
        op.create_index('ix_channel_expert_links_channel', 'channel_expert_links', ['channel_id'])
        op.create_index('ix_channel_expert_links_expert', 'channel_expert_links', ['expert_id'])

    # L3: Collaboration Compiler
    if 'weekly_plans' not in existing_tables:
        op.create_table(
            'weekly_plans',
            sa.Column('id', sa.String(36), primary_key=True, nullable=False),
            sa.Column('workspace_id', sa.String(255), nullable=False),
            sa.Column('channel_id', sa.String(36), nullable=False),
            sa.Column('week_start', sa.DateTime(), nullable=False),
            sa.Column('theme', sa.String(500), nullable=True),
            sa.Column('status', sa.String(50), nullable=False, server_default='draft'),
            sa.Column('slots', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default='[]'),
            sa.Column('community_signals', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
            sa.ForeignKeyConstraint(['channel_id'], ['channel_configs.id'], ondelete='CASCADE'),
        )
        op.create_index('ix_weekly_plans_workspace', 'weekly_plans', ['workspace_id'])
        op.create_index('ix_weekly_plans_channel', 'weekly_plans', ['channel_id'])
        op.create_index('ix_weekly_plans_week', 'weekly_plans', ['week_start'])

    # L4: Trust / Approval Layer
    if 'trust_gate_results' not in existing_tables:
        op.create_table(
            'trust_gate_results',
            sa.Column('id', sa.String(36), primary_key=True, nullable=False),
            sa.Column('workspace_id', sa.String(255), nullable=False),
            sa.Column('weekly_plan_id', sa.String(36), nullable=True),
            sa.Column('slot_index', sa.Integer(), nullable=True),
            sa.Column('content_ref', sa.String(500), nullable=True),
            sa.Column('content_risk_level', sa.String(20), nullable=False, server_default='low'),
            sa.Column('required_approval', sa.String(50), nullable=False, server_default='auto'),
            sa.Column('source_label', sa.String(100), nullable=False, server_default='ai_from_authorized_kb'),
            sa.Column('liability_label', sa.String(100), nullable=False, server_default='educational_only'),
            sa.Column('audit_trail', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default='[]'),
            sa.Column('approved', sa.Boolean(), nullable=True),
            sa.Column('approved_at', sa.DateTime(), nullable=True),
            sa.Column('approved_by', sa.String(255), nullable=True),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
            sa.ForeignKeyConstraint(['weekly_plan_id'], ['weekly_plans.id']),
        )
        op.create_index('ix_trust_gate_results_workspace', 'trust_gate_results', ['workspace_id'])
        op.create_index('ix_trust_gate_results_plan', 'trust_gate_results', ['weekly_plan_id'])


def downgrade():
    """Drop Expert Network schema and tables."""
    op.drop_index('ix_trust_gate_results_plan', table_name='trust_gate_results')
    op.drop_index('ix_trust_gate_results_workspace', table_name='trust_gate_results')
    op.drop_table('trust_gate_results')

    op.drop_index('ix_weekly_plans_week', table_name='weekly_plans')
    op.drop_index('ix_weekly_plans_channel', table_name='weekly_plans')
    op.drop_index('ix_weekly_plans_workspace', table_name='weekly_plans')
    op.drop_table('weekly_plans')

    op.drop_index('ix_channel_expert_links_expert', table_name='channel_expert_links')
    op.drop_index('ix_channel_expert_links_channel', table_name='channel_expert_links')
    op.drop_table('channel_expert_links')

    op.drop_index('ix_channel_configs_workspace', table_name='channel_configs')
    op.drop_table('channel_configs')

    op.drop_index('ix_expert_profiles_liability', table_name='expert_profiles')
    op.drop_index('ix_expert_profiles_auth_level', table_name='expert_profiles')
    op.drop_index('ix_expert_profiles_status', table_name='expert_profiles')
    op.drop_index('ix_expert_profiles_workspace', table_name='expert_profiles')
    op.drop_table('expert_profiles')
