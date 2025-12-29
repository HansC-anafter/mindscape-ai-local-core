"""
YogaCoach Database Models
Multi-tenant models for sessions, jobs, subscriptions, usage, share links, and channels
"""

import uuid
from datetime import datetime, date
from sqlalchemy import Column, String, DateTime, Boolean, Integer, ForeignKey, Date, Text, UniqueConstraint, Index, Numeric
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from database import Base


class Plan(Base):
    """Plan model for subscription plans"""

    __tablename__ = "yogacoach_plans"

    plan_id = Column(String(50), primary_key=True)
    name = Column(String(255), nullable=False)
    quota = Column(JSONB, nullable=False)
    price_usd = Column(String(20))
    billing_cycle = Column(String(50))
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Plan(plan_id={self.plan_id}, name={self.name})>"


class YogaCoachSubscription(Base):
    """Subscription model for YogaCoach"""

    __tablename__ = "yogacoach_subscriptions"

    subscription_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(255), nullable=False, index=True)
    user_id = Column(String(255))
    teacher_id = Column(UUID(as_uuid=True))
    plan_id = Column(String(50), ForeignKey("yogacoach_plans.plan_id"))
    status = Column(String(50), default="active", nullable=False, index=True)
    current_period_start = Column(Date)
    current_period_end = Column(Date)
    created_at = Column(DateTime, default=datetime.utcnow)

    plan = relationship("Plan", backref="yogacoach_subscriptions")

    __table_args__ = (
        Index("idx_yogacoach_subscriptions_tenant", "tenant_id"),
    )

    def __repr__(self):
        return f"<YogaCoachSubscription(subscription_id={self.subscription_id}, tenant_id={self.tenant_id}, plan_id={self.plan_id})>"


class Session(Base):
    """Session model for YogaCoach analysis sessions"""

    __tablename__ = "yogacoach_sessions"

    session_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(255), nullable=False, index=True)
    actor_id = Column(String(255), nullable=False)
    subject_user_id = Column(String(255), nullable=False)
    teacher_id = Column(String(255))
    plan_id = Column(String(50))
    channel = Column(String(50))
    idempotency_key = Column(String(255), unique=True, index=True)
    status = Column(String(50), default="created")
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_yogacoach_sessions_tenant", "tenant_id"),
        Index("idx_yogacoach_sessions_user", "tenant_id", "subject_user_id"),
    )

    def __repr__(self):
        return f"<Session(session_id={self.session_id}, tenant_id={self.tenant_id})>"


class Job(Base):
    """Job model for pipeline execution tracking"""

    __tablename__ = "yogacoach_jobs"

    job_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    tenant_id = Column(String(255), nullable=False, index=True)
    pipeline_version = Column(String(50), nullable=False)
    idempotency_key = Column(String(255), nullable=False, index=True)
    status = Column(String(50), nullable=False, default="queued", index=True)
    progress = Column(JSONB)
    error_message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("session_id", "pipeline_version", name="uq_session_pipeline"),
        Index("idx_yogacoach_jobs_tenant", "tenant_id"),
        Index("idx_yogacoach_jobs_status", "status"),
    )

    def __repr__(self):
        return f"<Job(job_id={self.job_id}, session_id={self.session_id}, status={self.status})>"


class UsageRecord(Base):
    """Usage record model for tracking billable minutes"""

    __tablename__ = "yogacoach_usage_records"

    usage_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(255), nullable=False, index=True)
    subscription_id = Column(UUID(as_uuid=True), ForeignKey("yogacoach_subscriptions.subscription_id"))
    session_id = Column(UUID(as_uuid=True), index=True)
    minutes_used = Column(Integer, nullable=False)
    status = Column(String(50), default="recorded")
    recorded_at = Column(DateTime, default=datetime.utcnow)

    subscription = relationship("Subscription", backref="usage_records")

    __table_args__ = (
        Index("idx_yogacoach_usage_tenant", "tenant_id"),
        Index("idx_yogacoach_usage_subscription", "subscription_id"),
        Index("idx_yogacoach_usage_session", "session_id"),
    )

    def __repr__(self):
        return f"<UsageRecord(usage_id={self.usage_id}, tenant_id={self.tenant_id}, minutes_used={self.minutes_used})>"


class ShareLink(Base):
    """Share link model for result sharing"""

    __tablename__ = "yogacoach_share_links"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(255), nullable=False, index=True)
    session_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    short_code = Column(String(50), unique=True, nullable=False, index=True)
    signature = Column(String(50), nullable=False)
    expires_at = Column(DateTime, nullable=False, index=True)
    access_scope = Column(String(50), default="owner_only")
    created_by = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_yogacoach_share_links_tenant", "tenant_id"),
    )

    def __repr__(self):
        return f"<ShareLink(id={self.id}, short_code={self.short_code}, expires_at={self.expires_at})>"


