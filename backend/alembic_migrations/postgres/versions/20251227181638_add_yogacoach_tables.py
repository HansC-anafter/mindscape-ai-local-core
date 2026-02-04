"""Add YogaCoach tables (DEPRECATED - MIGRATED TO TENANT DB)

Revision ID: 20251227181638
Revises: 20260103000000
Create Date: 2025-12-27 18:16:38.000000

⚠️ DEPRECATED: 此遷移腳本已廢棄
⚠️ Tenant-specific 表已遷移到 tenant-app 遷移目錄：migrations/tenant-app/yogacoach/versions/

此遷移腳本保留在 Cloud DB 中僅用於歷史記錄和向後兼容。
實際的 tenant-specific 表應該通過 tenant-db-provisioner 在 tenant DB 中創建。

架構違規的表（應該在 CRS-hub/site-hub DB）：
- yogacoach_plans (CRS-hub)
- yogacoach_subscriptions (CRS-hub)
- yogacoach_usage_records (CRS-hub)
- yogacoach_quota_reservations (CRS-hub)
- yogacoach_invoices (site-hub)
- yogacoach_billing_records (site-hub)

Tenant-specific 表（已遷移到 tenant-app）：
- yogacoach_sessions, yogacoach_jobs, yogacoach_share_links
- yogacoach_user_channels, yogacoach_privacy_audit_logs
- yogacoach_knowledge_entries, yogacoach_knowledge_vectors, yogacoach_conversations
- yogacoach_teachers, yogacoach_teacher_libraries, yogacoach_demo_videos
- yogacoach_rubrics, yogacoach_rubric_reviews
- yogacoach_courses, yogacoach_course_bookings, yogacoach_payment_links
- yogacoach_student_profiles, yogacoach_session_history, yogacoach_progress_snapshots
- yogacoach_unsubscribes, yogacoach_push_history

相關文檔：
- mindscape-ai-cloud/capabilities/yogacoach/docs/todos/tenant-db-architecture/WRONG_LOCATION_AUDIT.md
- mindscape-ai-cloud/migrations/tenant-app/yogacoach/versions/20251231120001_create_yogacoach_tables.py
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20251227181638'
down_revision = '20260103000000'
branch_labels = None
depends_on = None


def upgrade():
    """
    Create all YogaCoach tables with multi-tenancy support.
    All tables include tenant_id for isolation.
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    # Create yogacoach_plans table
    if 'yogacoach_plans' not in existing_tables:
        op.create_table(
            'yogacoach_plans',
            sa.Column('plan_id', sa.String(50), primary_key=True, nullable=False),
            sa.Column('name', sa.String(255), nullable=False),
            sa.Column('quota', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column('price_usd', sa.String(20)),
            sa.Column('billing_cycle', sa.String(50)),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        )

    # Create yogacoach_subscriptions table
    if 'yogacoach_subscriptions' not in existing_tables:
        op.create_table(
            'yogacoach_subscriptions',
            sa.Column('subscription_id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column('tenant_id', sa.String(255), nullable=False),
            sa.Column('user_id', sa.String(255)),
            sa.Column('teacher_id', postgresql.UUID(as_uuid=True)),
            sa.Column('plan_id', sa.String(50), sa.ForeignKey('yogacoach_plans.plan_id')),
            sa.Column('status', sa.String(50), nullable=False, server_default='active'),
            sa.Column('current_period_start', sa.Date()),
            sa.Column('current_period_end', sa.Date()),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        )
        op.create_index('idx_yogacoach_subscriptions_tenant', 'yogacoach_subscriptions', ['tenant_id'])

    # Create yogacoach_sessions table
    if 'yogacoach_sessions' not in existing_tables:
        op.create_table(
            'yogacoach_sessions',
            sa.Column('session_id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column('tenant_id', sa.String(255), nullable=False),
            sa.Column('actor_id', sa.String(255), nullable=False),
            sa.Column('subject_user_id', sa.String(255), nullable=False),
            sa.Column('teacher_id', sa.String(255)),
            sa.Column('plan_id', sa.String(50)),
            sa.Column('channel', sa.String(50)),
            sa.Column('idempotency_key', sa.String(255), unique=True),
            sa.Column('status', sa.String(50), server_default='created'),
            sa.Column('liff_context', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('updated_at', sa.DateTime(), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        )
        op.create_index('idx_yogacoach_sessions_tenant', 'yogacoach_sessions', ['tenant_id'])
        op.create_index('idx_yogacoach_sessions_user', 'yogacoach_sessions', ['tenant_id', 'subject_user_id'])
        op.create_index('idx_yogacoach_sessions_idempotency', 'yogacoach_sessions', ['idempotency_key'])

    # Create yogacoach_jobs table
    if 'yogacoach_jobs' not in existing_tables:
        op.create_table(
            'yogacoach_jobs',
            sa.Column('job_id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column('session_id', postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column('tenant_id', sa.String(255), nullable=False),
            sa.Column('pipeline_version', sa.String(50), nullable=False),
            sa.Column('idempotency_key', sa.String(255), nullable=False),
            sa.Column('status', sa.String(50), nullable=False, server_default='queued'),
            sa.Column('progress', postgresql.JSONB(astext_type=sa.Text())),
            sa.Column('error_message', sa.Text()),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.UniqueConstraint('session_id', 'pipeline_version', name='uq_session_pipeline'),
        )
        op.create_index('idx_yogacoach_jobs_tenant', 'yogacoach_jobs', ['tenant_id'])
        op.create_index('idx_yogacoach_jobs_status', 'yogacoach_jobs', ['status'])
        op.create_index('idx_yogacoach_jobs_idempotency', 'yogacoach_jobs', ['idempotency_key'])

    # Create yogacoach_usage_records table
    if 'yogacoach_usage_records' not in existing_tables:
        op.create_table(
            'yogacoach_usage_records',
            sa.Column('usage_id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column('tenant_id', sa.String(255), nullable=False),
            sa.Column('subscription_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('yogacoach_subscriptions.subscription_id')),
            sa.Column('session_id', postgresql.UUID(as_uuid=True)),
            sa.Column('minutes_used', sa.Integer(), nullable=False),
            sa.Column('status', sa.String(50), server_default='recorded'),
            sa.Column('recorded_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        )
        op.create_index('idx_yogacoach_usage_tenant', 'yogacoach_usage_records', ['tenant_id'])
        op.create_index('idx_yogacoach_usage_subscription', 'yogacoach_usage_records', ['subscription_id'])
        op.create_index('idx_yogacoach_usage_session', 'yogacoach_usage_records', ['session_id'])

    # Create yogacoach_share_links table
    if 'yogacoach_share_links' not in existing_tables:
        op.create_table(
            'yogacoach_share_links',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column('tenant_id', sa.String(255), nullable=False),
            sa.Column('session_id', postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column('short_code', sa.String(50), unique=True, nullable=False),
            sa.Column('signature', sa.String(50), nullable=False),
            sa.Column('expires_at', sa.DateTime(), nullable=False),
            sa.Column('access_scope', sa.String(50), server_default='owner_only'),
            sa.Column('created_by', sa.String(255)),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        )
        op.create_index('idx_yogacoach_share_links_tenant', 'yogacoach_share_links', ['tenant_id'])
        op.create_index('idx_yogacoach_share_links_short_code', 'yogacoach_share_links', ['short_code'])
        op.create_index('idx_yogacoach_share_links_expires', 'yogacoach_share_links', ['expires_at'])

    # Create yogacoach_user_channels table
    if 'yogacoach_user_channels' not in existing_tables:
        op.create_table(
            'yogacoach_user_channels',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column('user_id', sa.String(255), nullable=False),
            sa.Column('tenant_id', sa.String(255), nullable=False),
            sa.Column('channel', sa.String(50), nullable=False),
            sa.Column('channel_user_id', sa.String(255), nullable=False),
            sa.Column('bind_method', sa.String(50)),
            sa.Column('push_enabled', sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('bot_blocked', sa.Boolean(), nullable=False, server_default='false'),
            sa.Column('bind_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.UniqueConstraint('tenant_id', 'user_id', 'channel', name='uq_user_channel'),
        )
        op.create_index('idx_yogacoach_user_channels_tenant', 'yogacoach_user_channels', ['tenant_id'])

    # Create yogacoach_privacy_audit_logs table
    if 'yogacoach_privacy_audit_logs' not in existing_tables:
        op.create_table(
            'yogacoach_privacy_audit_logs',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column('tenant_id', sa.String(255), nullable=False),
            sa.Column('session_id', postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column('object_key_encrypted', sa.Text(), nullable=False),
            sa.Column('lifecycle_rule_id', sa.String(255)),
            sa.Column('expires_at', sa.DateTime(), nullable=False),
            sa.Column('deletion_scheduled_at', sa.DateTime()),
            sa.Column('status', sa.String(50), server_default='scheduled'),
            sa.Column('verified_at', sa.DateTime()),
            sa.Column('error_message', sa.Text()),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        )
        op.create_index('idx_yogacoach_privacy_audit_tenant', 'yogacoach_privacy_audit_logs', ['tenant_id'])
        op.create_index('idx_yogacoach_privacy_audit_expires', 'yogacoach_privacy_audit_logs', ['expires_at'])

    # Create yogacoach_quota_reservations table
    if 'yogacoach_quota_reservations' not in existing_tables:
        op.create_table(
            'yogacoach_quota_reservations',
            sa.Column('reservation_id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column('tenant_id', sa.String(255), nullable=False),
            sa.Column('subscription_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('yogacoach_subscriptions.subscription_id')),
            sa.Column('session_id', postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column('billable_minutes_reserved', sa.Integer(), nullable=False),
            sa.Column('expires_at', sa.DateTime(), nullable=False),
            sa.Column('status', sa.String(50), server_default='reserved'),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        )
        op.create_index('idx_yogacoach_quota_reservations_tenant', 'yogacoach_quota_reservations', ['tenant_id'])
        op.create_index('idx_yogacoach_quota_reservations_expires', 'yogacoach_quota_reservations', ['expires_at'])

    # Create yogacoach_knowledge_entries table
    if 'yogacoach_knowledge_entries' not in existing_tables:
        op.create_table(
            'yogacoach_knowledge_entries',
            sa.Column('entry_id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column('tenant_id', sa.String(255), nullable=False),
            sa.Column('title', sa.String(255), nullable=False),
            sa.Column('content', sa.Text(), nullable=False),
            sa.Column('asana_id', sa.String(100)),
            sa.Column('entry_type', sa.String(50)),
            sa.Column('language', sa.String(10), server_default='zh-TW'),
            sa.Column('version', sa.String(50)),
            sa.Column('status', sa.String(50), server_default='published'),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        )
        op.create_index('idx_knowledge_entries_tenant', 'yogacoach_knowledge_entries', ['tenant_id'])
        op.create_index('idx_knowledge_entries_asana', 'yogacoach_knowledge_entries', ['asana_id'])

    # Create yogacoach_knowledge_vectors table
    if 'yogacoach_knowledge_vectors' not in existing_tables:
        op.create_table(
            'yogacoach_knowledge_vectors',
            sa.Column('vector_id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column('tenant_id', sa.String(255), nullable=False),
            sa.Column('entry_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('yogacoach_knowledge_entries.entry_id'), nullable=False),
            sa.Column('embedding', sa.Text()),
            sa.Column('chunk_text', sa.Text(), nullable=False),
            sa.Column('chunk_index', sa.Integer(), server_default='0'),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        )
        op.create_index('idx_knowledge_vectors_tenant', 'yogacoach_knowledge_vectors', ['tenant_id'])
        op.create_index('idx_knowledge_vectors_entry', 'yogacoach_knowledge_vectors', ['entry_id'])

    # Create yogacoach_conversations table
    if 'yogacoach_conversations' not in existing_tables:
        op.create_table(
            'yogacoach_conversations',
            sa.Column('conversation_id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column('tenant_id', sa.String(255), nullable=False),
            sa.Column('user_id', sa.String(255), nullable=False),
            sa.Column('session_id', postgresql.UUID(as_uuid=True)),
            sa.Column('messages', postgresql.JSONB(astext_type=sa.Text())),
            sa.Column('intent', postgresql.JSONB(astext_type=sa.Text())),
            sa.Column('sources', postgresql.JSONB(astext_type=sa.Text())),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        )
        op.create_index('idx_conversations_tenant', 'yogacoach_conversations', ['tenant_id'])
        op.create_index('idx_conversations_user', 'yogacoach_conversations', ['tenant_id', 'user_id'])

    # Create yogacoach_teachers table
    if 'yogacoach_teachers' not in existing_tables:
        op.create_table(
            'yogacoach_teachers',
            sa.Column('teacher_id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column('tenant_id', sa.String(255), nullable=False),
            sa.Column('name', sa.String(255), nullable=False),
            sa.Column('studio_name', sa.String(255)),
            sa.Column('certification', sa.String(255)),
            sa.Column('teaching_style', sa.String(255)),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        )
        op.create_index('idx_yogacoach_teachers_tenant', 'yogacoach_teachers', ['tenant_id'])

    # Create yogacoach_teacher_libraries table
    if 'yogacoach_teacher_libraries' not in existing_tables:
        op.create_table(
            'yogacoach_teacher_libraries',
            sa.Column('library_id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column('tenant_id', sa.String(255), nullable=False),
            sa.Column('teacher_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('yogacoach_teachers.teacher_id'), nullable=False),
            sa.Column('library_version', sa.String(50), server_default='v1'),
            sa.Column('asana_whitelist', postgresql.JSONB(astext_type=sa.Text())),
            sa.Column('series', postgresql.JSONB(astext_type=sa.Text())),
            sa.Column('feedback_policy', postgresql.JSONB(astext_type=sa.Text())),
            sa.Column('status', sa.String(50), server_default='draft'),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        )
        op.create_index('idx_yogacoach_teacher_libraries_tenant', 'yogacoach_teacher_libraries', ['tenant_id'])
        op.create_index('idx_yogacoach_teacher_libraries_teacher', 'yogacoach_teacher_libraries', ['teacher_id'])

    # Create yogacoach_demo_videos table
    if 'yogacoach_demo_videos' not in existing_tables:
        op.create_table(
            'yogacoach_demo_videos',
            sa.Column('demo_video_id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column('tenant_id', sa.String(255), nullable=False),
            sa.Column('teacher_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('yogacoach_teachers.teacher_id'), nullable=False),
            sa.Column('asana_id', sa.String(100)),
            sa.Column('source', sa.String(50)),
            sa.Column('video_id', sa.String(255)),
            sa.Column('url', sa.Text()),
            sa.Column('duration_seconds', sa.Integer()),
            sa.Column('chapters', postgresql.JSONB(astext_type=sa.Text())),
            sa.Column('mapping_table', postgresql.JSONB(astext_type=sa.Text())),
            sa.Column('chapters_version', sa.String(50), server_default='v1'),
            sa.Column('status', sa.String(50), server_default='draft'),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('published_at', sa.DateTime()),
        )
        op.create_index('idx_yogacoach_demo_videos_tenant', 'yogacoach_demo_videos', ['tenant_id'])
        op.create_index('idx_yogacoach_demo_videos_teacher', 'yogacoach_demo_videos', ['teacher_id'])
        op.create_index('idx_yogacoach_demo_videos_asana', 'yogacoach_demo_videos', ['asana_id'])

    # Create yogacoach_rubrics table
    if 'yogacoach_rubrics' not in existing_tables:
        op.create_table(
            'yogacoach_rubrics',
            sa.Column('rubric_id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column('tenant_id', sa.String(255), nullable=False),
            sa.Column('asana_id', sa.String(100)),
            sa.Column('rubric_version', sa.String(50), server_default='v1'),
            sa.Column('content', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column('status', sa.String(50), server_default='draft'),
            sa.Column('author_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('yogacoach_teachers.teacher_id')),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('published_at', sa.DateTime()),
        )
        op.create_index('idx_yogacoach_rubrics_tenant', 'yogacoach_rubrics', ['tenant_id'])
        op.create_index('idx_yogacoach_rubrics_asana', 'yogacoach_rubrics', ['asana_id'])
        op.create_index('idx_yogacoach_rubrics_status', 'yogacoach_rubrics', ['status'])

    # Create yogacoach_rubric_reviews table
    if 'yogacoach_rubric_reviews' not in existing_tables:
        op.create_table(
            'yogacoach_rubric_reviews',
            sa.Column('review_id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column('tenant_id', sa.String(255), nullable=False),
            sa.Column('rubric_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('yogacoach_rubrics.rubric_id'), nullable=False),
            sa.Column('reviewer_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('yogacoach_teachers.teacher_id'), nullable=False),
            sa.Column('status', sa.String(50), server_default='pending'),
            sa.Column('comments', sa.Text()),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('reviewed_at', sa.DateTime()),
        )
        op.create_index('idx_yogacoach_rubric_reviews_tenant', 'yogacoach_rubric_reviews', ['tenant_id'])
        op.create_index('idx_yogacoach_rubric_reviews_rubric', 'yogacoach_rubric_reviews', ['rubric_id'])

    # Create yogacoach_courses table
    if 'yogacoach_courses' not in existing_tables:
        op.create_table(
            'yogacoach_courses',
            sa.Column('course_id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column('tenant_id', sa.String(255), nullable=False),
            sa.Column('teacher_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('yogacoach_teachers.teacher_id'), nullable=False),
            sa.Column('title', sa.String(255), nullable=False),
            sa.Column('course_datetime', sa.DateTime(), nullable=False),
            sa.Column('max_students', sa.Integer()),
            sa.Column('price_amount', sa.Numeric(10, 2)),
            sa.Column('price_currency', sa.String(10), server_default='TWD'),
            sa.Column('status', sa.String(50), server_default='scheduled'),
            sa.Column('external_calendar_id', sa.String(255)),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        )
        op.create_index('idx_yogacoach_courses_tenant', 'yogacoach_courses', ['tenant_id'])
        op.create_index('idx_yogacoach_courses_teacher', 'yogacoach_courses', ['teacher_id'])
        op.create_index('idx_yogacoach_courses_datetime', 'yogacoach_courses', ['course_datetime'])

    # Create yogacoach_course_bookings table
    if 'yogacoach_course_bookings' not in existing_tables:
        op.create_table(
            'yogacoach_course_bookings',
            sa.Column('booking_id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column('tenant_id', sa.String(255), nullable=False),
            sa.Column('course_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('yogacoach_courses.course_id'), nullable=False),
            sa.Column('user_id', sa.String(255), nullable=False),
            sa.Column('status', sa.String(50), server_default='pending'),
            sa.Column('payment_link_id', postgresql.UUID(as_uuid=True)),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('confirmed_at', sa.DateTime()),
        )
        op.create_index('idx_yogacoach_course_bookings_tenant', 'yogacoach_course_bookings', ['tenant_id'])
        op.create_index('idx_yogacoach_course_bookings_course', 'yogacoach_course_bookings', ['course_id'])
        op.create_index('idx_yogacoach_course_bookings_user', 'yogacoach_course_bookings', ['user_id'])

    # Create yogacoach_invoices table (created before payment_links due to FK dependency)
    if 'yogacoach_invoices' not in existing_tables:
        op.create_table(
            'yogacoach_invoices',
            sa.Column('invoice_id', sa.String(50), primary_key=True, nullable=False),
            sa.Column('tenant_id', sa.String(255), nullable=False),
            sa.Column('subscription_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('yogacoach_subscriptions.subscription_id'), nullable=False),
            sa.Column('billing_period_start', sa.Date(), nullable=False),
            sa.Column('billing_period_end', sa.Date(), nullable=False),
            sa.Column('usage_summary', postgresql.JSONB(astext_type=sa.Text())),
            sa.Column('base_price_usd', sa.Numeric(10, 2)),
            sa.Column('overage_minutes', sa.Integer(), server_default='0'),
            sa.Column('overage_charges_usd', sa.Numeric(10, 2), server_default='0'),
            sa.Column('tax_usd', sa.Numeric(10, 2), server_default='0'),
            sa.Column('total_usd', sa.Numeric(10, 2), nullable=False),
            sa.Column('payment_status', sa.String(50), nullable=False, server_default='pending'),
            sa.Column('payment_method', sa.String(50)),
            sa.Column('transaction_id', sa.String(255)),
            sa.Column('invoice_url', sa.Text()),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('paid_at', sa.DateTime()),
            sa.Column('due_date', sa.Date(), nullable=False),
        )
        op.create_index('idx_yogacoach_invoices_tenant', 'yogacoach_invoices', ['tenant_id'])
        op.create_index('idx_yogacoach_invoices_subscription', 'yogacoach_invoices', ['subscription_id'])
        op.create_index('idx_yogacoach_invoices_billing_period', 'yogacoach_invoices', ['billing_period_start', 'billing_period_end'])
        op.create_index('idx_yogacoach_invoices_payment_status', 'yogacoach_invoices', ['payment_status'])

    # Create yogacoach_payment_links table
    if 'yogacoach_payment_links' not in existing_tables:
        op.create_table(
            'yogacoach_payment_links',
            sa.Column('payment_link_id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column('tenant_id', sa.String(255), nullable=False),
            sa.Column('booking_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('yogacoach_course_bookings.booking_id')),
            sa.Column('invoice_id', sa.String(50), sa.ForeignKey('yogacoach_invoices.invoice_id')),
            sa.Column('amount', sa.Numeric(10, 2), nullable=False),
            sa.Column('currency', sa.String(10), server_default='TWD'),
            sa.Column('payment_method', sa.String(50)),
            sa.Column('status', sa.String(50), server_default='pending'),
            sa.Column('payment_url', sa.Text()),
            sa.Column('short_code', sa.String(50), unique=True),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('paid_at', sa.DateTime()),
            sa.Column('expires_at', sa.DateTime()),
        )
        op.create_index('idx_yogacoach_payment_links_tenant', 'yogacoach_payment_links', ['tenant_id'])
        op.create_index('idx_yogacoach_payment_links_booking', 'yogacoach_payment_links', ['booking_id'])
        op.create_index('idx_yogacoach_payment_links_invoice', 'yogacoach_payment_links', ['invoice_id'])
        op.create_index('idx_yogacoach_payment_links_status', 'yogacoach_payment_links', ['status'])

    # Create yogacoach_student_profiles table
    if 'yogacoach_student_profiles' not in existing_tables:
        op.create_table(
            'yogacoach_student_profiles',
            sa.Column('profile_id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column('tenant_id', sa.String(255), nullable=False),
            sa.Column('user_id', sa.String(255), nullable=False),
            sa.Column('teacher_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('yogacoach_teachers.teacher_id')),
            sa.Column('level', sa.String(50)),
            sa.Column('goals', postgresql.JSONB(astext_type=sa.Text())),
            sa.Column('preferences', postgresql.JSONB(astext_type=sa.Text())),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        )
        op.create_index('idx_yogacoach_student_profiles_tenant', 'yogacoach_student_profiles', ['tenant_id'])
        op.create_index('idx_yogacoach_student_profiles_user', 'yogacoach_student_profiles', ['user_id'])

    # Create yogacoach_session_history table
    if 'yogacoach_session_history' not in existing_tables:
        op.create_table(
            'yogacoach_session_history',
            sa.Column('history_id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column('tenant_id', sa.String(255), nullable=False),
            sa.Column('session_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('yogacoach_sessions.session_id'), nullable=False),
            sa.Column('user_id', sa.String(255), nullable=False),
            sa.Column('teacher_id', postgresql.UUID(as_uuid=True)),
            sa.Column('practice_date', sa.Date()),
            sa.Column('summary', postgresql.JSONB(astext_type=sa.Text())),
            sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        )
        op.create_index('idx_yogacoach_session_history_tenant', 'yogacoach_session_history', ['tenant_id'])
        op.create_index('idx_yogacoach_session_history_user', 'yogacoach_session_history', ['user_id'])
        op.create_index('idx_yogacoach_session_history_date', 'yogacoach_session_history', ['practice_date'])

    # Create yogacoach_progress_snapshots table
    if 'yogacoach_progress_snapshots' not in existing_tables:
        op.create_table(
            'yogacoach_progress_snapshots',
            sa.Column('snapshot_id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column('tenant_id', sa.String(255), nullable=False),
            sa.Column('user_id', sa.String(255), nullable=False),
            sa.Column('session_id', postgresql.UUID(as_uuid=True)),
            sa.Column('snapshot_data', postgresql.JSONB(astext_type=sa.Text())),
            sa.Column('metrics', postgresql.JSONB(astext_type=sa.Text())),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        )
        op.create_index('idx_yogacoach_progress_snapshots_tenant', 'yogacoach_progress_snapshots', ['tenant_id'])
        op.create_index('idx_yogacoach_progress_snapshots_user', 'yogacoach_progress_snapshots', ['user_id'])
        op.create_index('idx_yogacoach_progress_snapshots_created', 'yogacoach_progress_snapshots', ['created_at'])

    # Create yogacoach_billing_records table
    if 'yogacoach_billing_records' not in existing_tables:
        op.create_table(
            'yogacoach_billing_records',
            sa.Column('record_id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column('tenant_id', sa.String(255), nullable=False),
            sa.Column('invoice_id', sa.String(50), sa.ForeignKey('yogacoach_invoices.invoice_id'), nullable=False),
            sa.Column('subscription_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('yogacoach_subscriptions.subscription_id'), nullable=False),
            sa.Column('calculation_details', postgresql.JSONB(astext_type=sa.Text())),
            sa.Column('usage_data', postgresql.JSONB(astext_type=sa.Text())),
            sa.Column('charges_breakdown', postgresql.JSONB(astext_type=sa.Text())),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        )
        op.create_index('idx_yogacoach_billing_records_tenant', 'yogacoach_billing_records', ['tenant_id'])
        op.create_index('idx_yogacoach_billing_records_invoice', 'yogacoach_billing_records', ['invoice_id'])
        op.create_index('idx_yogacoach_billing_records_subscription', 'yogacoach_billing_records', ['subscription_id'])


def downgrade():
    """
    Drop all YogaCoach tables in reverse order.
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    tables_in_drop_order = [
        'yogacoach_billing_records',
        'yogacoach_payment_links',
        'yogacoach_invoices',
        'yogacoach_progress_snapshots',
        'yogacoach_session_history',
        'yogacoach_student_profiles',
        'yogacoach_course_bookings',
        'yogacoach_courses',
        'yogacoach_rubric_reviews',
        'yogacoach_rubrics',
        'yogacoach_demo_videos',
        'yogacoach_teacher_libraries',
        'yogacoach_teachers',
        'yogacoach_conversations',
        'yogacoach_knowledge_vectors',
        'yogacoach_knowledge_entries',
        'yogacoach_quota_reservations',
        'yogacoach_privacy_audit_logs',
        'yogacoach_user_channels',
        'yogacoach_share_links',
        'yogacoach_usage_records',
        'yogacoach_jobs',
        'yogacoach_sessions',
        'yogacoach_subscriptions',
        'yogacoach_plans',
    ]

    for table_name in tables_in_drop_order:
        if table_name in existing_tables:
            op.drop_table(table_name)
