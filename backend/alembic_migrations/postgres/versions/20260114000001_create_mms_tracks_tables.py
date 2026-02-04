"""Create MMS tracks and timeline_items tables

Revision ID: 20260114000001
Revises: 20260114000000
Create Date: 2026-01-14 00:00:01.000000

Creates tables for tracks and timeline items:
- multi_media_studio.mms_tracks
- multi_media_studio.mms_timeline_items
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20260114000001'
down_revision = '20260114000000'
branch_labels = None
depends_on = None


def upgrade():
    """
    Create MMS tracks and timeline_items tables
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Ensure schema exists
    schemas = inspector.get_schema_names()
    if 'multi_media_studio' not in schemas:
        op.execute(sa.text('CREATE SCHEMA multi_media_studio'))

    existing_tables = set(inspector.get_table_names(schema='multi_media_studio'))

    # Create mms_tracks table
    if 'mms_tracks' not in existing_tables:
        op.create_table(
            'mms_tracks',
            sa.Column('track_id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column('project_id', postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column('tenant_id', sa.String(64), nullable=False),
            sa.Column('type', sa.String(32), nullable=False),
            sa.Column('name', sa.String(255), nullable=False),
            sa.Column('height', sa.Integer(), nullable=False, server_default='60'),
            sa.Column('min_height', sa.Integer(), nullable=False, server_default='30'),
            sa.Column('max_height', sa.Integer(), nullable=False, server_default='200'),
            sa.Column('locked', sa.Boolean(), nullable=False, server_default='false'),
            sa.Column('visible', sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('muted', sa.Boolean(), nullable=False, server_default='false'),
            sa.Column('color', sa.String(7), nullable=True),
            sa.Column('order_index', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('meta_data', postgresql.JSONB(astext_type=sa.Text()), server_default='{}'),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), onupdate=sa.text('CURRENT_TIMESTAMP'), nullable=False),
            schema='multi_media_studio'
        )

        # Create indexes (only when creating table)
        op.create_index('idx_tracks_project', 'mms_tracks', ['project_id'], schema='multi_media_studio')
        op.create_index('idx_tracks_tenant', 'mms_tracks', ['tenant_id'], schema='multi_media_studio')
        op.create_index('idx_tracks_type', 'mms_tracks', ['type'], schema='multi_media_studio')

    # Create mms_timeline_items table
    if 'mms_timeline_items' not in existing_tables:
        op.create_table(
            'mms_timeline_items',
            sa.Column('item_id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column('track_id', postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column('project_id', postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column('tenant_id', sa.String(64), nullable=False),
            sa.Column('start_time', sa.Float(), nullable=False),
            sa.Column('end_time', sa.Float(), nullable=False),
            sa.Column('data', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
            sa.Column('meta_data', postgresql.JSONB(astext_type=sa.Text()), server_default='{}'),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), onupdate=sa.text('CURRENT_TIMESTAMP'), nullable=False),
            sa.ForeignKeyConstraint(
                ['track_id'],
                ['multi_media_studio.mms_tracks.track_id'],
                ondelete='CASCADE'
            ),
            schema='multi_media_studio'
        )

        # Create indexes (only when creating table)
        op.create_index('idx_items_track', 'mms_timeline_items', ['track_id'], schema='multi_media_studio')
        op.create_index('idx_items_project', 'mms_timeline_items', ['project_id'], schema='multi_media_studio')
        op.create_index('idx_items_tenant', 'mms_timeline_items', ['tenant_id'], schema='multi_media_studio')
        op.create_index('idx_items_time_range', 'mms_timeline_items', ['start_time', 'end_time'], schema='multi_media_studio')


def downgrade():
    """
    Drop MMS tracks and timeline_items tables
    """
    op.drop_table('mms_timeline_items', schema='multi_media_studio')
    op.drop_table('mms_tracks', schema='multi_media_studio')