class UserChannel(Base):
    """User channel model for multi-channel delivery (LINE, Web, etc.)"""

    __tablename__ = "yogacoach_user_channels"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(255), nullable=False)
    tenant_id = Column(String(255), nullable=False, index=True)
    channel = Column(String(50), nullable=False)
    channel_user_id = Column(String(255), nullable=False)
    bind_method = Column(String(50))
    push_enabled = Column(Boolean, default=True, nullable=False)
    bot_blocked = Column(Boolean, default=False, nullable=False)
    bind_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", "channel", name="uq_user_channel"),
        Index("idx_yogacoach_user_channels_tenant", "tenant_id"),
    )

    def __repr__(self):
        return f"<UserChannel(id={self.id}, tenant_id={self.tenant_id}, user_id={self.user_id}, channel={self.channel})>"


class PrivacyAuditLog(Base):
    """Privacy audit log for deletion proof tracking"""

    __tablename__ = "yogacoach_privacy_audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(255), nullable=False, index=True)
    session_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    object_key_encrypted = Column(Text, nullable=False)
    lifecycle_rule_id = Column(String(255))
    expires_at = Column(DateTime, nullable=False, index=True)
    deletion_scheduled_at = Column(DateTime)
    status = Column(String(50), default="scheduled", index=True)
    verified_at = Column(DateTime)
    error_message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_yogacoach_privacy_audit_tenant", "tenant_id"),
        Index("idx_yogacoach_privacy_audit_expires", "expires_at"),
    )

    def __repr__(self):
        return f"<PrivacyAuditLog(id={self.id}, session_id={self.session_id}, status={self.status})>"


class QuotaReservation(Base):
    """Quota reservation for temporary quota hold"""

    __tablename__ = "yogacoach_quota_reservations"

    reservation_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(255), nullable=False, index=True)
    subscription_id = Column(UUID(as_uuid=True), ForeignKey("yogacoach_subscriptions.subscription_id"))
    session_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    billable_minutes_reserved = Column(Integer, nullable=False)
    expires_at = Column(DateTime, nullable=False, index=True)
    status = Column(String(50), default="reserved", index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    subscription = relationship("Subscription", backref="quota_reservations")

    __table_args__ = (
        Index("idx_yogacoach_quota_reservations_tenant", "tenant_id"),
        Index("idx_yogacoach_quota_reservations_expires", "expires_at"),
    )

    def __repr__(self):
        return f"<QuotaReservation(reservation_id={self.reservation_id}, session_id={self.session_id}, minutes={self.billable_minutes_reserved})>"


class KnowledgeEntry(Base):
    """Knowledge entry model for QA knowledge base"""

    __tablename__ = "yogacoach_knowledge_entries"

    entry_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(255), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    asana_id = Column(String(100), index=True)
    entry_type = Column(String(50))
    language = Column(String(10), default="zh-TW")
    version = Column(String(50))
    status = Column(String(50), default="published", index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_knowledge_entries_tenant", "tenant_id"),
        Index("idx_knowledge_entries_asana", "asana_id"),
    )

    def __repr__(self):
        return f"<KnowledgeEntry(entry_id={self.entry_id}, title={self.title}, asana_id={self.asana_id})>"


class KnowledgeVector(Base):
    """Knowledge vector model for semantic search"""

    __tablename__ = "yogacoach_knowledge_vectors"

    vector_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(255), nullable=False, index=True)
    entry_id = Column(UUID(as_uuid=True), ForeignKey("yogacoach_knowledge_entries.entry_id"), nullable=False, index=True)
    embedding = Column(Text)
    chunk_text = Column(Text, nullable=False)
    chunk_index = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    entry = relationship("KnowledgeEntry", backref="vectors")

    __table_args__ = (
        Index("idx_knowledge_vectors_tenant", "tenant_id"),
        Index("idx_knowledge_vectors_entry", "entry_id"),
    )

    def __repr__(self):
        return f"<KnowledgeVector(vector_id={self.vector_id}, entry_id={self.entry_id}, chunk_index={self.chunk_index})>"


