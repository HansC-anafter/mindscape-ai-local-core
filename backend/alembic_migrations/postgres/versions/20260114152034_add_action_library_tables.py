"""Add action library tables (jobs and artifacts)

Revision ID: 20260114152034
Revises: 20260106230000
Create Date: 2025-01-07 00:00:00.000000

Adds tables for workflow job tracking and artifact storage:
- yogacoach_action_library_jobs: Tracks workflow execution
- yogacoach_artifacts: Stores reusable execution artifacts

Note: No schema prefix (consistent with yogacoach_teachers, yogacoach_teacher_libraries)
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import logging

logger = logging.getLogger(__name__)

# revision identifiers, used by Alembic.
revision = '20260114152034'
down_revision = '20260106230000'
branch_labels = None
depends_on = None


def upgrade():
    """
    Create action library tables for workflow orchestration
    Also adds extension_data column to yogacoach_teacher_libraries if it doesn't exist
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    # Add extension_data column to yogacoach_teacher_libraries if it doesn't exist
    if 'yogacoach_teacher_libraries' in existing_tables:
        # Check if column already exists
        columns = [col['name'] for col in inspector.get_columns('yogacoach_teacher_libraries')]
        if 'extension_data' not in columns:
            op.add_column(
                'yogacoach_teacher_libraries',
                sa.Column('extension_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True)
            )
            logger.info("Added extension_data column to yogacoach_teacher_libraries")

    # Create yogacoach_action_library_jobs table
    if 'yogacoach_action_library_jobs' not in existing_tables:
        op.create_table(
            'yogacoach_action_library_jobs',
            sa.Column('job_id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column('tenant_id', sa.String(64), nullable=False),

            # Workflow information
            sa.Column('workflow_code', sa.String(128), nullable=False),
            sa.Column('workflow_version', sa.String(32), server_default='1.0.0'),

            # Associations
            sa.Column('project_id', postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column('library_id', postgresql.UUID(as_uuid=True), nullable=True),

            # Status
            sa.Column('status', sa.String(32), nullable=False, server_default='queued'),
            sa.Column('current_step', sa.String(128), nullable=True),
            sa.Column('completed_steps', postgresql.JSONB(astext_type=sa.Text()), server_default='[]'),

            # Progress
            sa.Column('progress', sa.Float(), server_default='0.0'),
            sa.Column('total_steps', sa.Integer(), server_default='0'),

            # Input/Output
            sa.Column('input_data', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column('artifacts', postgresql.JSONB(astext_type=sa.Text()), server_default='{}'),
            sa.Column('output_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),

            # Error handling
            sa.Column('error_message', sa.Text(), nullable=True),
            sa.Column('error_step', sa.String(128), nullable=True),
            sa.Column('retry_count', sa.Integer(), server_default='0'),
            sa.Column('max_retries', sa.Integer(), server_default='3'),

            # Idempotency
            sa.Column('idempotency_key', sa.String(255), nullable=True, unique=True),
            sa.Column('input_hash', sa.String(64), nullable=True),

            # Timestamps
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
            sa.Column('started_at', sa.DateTime(), nullable=True),
            sa.Column('completed_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), onupdate=sa.text('CURRENT_TIMESTAMP')),
        )

        # Create indexes
        op.create_index('idx_jobs_tenant', 'yogacoach_action_library_jobs', ['tenant_id'])
        op.create_index('idx_jobs_project', 'yogacoach_action_library_jobs', ['project_id'])
        op.create_index('idx_jobs_library', 'yogacoach_action_library_jobs', ['library_id'])
        op.create_index('idx_jobs_status', 'yogacoach_action_library_jobs', ['status'])
        op.create_index('idx_jobs_idempotency', 'yogacoach_action_library_jobs', ['idempotency_key'])
        op.create_index('idx_jobs_input_hash', 'yogacoach_action_library_jobs', ['input_hash'])

    # Create yogacoach_artifacts table
    if 'yogacoach_artifacts' not in existing_tables:
        op.create_table(
            'yogacoach_artifacts',
            sa.Column('artifact_id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column('tenant_id', sa.String(64), nullable=False),

            # Artifact metadata
            sa.Column('artifact_type', sa.String(64), nullable=False),
            sa.Column('artifact_name', sa.String(255), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),

            # Storage
            sa.Column('storage_type', sa.String(32), nullable=False, server_default='database'),
            sa.Column('storage_path', sa.String(512), nullable=True),
            sa.Column('storage_reference', postgresql.JSONB(astext_type=sa.Text()), nullable=True),

            # Content
            sa.Column('content_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column('content_hash', sa.String(64), nullable=True),

            # Associations
            sa.Column('job_id', postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column('library_id', postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column('project_id', postgresql.UUID(as_uuid=True), nullable=True),

            # Metadata
            sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), server_default='{}'),
            sa.Column('tags', postgresql.ARRAY(sa.String(64)), server_default='{}'),

            # Timestamps
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), onupdate=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('expires_at', sa.DateTime(), nullable=True),
        )

        # Create indexes
        op.create_index('idx_artifacts_tenant', 'yogacoach_artifacts', ['tenant_id'])
        op.create_index('idx_artifacts_type', 'yogacoach_artifacts', ['artifact_type'])
        op.create_index('idx_artifacts_job', 'yogacoach_artifacts', ['job_id'])
        op.create_index('idx_artifacts_library', 'yogacoach_artifacts', ['library_id'])
        op.create_index('idx_artifacts_project', 'yogacoach_artifacts', ['project_id'])
        op.create_index('idx_artifacts_hash', 'yogacoach_artifacts', ['content_hash'])


def downgrade():
    """Drop action library tables"""
    op.drop_index('idx_artifacts_hash', table_name='yogacoach_artifacts')
    op.drop_index('idx_artifacts_project', table_name='yogacoach_artifacts')
    op.drop_index('idx_artifacts_library', table_name='yogacoach_artifacts')
    op.drop_index('idx_artifacts_job', table_name='yogacoach_artifacts')
    op.drop_index('idx_artifacts_type', table_name='yogacoach_artifacts')
    op.drop_index('idx_artifacts_tenant', table_name='yogacoach_artifacts')
    op.drop_table('yogacoach_artifacts')

    op.drop_index('idx_jobs_input_hash', table_name='yogacoach_action_library_jobs')
    op.drop_index('idx_jobs_idempotency', table_name='yogacoach_action_library_jobs')
    op.drop_index('idx_jobs_status', table_name='yogacoach_action_library_jobs')
    op.drop_index('idx_jobs_library', table_name='yogacoach_action_library_jobs')
    op.drop_index('idx_jobs_project', table_name='yogacoach_action_library_jobs')
    op.drop_index('idx_jobs_tenant', table_name='yogacoach_action_library_jobs')
    op.drop_table('yogacoach_action_library_jobs')
