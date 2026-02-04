"""Add action library tables (jobs and artifacts)

Revision ID: 20260107000000
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
revision = '20260107000000'
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

            # Job association (optional)
            sa.Column('job_id', postgresql.UUID(as_uuid=True), nullable=True),

            # Step information
            sa.Column('step_code', sa.String(128), nullable=False),
            sa.Column('project_id', postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column('input_hash', sa.String(64), nullable=False),

            # Artifact data
            sa.Column('data', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column('status', sa.String(32), nullable=False, server_default='completed'),

            # Dependencies
            sa.Column('depends_on', postgresql.JSONB(astext_type=sa.Text()), server_default='[]'),

            # Metadata
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
            sa.Column('expires_at', sa.DateTime(), nullable=True),
        )

        # Create indexes
        op.create_index('idx_artifacts_job', 'yogacoach_artifacts', ['job_id'])
        op.create_index('idx_artifacts_step', 'yogacoach_artifacts', ['step_code'])
        op.create_index('idx_artifacts_input_hash', 'yogacoach_artifacts', ['input_hash'])
        op.create_index('idx_artifacts_project', 'yogacoach_artifacts', ['project_id'])
        op.create_index('idx_artifacts_tenant', 'yogacoach_artifacts', ['tenant_id'])

        # Create unique constraint: same step_code + project_id + input_hash = same artifact
        op.create_unique_constraint(
            'unique_step_input',
            'yogacoach_artifacts',
            ['step_code', 'project_id', 'input_hash']
        )

    # Create yogacoach_teacher_library_actions table
    if 'yogacoach_teacher_library_actions' not in existing_tables:
        op.create_table(
            'yogacoach_teacher_library_actions',
            sa.Column('action_id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column('tenant_id', sa.String(64), nullable=False),
            sa.Column('library_id', postgresql.UUID(as_uuid=True), nullable=False),

            # Action metadata
            sa.Column('asana_id', sa.String(64), nullable=False),
            sa.Column('asana_name', sa.String(255), nullable=False),
            sa.Column('chapter_id', postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column('video_id', postgresql.UUID(as_uuid=True), nullable=True),

            # Timing
            sa.Column('start_time', sa.Float(), nullable=False),
            sa.Column('end_time', sa.Float(), nullable=False),
            sa.Column('duration', sa.Float(), nullable=False),

            # Phase information
            sa.Column('phases', postgresql.JSONB(astext_type=sa.Text()), server_default='{}'),

            # Keyframes and keypoints
            sa.Column('keyframes', postgresql.JSONB(astext_type=sa.Text()), server_default='[]'),
            sa.Column('representative_keyframe', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column('keypoints_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),

            # Metrics
            sa.Column('pose_metrics', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column('quality_score', sa.Float(), nullable=True),

            # Metadata
            sa.Column('tags', postgresql.JSONB(astext_type=sa.Text()), server_default='[]'),
            sa.Column('notes', sa.Text(), nullable=True),

            # Timestamps
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), onupdate=sa.text('CURRENT_TIMESTAMP')),

            # Foreign key
            sa.ForeignKeyConstraint(['library_id'], ['yogacoach_teacher_libraries.library_id'], ondelete='CASCADE'),
        )

        # Create indexes
        op.create_index('idx_actions_library', 'yogacoach_teacher_library_actions', ['library_id'])
        op.create_index('idx_actions_asana', 'yogacoach_teacher_library_actions', ['asana_id'])
        op.create_index('idx_actions_tenant', 'yogacoach_teacher_library_actions', ['tenant_id'])

    # Create yogacoach_similarity_assessments table
    if 'yogacoach_similarity_assessments' not in existing_tables:
        op.create_table(
            'yogacoach_similarity_assessments',
            sa.Column('assessment_id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column('tenant_id', sa.String(64), nullable=False),

            # Associations
            sa.Column('session_id', sa.String(255), nullable=True),
            sa.Column('student_id', sa.String(255), nullable=True),
            sa.Column('library_id', postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column('project_id', postgresql.UUID(as_uuid=True), nullable=True),

            # Assessment data
            sa.Column('overall_score', sa.Float(), nullable=False),
            sa.Column('quality_rating', sa.String(32), nullable=False),
            sa.Column('summary', sa.Text(), nullable=True),

            # Detailed scores
            sa.Column('pose_similarity', sa.Float(), nullable=True),
            sa.Column('timing_similarity', sa.Float(), nullable=True),
            sa.Column('sequence_similarity', sa.Float(), nullable=True),

            # Action breakdown
            sa.Column('action_breakdown', postgresql.JSONB(astext_type=sa.Text()), server_default='[]'),
            sa.Column('improvement_suggestions', postgresql.JSONB(astext_type=sa.Text()), server_default='[]'),

            # Report data
            sa.Column('report_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),

            # Media
            sa.Column('report_url', sa.String(512), nullable=True),
            sa.Column('comparison_video_url', sa.String(512), nullable=True),

            # Timestamps
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        )

        # Create indexes
        op.create_index('idx_assessments_session', 'yogacoach_similarity_assessments', ['session_id'])
        op.create_index('idx_assessments_student', 'yogacoach_similarity_assessments', ['student_id'])
        op.create_index('idx_assessments_library', 'yogacoach_similarity_assessments', ['library_id'])
        op.create_index('idx_assessments_tenant', 'yogacoach_similarity_assessments', ['tenant_id'])
        op.create_index('idx_assessments_project', 'yogacoach_similarity_assessments', ['project_id'])


def downgrade():
    """
    Drop action library tables
    """
    op.drop_table('yogacoach_similarity_assessments')
    op.drop_table('yogacoach_teacher_library_actions')
    op.drop_table('yogacoach_artifacts')
    op.drop_table('yogacoach_action_library_jobs')