class Conversation(Base):
    """Conversation model for QA dialogue"""

    __tablename__ = "yogacoach_conversations"

    conversation_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(255), nullable=False, index=True)
    user_id = Column(String(255), nullable=False, index=True)
    session_id = Column(UUID(as_uuid=True))
    messages = Column(JSONB)
    intent = Column(JSONB)
    sources = Column(JSONB)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_conversations_tenant", "tenant_id"),
        Index("idx_conversations_user", "tenant_id", "user_id"),
    )

    def __repr__(self):
        return f"<Conversation(conversation_id={self.conversation_id}, user_id={self.user_id})>"


class Teacher(Base):
    """Teacher model for yoga teachers"""

    __tablename__ = "yogacoach_teachers"

    teacher_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(255), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    studio_name = Column(String(255))
    certification = Column(String(255))
    teaching_style = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_yogacoach_teachers_tenant", "tenant_id"),
    )

    def __repr__(self):
        return f"<Teacher(teacher_id={self.teacher_id}, name={self.name})>"


class TeacherLibrary(Base):
    """Teacher library model for asana whitelist and feedback policy"""

    __tablename__ = "yogacoach_teacher_libraries"

    library_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(255), nullable=False, index=True)
    teacher_id = Column(UUID(as_uuid=True), ForeignKey("yogacoach_teachers.teacher_id"), nullable=False, index=True)
    library_version = Column(String(50), default="v1")
    asana_whitelist = Column(JSONB)
    series = Column(JSONB)
    feedback_policy = Column(JSONB)
    status = Column(String(50), default="draft", index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    teacher = relationship("Teacher", backref="libraries")

    __table_args__ = (
        Index("idx_yogacoach_teacher_libraries_tenant", "tenant_id"),
        Index("idx_yogacoach_teacher_libraries_teacher", "teacher_id"),
    )

    def __repr__(self):
        return f"<TeacherLibrary(library_id={self.library_id}, teacher_id={self.teacher_id}, version={self.library_version})>"


class DemoVideo(Base):
    """Demo video model for teacher demonstration videos"""

    __tablename__ = "yogacoach_demo_videos"

    demo_video_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(255), nullable=False, index=True)
    teacher_id = Column(UUID(as_uuid=True), ForeignKey("yogacoach_teachers.teacher_id"), nullable=False, index=True)
    asana_id = Column(String(100), index=True)
    source = Column(String(50))
    video_id = Column(String(255))
    url = Column(Text)
    duration_seconds = Column(Integer)
    chapters = Column(JSONB)
    mapping_table = Column(JSONB)
    chapters_version = Column(String(50), default="v1")
    status = Column(String(50), default="draft", index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    published_at = Column(DateTime)

    teacher = relationship("Teacher", backref="demo_videos")

    __table_args__ = (
        Index("idx_yogacoach_demo_videos_tenant", "tenant_id"),
        Index("idx_yogacoach_demo_videos_teacher", "teacher_id"),
        Index("idx_yogacoach_demo_videos_asana", "asana_id"),
    )

    def __repr__(self):
        return f"<DemoVideo(demo_video_id={self.demo_video_id}, teacher_id={self.teacher_id}, asana_id={self.asana_id})>"


class Rubric(Base):
    """Rubric model for pose assessment criteria"""

    __tablename__ = "yogacoach_rubrics"

    rubric_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(255), nullable=False, index=True)
    asana_id = Column(String(100), index=True)
    rubric_version = Column(String(50), default="v1")
    content = Column(JSONB, nullable=False)
    status = Column(String(50), default="draft", index=True)
    author_id = Column(UUID(as_uuid=True), ForeignKey("yogacoach_teachers.teacher_id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    published_at = Column(DateTime)

    author = relationship("Teacher", backref="rubrics")

    __table_args__ = (
        Index("idx_yogacoach_rubrics_tenant", "tenant_id"),
        Index("idx_yogacoach_rubrics_asana", "asana_id"),
        Index("idx_yogacoach_rubrics_status", "status"),
    )

    def __repr__(self):
        return f"<Rubric(rubric_id={self.rubric_id}, asana_id={self.asana_id}, version={self.rubric_version})>"


class RubricReview(Base):
    """Rubric review model for collaboration workflow"""

    __tablename__ = "yogacoach_rubric_reviews"

    review_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(255), nullable=False, index=True)
    rubric_id = Column(UUID(as_uuid=True), ForeignKey("yogacoach_rubrics.rubric_id"), nullable=False, index=True)
    reviewer_id = Column(UUID(as_uuid=True), ForeignKey("yogacoach_teachers.teacher_id"), nullable=False)
    status = Column(String(50), default="pending", index=True)
    comments = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    reviewed_at = Column(DateTime)

    rubric = relationship("Rubric", backref="reviews")
    reviewer = relationship("Teacher", backref="rubric_reviews")

    __table_args__ = (
        Index("idx_yogacoach_rubric_reviews_tenant", "tenant_id"),
        Index("idx_yogacoach_rubric_reviews_rubric", "rubric_id"),
    )

    def __repr__(self):
        return f"<RubricReview(review_id={self.review_id}, rubric_id={self.rubric_id}, status={self.status})>"


class Course(Base):
    """Course model for class scheduling"""

    __tablename__ = "yogacoach_courses"

    course_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(255), nullable=False, index=True)
    teacher_id = Column(UUID(as_uuid=True), ForeignKey("yogacoach_teachers.teacher_id"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    course_datetime = Column(DateTime, nullable=False, index=True)
    max_students = Column(Integer)
    price_amount = Column(Numeric(10, 2))
    price_currency = Column(String(10), default="TWD")
    status = Column(String(50), default="scheduled", index=True)
    external_calendar_id = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    teacher = relationship("Teacher", backref="courses")

    __table_args__ = (
        Index("idx_yogacoach_courses_tenant", "tenant_id"),
        Index("idx_yogacoach_courses_teacher", "teacher_id"),
        Index("idx_yogacoach_courses_datetime", "course_datetime"),
    )

    def __repr__(self):
        return f"<Course(course_id={self.course_id}, title={self.title}, course_datetime={self.course_datetime})>"


class CourseBooking(Base):
    """Course booking model for student reservations"""

    __tablename__ = "yogacoach_course_bookings"

    booking_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(255), nullable=False, index=True)
    course_id = Column(UUID(as_uuid=True), ForeignKey("yogacoach_courses.course_id"), nullable=False, index=True)
    user_id = Column(String(255), nullable=False, index=True)
    status = Column(String(50), default="pending", index=True)
    payment_link_id = Column(UUID(as_uuid=True))
    created_at = Column(DateTime, default=datetime.utcnow)
    confirmed_at = Column(DateTime)

    course = relationship("Course", backref="bookings")

    __table_args__ = (
        Index("idx_yogacoach_course_bookings_tenant", "tenant_id"),
        Index("idx_yogacoach_course_bookings_course", "course_id"),
        Index("idx_yogacoach_course_bookings_user", "user_id"),
    )

    def __repr__(self):
        return f"<CourseBooking(booking_id={self.booking_id}, course_id={self.course_id}, status={self.status})>"


class PaymentLink(Base):
    """Payment link model for course payments and invoice payments"""

    __tablename__ = "yogacoach_payment_links"

    payment_link_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(255), nullable=False, index=True)
    booking_id = Column(UUID(as_uuid=True), ForeignKey("yogacoach_course_bookings.booking_id"), index=True)
    invoice_id = Column(String(50), ForeignKey("yogacoach_invoices.invoice_id"), index=True)
    amount = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(10), default="TWD")
    payment_method = Column(String(50))
    status = Column(String(50), default="pending", index=True)
    payment_url = Column(Text)
    short_code = Column(String(50), unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    paid_at = Column(DateTime)
    expires_at = Column(DateTime)

    booking = relationship("CourseBooking", backref="payment_link")
    invoice = relationship("Invoice", backref="payment_links")

    __table_args__ = (
        Index("idx_yogacoach_payment_links_tenant", "tenant_id"),
        Index("idx_yogacoach_payment_links_booking", "booking_id"),
        Index("idx_yogacoach_payment_links_invoice", "invoice_id"),
        Index("idx_yogacoach_payment_links_status", "status"),
    )

    def __repr__(self):
        return f"<PaymentLink(payment_link_id={self.payment_link_id}, booking_id={self.booking_id}, invoice_id={self.invoice_id}, status={self.status})>"


class StudentProfile(Base):
    """Student profile model"""

    __tablename__ = "yogacoach_student_profiles"

    profile_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(255), nullable=False, index=True)
    user_id = Column(String(255), nullable=False, index=True)
    teacher_id = Column(UUID(as_uuid=True), ForeignKey("yogacoach_teachers.teacher_id"))
    level = Column(String(50))
    goals = Column(JSONB)
    preferences = Column(JSONB)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    teacher = relationship("Teacher", backref="student_profiles")

    __table_args__ = (
        Index("idx_yogacoach_student_profiles_tenant", "tenant_id"),
        Index("idx_yogacoach_student_profiles_user", "user_id"),
    )

    def __repr__(self):
        return f"<StudentProfile(profile_id={self.profile_id}, user_id={self.user_id})>"


