"""Rename metadata column to meta_data to avoid SQLAlchemy reserved name conflict

Revision ID: 20260114000002
Revises: 20260114000001
Create Date: 2026-01-14 00:00:02.000000

Renames 'metadata' column to 'meta_data' in mms_tracks and mms_timeline_items tables
to avoid SQLAlchemy reserved name conflict.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20260114000002'
down_revision = '20260114000001'
branch_labels = None
depends_on = None


def upgrade():
    """
    Rename metadata column to meta_data in all MMS tables if they exist
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    existing_tables = set(inspector.get_table_names(schema='multi_media_studio'))

    # Tables that may have metadata column
    tables_to_check = [
        'mms_tracks',
        'mms_timeline_items',
        'transcriptions',
        'transcription_segments',
        'content_analyses',
        'content_topics'
    ]

    for table_name in tables_to_check:
        if table_name in existing_tables:
            columns = {col['name']: col for col in inspector.get_columns(table_name, schema='multi_media_studio')}
            if 'metadata' in columns and 'meta_data' not in columns:
                op.alter_column(table_name, 'metadata', new_column_name='meta_data', schema='multi_media_studio')
                print(f"Renamed 'metadata' to 'meta_data' in {table_name}")


def downgrade():
    """
    Rename meta_data column back to metadata (reverse operation)
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    existing_tables = set(inspector.get_table_names(schema='multi_media_studio'))

    # Tables that may have meta_data column
    tables_to_check = [
        'mms_tracks',
        'mms_timeline_items',
        'transcriptions',
        'transcription_segments',
        'content_analyses',
        'content_topics'
    ]

    for table_name in tables_to_check:
        if table_name in existing_tables:
            columns = {col['name']: col for col in inspector.get_columns(table_name, schema='multi_media_studio')}
            if 'meta_data' in columns and 'metadata' not in columns:
                op.alter_column(table_name, 'meta_data', new_column_name='metadata', schema='multi_media_studio')
