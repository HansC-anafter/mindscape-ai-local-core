"""add runtime_environments table

Revision ID: 20260103000000
Revises: 20251227174800
Create Date: 2026-01-03 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20260103000000'
down_revision = '20251227174800'
branch_labels = None
depends_on = None


def upgrade():
    """Create runtime_environments table"""
    op.create_table(
        'runtime_environments',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('icon', sa.String(), nullable=True),
        sa.Column('config_url', sa.String(), nullable=False),
        sa.Column('auth_type', sa.String(), nullable=False, server_default='none'),
        sa.Column('auth_config', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('status', sa.String(), nullable=False, server_default='not_configured'),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('supports_dispatch', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('supports_cell', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('recommended_for_dispatch', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('extra_metadata', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes
    op.create_index('ix_runtime_environments_user_id', 'runtime_environments', ['user_id'])
    op.create_index('ix_runtime_environments_status', 'runtime_environments', ['status'])


def downgrade():
    """Drop runtime_environments table"""
    op.drop_index('ix_runtime_environments_status', table_name='runtime_environments')
    op.drop_index('ix_runtime_environments_user_id', table_name='runtime_environments')
    op.drop_table('runtime_environments')