class SessionHistory(Base):
    """Session history model for practice tracking"""

    __tablename__ = "yogacoach_session_history"

    history_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(255), nullable=False, index=True)
    session_id = Column(UUID(as_uuid=True), ForeignKey("yogacoach_sessions.session_id"), nullable=False, index=True)
    user_id = Column(String(255), nullable=False, index=True)
    teacher_id = Column(UUID(as_uuid=True))
    practice_date = Column(Date, index=True)
    summary = Column(JSONB)
    created_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("Session", backref="history")

    __table_args__ = (
        Index("idx_yogacoach_session_history_tenant", "tenant_id"),
        Index("idx_yogacoach_session_history_user", "user_id"),
        Index("idx_yogacoach_session_history_date", "practice_date"),
    )

    def __repr__(self):
        return f"<SessionHistory(history_id={self.history_id}, session_id={self.session_id}, practice_date={self.practice_date})>"


class ProgressSnapshot(Base):
    """Progress snapshot model for progress tracking"""

    __tablename__ = "yogacoach_progress_snapshots"

    snapshot_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(255), nullable=False, index=True)
    user_id = Column(String(255), nullable=False, index=True)
    session_id = Column(UUID(as_uuid=True))
    snapshot_data = Column(JSONB)
    metrics = Column(JSONB)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (
        Index("idx_yogacoach_progress_snapshots_tenant", "tenant_id"),
        Index("idx_yogacoach_progress_snapshots_user", "user_id"),
        Index("idx_yogacoach_progress_snapshots_created", "created_at"),
    )

    def __repr__(self):
        return f"<ProgressSnapshot(snapshot_id={self.snapshot_id}, user_id={self.user_id}, created_at={self.created_at})>"


