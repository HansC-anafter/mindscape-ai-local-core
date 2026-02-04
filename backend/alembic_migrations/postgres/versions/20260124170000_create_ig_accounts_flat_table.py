"""Create IG accounts flat table

Revision ID: 20260124170000
Revises:
Create Date: 2026-01-24 17:00:00.000000

Creates ig_accounts_flat table for analysis-ready account snapshots.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20260124170000'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if 'ig_accounts_flat' not in existing_tables:
        op.create_table(
            'ig_accounts_flat',
            sa.Column('id', sa.String(36), primary_key=True, nullable=False),
            sa.Column('workspace_id', sa.String(255), nullable=False),
            sa.Column('seed', sa.String(255), nullable=False),
            sa.Column('source_handle', sa.String(255), nullable=True),
            sa.Column('source_profile_ref', sa.String(512), nullable=True),
            sa.Column('handle', sa.String(255), nullable=False),
            sa.Column('name', sa.String(255), nullable=True),
            sa.Column('is_verified', sa.Boolean(), nullable=True),
            sa.Column('follower_count', sa.Integer(), nullable=True),
            sa.Column('following_count', sa.Integer(), nullable=True),
            sa.Column('post_count', sa.Integer(), nullable=True),
            sa.Column('bio', sa.Text(), nullable=True),
            sa.Column('external_url', sa.String(512), nullable=True),
            sa.Column('profile_picture_url', sa.String(512), nullable=True),
            sa.Column('category', sa.String(255), nullable=True),
            sa.Column('tags_json', sa.Text(), nullable=True),
            sa.Column('captured_at', sa.String(64), nullable=False),
            sa.Column('execution_id', sa.String(64), nullable=True),
            sa.Column('trace_id', sa.String(64), nullable=True),
            sa.Column('artifact_id', sa.String(64), nullable=True),
            sa.Column('schema_version', sa.String(128), nullable=True),
            sa.Column('seed_version', sa.String(128), nullable=True),
            sa.Column('capture_method', sa.String(64), nullable=True),
            sa.Column('run_mode', sa.String(32), nullable=True),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        )
        op.create_index('ix_ig_accounts_flat_workspace', 'ig_accounts_flat', ['workspace_id'])
        op.create_index('ix_ig_accounts_flat_seed', 'ig_accounts_flat', ['seed'])
        op.create_index('ix_ig_accounts_flat_handle', 'ig_accounts_flat', ['handle'])
        op.create_index('ix_ig_accounts_flat_captured_at', 'ig_accounts_flat', ['captured_at'])
        op.create_index(
            'uq_ig_accounts_flat_workspace_seed_handle_captured',
            'ig_accounts_flat',
            ['workspace_id', 'seed', 'handle', 'captured_at'],
            unique=True
        )


def downgrade():
    op.drop_index('uq_ig_accounts_flat_workspace_seed_handle_captured', table_name='ig_accounts_flat')
    op.drop_index('ix_ig_accounts_flat_captured_at', table_name='ig_accounts_flat')
    op.drop_index('ix_ig_accounts_flat_handle', table_name='ig_accounts_flat')
    op.drop_index('ix_ig_accounts_flat_seed', table_name='ig_accounts_flat')
    op.drop_index('ix_ig_accounts_flat_workspace', table_name='ig_accounts_flat')
    op.drop_table('ig_accounts_flat')
