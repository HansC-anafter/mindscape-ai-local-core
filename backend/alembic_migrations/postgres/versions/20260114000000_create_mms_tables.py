"""Create MMS tables (transcriptions, content_analyses)

Revision ID: 20260114000000
Revises: None
Create Date: 2026-01-14 00:00:00.000000

Creates tables for audio transcription and content analysis:
- multi_media_studio.transcriptions
- multi_media_studio.transcription_segments
- multi_media_studio.content_analyses
- multi_media_studio.content_topics

Note: Uses multi_media_studio schema (consistent with VCS schema pattern)
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20260114000000'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    """
    Create MMS tables for transcription and content analysis
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Check if schema exists, create if not
    schemas = inspector.get_schema_names()
    if 'multi_media_studio' not in schemas:
        op.execute(sa.text('CREATE SCHEMA multi_media_studio'))

    existing_tables = set(inspector.get_table_names(schema='multi_media_studio'))

    # Create transcriptions table
    if 'transcriptions' not in existing_tables:
        op.create_table(
            'transcriptions',
            sa.Column('transcription_id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column('tenant_id', sa.String(64), nullable=False),
            sa.Column('project_id', postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column('full_text', sa.Text(), nullable=True),
            sa.Column('language', sa.String(10), nullable=True),
            sa.Column('duration', sa.Float(), nullable=True),
            sa.Column('runtime', sa.String(32), nullable=True),
            sa.Column('model_name', sa.String(128), nullable=True),
            sa.Column('video_ref', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column('meta_data', postgresql.JSONB(astext_type=sa.Text()), server_default='{}'),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), onupdate=sa.text('CURRENT_TIMESTAMP')),
            schema='multi_media_studio'
        )

        op.create_index('idx_transcriptions_tenant', 'transcriptions', ['tenant_id'], schema='multi_media_studio')
        op.create_index('idx_transcriptions_project', 'transcriptions', ['project_id'], schema='multi_media_studio')

    # Create transcription_segments table
    if 'transcription_segments' not in existing_tables:
        op.create_table(
            'transcription_segments',
            sa.Column('segment_id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column('transcription_id', postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column('tenant_id', sa.String(64), nullable=False),
            sa.Column('text', sa.Text(), nullable=False),
            sa.Column('start_time', sa.Float(), nullable=False),
            sa.Column('end_time', sa.Float(), nullable=False),
            sa.Column('confidence', sa.Float(), nullable=True),
            sa.Column('words', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column('meta_data', postgresql.JSONB(astext_type=sa.Text()), server_default='{}'),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
            sa.ForeignKeyConstraint(
                ['transcription_id'],
                ['multi_media_studio.transcriptions.transcription_id'],
                ondelete='CASCADE'
            ),
            schema='multi_media_studio'
        )

        op.create_index('idx_segments_transcription', 'transcription_segments', ['transcription_id'], schema='multi_media_studio')
        op.create_index('idx_segments_tenant', 'transcription_segments', ['tenant_id'], schema='multi_media_studio')

    # Create content_analyses table
    if 'content_analyses' not in existing_tables:
        op.create_table(
            'content_analyses',
            sa.Column('analysis_id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column('tenant_id', sa.String(64), nullable=False),
            sa.Column('project_id', postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column('transcription_id', postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column('summary', sa.Text(), nullable=True),
            sa.Column('language', sa.String(10), nullable=True),
            sa.Column('key_points', postgresql.JSONB(astext_type=sa.Text()), server_default='[]'),
            sa.Column('domain_hints', postgresql.JSONB(astext_type=sa.Text()), server_default='[]'),
            sa.Column('meta_data', postgresql.JSONB(astext_type=sa.Text()), server_default='{}'),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), onupdate=sa.text('CURRENT_TIMESTAMP')),
            sa.ForeignKeyConstraint(
                ['transcription_id'],
                ['multi_media_studio.transcriptions.transcription_id'],
                ondelete='SET NULL'
            ),
            schema='multi_media_studio'
        )

        op.create_index('idx_analyses_tenant', 'content_analyses', ['tenant_id'], schema='multi_media_studio')
        op.create_index('idx_analyses_project', 'content_analyses', ['project_id'], schema='multi_media_studio')
        op.create_index('idx_analyses_transcription', 'content_analyses', ['transcription_id'], schema='multi_media_studio')

    # Create content_topics table
    if 'content_topics' not in existing_tables:
        op.create_table(
            'content_topics',
            sa.Column('topic_id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column('analysis_id', postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column('tenant_id', sa.String(64), nullable=False),
            sa.Column('topic_code', sa.String(128), nullable=False),
            sa.Column('name', sa.String(255), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('confidence', sa.Float(), nullable=True),
            sa.Column('segment_indices', postgresql.JSONB(astext_type=sa.Text()), server_default='[]'),
            sa.Column('meta_data', postgresql.JSONB(astext_type=sa.Text()), server_default='{}'),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
            sa.ForeignKeyConstraint(
                ['analysis_id'],
                ['multi_media_studio.content_analyses.analysis_id'],
                ondelete='CASCADE'
            ),
            schema='multi_media_studio'
        )

        op.create_index('idx_topics_analysis', 'content_topics', ['analysis_id'], schema='multi_media_studio')
        op.create_index('idx_topics_tenant', 'content_topics', ['tenant_id'], schema='multi_media_studio')
        op.create_index('idx_topics_code', 'content_topics', ['topic_code'], schema='multi_media_studio')


def downgrade():
    """
    Drop MMS tables
    """
    op.drop_table('content_topics', schema='multi_media_studio')
    op.drop_table('content_analyses', schema='multi_media_studio')
    op.drop_table('transcription_segments', schema='multi_media_studio')
    op.drop_table('transcriptions', schema='multi_media_studio')