class Invoice(Base):
    """Invoice model for billing records"""

    __tablename__ = "yogacoach_invoices"

    invoice_id = Column(String(50), primary_key=True)
    tenant_id = Column(String(255), nullable=False, index=True)
    subscription_id = Column(UUID(as_uuid=True), ForeignKey("yogacoach_subscriptions.subscription_id"), nullable=False, index=True)
    billing_period_start = Column(Date, nullable=False)
    billing_period_end = Column(Date, nullable=False)

    usage_summary = Column(JSONB)
    base_price_usd = Column(Numeric(10, 2))
    overage_minutes = Column(Integer, default=0)
    overage_charges_usd = Column(Numeric(10, 2), default=0)
    tax_usd = Column(Numeric(10, 2), default=0)
    total_usd = Column(Numeric(10, 2), nullable=False)

    payment_status = Column(String(50), default="pending", nullable=False, index=True)
    payment_method = Column(String(50))
    transaction_id = Column(String(255))

    invoice_url = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    paid_at = Column(DateTime)
    due_date = Column(Date, nullable=False)

    subscription = relationship("YogaCoachSubscription", backref="invoices")

    __table_args__ = (
        Index("idx_yogacoach_invoices_tenant", "tenant_id"),
        Index("idx_yogacoach_invoices_subscription", "subscription_id"),
        Index("idx_yogacoach_invoices_billing_period", "billing_period_start", "billing_period_end"),
        Index("idx_yogacoach_invoices_payment_status", "payment_status"),
    )

    def __repr__(self):
        return f"<Invoice(invoice_id={self.invoice_id}, tenant_id={self.tenant_id}, total_usd={self.total_usd}, payment_status={self.payment_status})>"


class BillingRecord(Base):
    """Billing record model for audit tracking"""

    __tablename__ = "yogacoach_billing_records"

    record_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(255), nullable=False, index=True)
    invoice_id = Column(String(50), ForeignKey("yogacoach_invoices.invoice_id"), nullable=False, index=True)
    subscription_id = Column(UUID(as_uuid=True), ForeignKey("yogacoach_subscriptions.subscription_id"), nullable=False)

    calculation_details = Column(JSONB)
    usage_data = Column(JSONB)
    charges_breakdown = Column(JSONB)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    invoice = relationship("Invoice", backref="billing_records")
    subscription = relationship("YogaCoachSubscription", backref="billing_records")

    __table_args__ = (
        Index("idx_yogacoach_billing_records_tenant", "tenant_id"),
        Index("idx_yogacoach_billing_records_invoice", "invoice_id"),
        Index("idx_yogacoach_billing_records_subscription", "subscription_id"),
    )

    def __repr__(self):
        return f"<BillingRecord(record_id={self.record_id}, invoice_id={self.invoice_id}, created_at={self.created_at})>"

