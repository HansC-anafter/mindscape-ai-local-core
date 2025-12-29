"""
Sonic Space Database Models
Multi-tenant models for audio assets, segments, embeddings, bookmarks, and sound kits.

Related specs:
- Data Model Overview (roadmap lines 228-308)
- Multi-tenancy Rules (roadmap lines 3657-3739)
"""

import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, DateTime, Boolean, Integer, Float, Text,
    ForeignKey, UniqueConstraint, Index
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.orm import relationship

from app.database import Base


class SonicAudioAsset(Base):
    """Audio asset model for imported audio files."""

    __tablename__ = "sonic_audio_assets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(String(255), nullable=False, index=True)
    tenant_uuid = Column(String(255), nullable=False, index=True)

    # File info
    original_filename = Column(String(500), nullable=False)
    normalized_path = Column(String(1000))
    storage_key = Column(String(500))

    # Format
    sample_rate = Column(Integer, default=44100)
    bit_depth = Column(Integer, default=16)
    channels = Column(Integer, default=2)

    # Metadata
    duration_ms = Column(Integer)
    peak_db = Column(Float)
    lufs = Column(Float)
    dynamic_range_db = Column(Float)

    # QA result
    qa_passed = Column(Boolean, default=False)
    qa_result = Column(JSONB)

    # Source
    source_type = Column(String(50), default="upload")  # upload, url, extracted
    source_url = Column(Text)

    # Status
    status = Column(String(50), default="pending", index=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(String(255))

    # Relationships
    license_card = relationship(
        "SonicLicenseCard", back_populates="audio_asset", uselist=False
    )
    segments = relationship("SonicSegment", back_populates="audio_asset")

    __table_args__ = (
        Index("idx_sonic_assets_tenant_workspace", "tenant_uuid", "workspace_id"),
        Index("idx_sonic_assets_status", "status"),
    )

    def __repr__(self):
        return f"<SonicAudioAsset(id={self.id}, filename={self.original_filename})>"


class SonicLicenseCard(Base):
    """License card model for audio asset licensing."""

    __tablename__ = "sonic_license_cards"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    audio_asset_id = Column(
        UUID(as_uuid=True),
        ForeignKey("sonic_audio_assets.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True
    )
    workspace_id = Column(String(255), nullable=False, index=True)
    tenant_uuid = Column(String(255), nullable=False, index=True)

    # Source
    source_type = Column(String(50), nullable=False)
    source_details = Column(JSONB)

    # Usage scope
    usage_scope = Column(JSONB)  # commercial, broadcast, streaming, derivative, redistribution

    # Restrictions
    restrictions = Column(JSONB)  # territories, platforms, duration_limit

    # Risk assessment
    risk_level = Column(String(20), default="medium")  # low, medium, high, critical
    risk_factors = Column(ARRAY(String(255)))

    # Usage rules
    usage_rules = Column(JSONB)  # allowed, prohibited

    # Attribution
    attribution_required = Column(Boolean, default=False)
    attribution_text = Column(Text)

    # Expiry
    expiry_date = Column(DateTime)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    audio_asset = relationship("SonicAudioAsset", back_populates="license_card")

    __table_args__ = (
        Index("idx_sonic_licenses_tenant_workspace", "tenant_uuid", "workspace_id"),
        Index("idx_sonic_licenses_risk", "risk_level"),
    )

    def __repr__(self):
        return f"<SonicLicenseCard(id={self.id}, source_type={self.source_type})>"


class SonicSegment(Base):
    """Segment model for audio sub-portions."""

    __tablename__ = "sonic_segments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    audio_asset_id = Column(
        UUID(as_uuid=True),
        ForeignKey("sonic_audio_assets.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    workspace_id = Column(String(255), nullable=False, index=True)
    tenant_uuid = Column(String(255), nullable=False, index=True)

    # Timing
    start_ms = Column(Integer, nullable=False)
    end_ms = Column(Integer, nullable=False)
    duration_ms = Column(Integer, nullable=False)

    # Status
    is_silent = Column(Boolean, default=False)

    # Features (normalized 0-100)
    spectral_centroid = Column(Float)
    spectral_flux = Column(Float)
    dynamic_range_db = Column(Float)
    rms_energy = Column(Float)
    low_mid_ratio = Column(Float)
    reverb_ratio = Column(Float)
    tempo_stability = Column(Float)

    # Storage
    storage_key = Column(String(500))

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    audio_asset = relationship("SonicAudioAsset", back_populates="segments")
    embedding = relationship(
        "SonicEmbedding", back_populates="segment", uselist=False
    )

    __table_args__ = (
        Index("idx_sonic_segments_tenant_workspace", "tenant_uuid", "workspace_id"),
        Index("idx_sonic_segments_asset", "audio_asset_id"),
    )

    def __repr__(self):
        return f"<SonicSegment(id={self.id}, start_ms={self.start_ms}, end_ms={self.end_ms})>"


class SonicEmbedding(Base):
    """Embedding model for segment vector representations."""

    __tablename__ = "sonic_embeddings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    segment_id = Column(
        UUID(as_uuid=True),
        ForeignKey("sonic_segments.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True
    )
    workspace_id = Column(String(255), nullable=False, index=True)
    tenant_uuid = Column(String(255), nullable=False, index=True)

    # Model info
    model = Column(String(50), default="clap")  # clap, audioclip, wav2vec2
    dimension = Column(Integer, default=512)

    # Vector (stored as reference to pgvector or as JSON for portability)
    vector_db_ref = Column(String(255))  # Reference in pgvector
    vector_data = Column(JSONB)  # Fallback JSON storage

    # Metadata (renamed to avoid SQLAlchemy reserved word conflict)
    embedding_metadata = Column(JSONB)

    # Storage
    storage_backend = Column(String(50), default="pgvector")

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    segment = relationship("SonicSegment", back_populates="embedding")

    __table_args__ = (
        Index("idx_sonic_embeddings_tenant_workspace", "tenant_uuid", "workspace_id"),
    )

    def __repr__(self):
        return f"<SonicEmbedding(id={self.id}, model={self.model})>"


class SonicIntentCard(Base):
    """Intent card model for sonic search intents."""

    __tablename__ = "sonic_intent_cards"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(String(255), nullable=False, index=True)
    tenant_uuid = Column(String(255), nullable=False, index=True)

    # Intent
    original_description = Column(Text, nullable=False)
    target_scene = Column(String(50))  # meditation, brand_audio, ui_sound, etc.

    # Dimension targets
    dimension_targets = Column(JSONB)  # [{dimension, target_value, tolerance, priority}]

    # Prohibitions
    prohibitions = Column(JSONB)  # [{dimension, prohibited_range, reason}]

    # References
    reference_fingerprints = Column(JSONB)  # {positive: [], negative: []}

    # Status
    status = Column(String(50), default="draft", index=True)  # draft, active, archived

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    decision_traces = relationship("SonicDecisionTrace", back_populates="intent_card")
    candidate_sets = relationship("SonicCandidateSet", back_populates="intent_card")

    __table_args__ = (
        Index("idx_sonic_intents_tenant_workspace", "tenant_uuid", "workspace_id"),
        Index("idx_sonic_intents_status", "status"),
    )

    def __repr__(self):
        return f"<SonicIntentCard(id={self.id}, scene={self.target_scene})>"


class SonicCandidateSet(Base):
    """Candidate set model for navigation search results."""

    __tablename__ = "sonic_candidate_sets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    intent_card_id = Column(
        UUID(as_uuid=True),
        ForeignKey("sonic_intent_cards.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    workspace_id = Column(String(255), nullable=False, index=True)
    tenant_uuid = Column(String(255), nullable=False, index=True)

    # Candidates
    candidates = Column(JSONB)  # [{segment_id, similarity_score, dimension_match, license_info}]

    # Search params
    search_params = Column(JSONB)  # query_vector_hash, top_k, diversity_factor, filters
    total_found = Column(Integer, default=0)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    intent_card = relationship("SonicIntentCard", back_populates="candidate_sets")

    __table_args__ = (
        Index("idx_sonic_candidates_tenant_workspace", "tenant_uuid", "workspace_id"),
    )

    def __repr__(self):
        return f"<SonicCandidateSet(id={self.id}, total_found={self.total_found})>"


class SonicDecisionTrace(Base):
    """Decision trace model for A/B listening experiments."""

    __tablename__ = "sonic_decision_traces"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    intent_card_id = Column(
        UUID(as_uuid=True),
        ForeignKey("sonic_intent_cards.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    workspace_id = Column(String(255), nullable=False, index=True)
    tenant_uuid = Column(String(255), nullable=False, index=True)

    # Branching
    parent_trace_id = Column(UUID(as_uuid=True), ForeignKey("sonic_decision_traces.id"))
    fork_point_step = Column(Integer)

    # Decisions
    decisions = Column(JSONB)  # [{step, timestamp, dimension, option_a, option_b, choice, reasoning}]
    current_step = Column(Integer, default=0)

    # Current position
    current_position = Column(JSONB)  # {embedding, fingerprint}

    # Status
    status = Column(String(50), default="exploring", index=True)  # exploring, paused, completed

    # Local-core integration
    decision_session_id = Column(String(255))  # Reference to local-core decisions API

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    intent_card = relationship("SonicIntentCard", back_populates="decision_traces")
    parent_trace = relationship("SonicDecisionTrace", remote_side=[id])

    __table_args__ = (
        Index("idx_sonic_traces_tenant_workspace", "tenant_uuid", "workspace_id"),
        Index("idx_sonic_traces_status", "status"),
    )

    def __repr__(self):
        return f"<SonicDecisionTrace(id={self.id}, status={self.status})>"


class SonicBookmark(Base):
    """Bookmark model for reusable latent space points."""

    __tablename__ = "sonic_bookmarks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(String(255), nullable=False, index=True)
    tenant_uuid = Column(String(255), nullable=False, index=True)

    # Basic info
    name = Column(String(255), nullable=False)
    description = Column(Text)

    # Coordinates
    embedding = Column(JSONB)  # Vector as JSON array
    fingerprint = Column(JSONB)  # {spatiality, density, granularity, brightness, warmth, dynamics}

    # Representative segment
    representative_segment_id = Column(
        UUID(as_uuid=True),
        ForeignKey("sonic_segments.id"),
        index=True
    )

    # Usage suggestions
    usage_suggestions = Column(JSONB)  # [{scene, reason, confidence}]

    # Source
    source_type = Column(String(50))  # decision_trace, direct_segment, manual
    source_reference_id = Column(String(255))

    # Tags and metadata
    tags = Column(ARRAY(String(100)))
    usage_count = Column(Integer, default=0)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_used_at = Column(DateTime)

    __table_args__ = (
        Index("idx_sonic_bookmarks_tenant_workspace", "tenant_uuid", "workspace_id"),
    )

    def __repr__(self):
        return f"<SonicBookmark(id={self.id}, name={self.name})>"


class SonicSoundKit(Base):
    """Sound kit model for packaged audio collections."""

    __tablename__ = "sonic_sound_kits"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(String(255), nullable=False, index=True)
    tenant_uuid = Column(String(255), nullable=False, index=True)

    # Basic info
    name = Column(String(255), nullable=False)
    kit_type = Column(String(50))  # sfx, loop, ambience, ui_sound, mixed
    version = Column(String(50), default="1.0.0")
    description = Column(Text)

    # Contents
    contents = Column(JSONB)  # {total_files, total_duration_ms, categories}

    # Format
    format_spec = Column(JSONB)  # {format, bit_depth, sample_rate}

    # License
    license_summary = Column(JSONB)  # {summary, can_commercial, requires_attribution}

    # URLs
    package_url = Column(Text)
    preview_url = Column(Text)

    # Sound tokens
    sound_tokens = Column(JSONB)  # Full sound_tokens.json content

    # Stats
    downloads = Column(Integer, default=0)

    # Status
    status = Column(String(50), default="draft", index=True)  # draft, ready, published

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    items = relationship("SonicSoundKitItem", back_populates="sound_kit")

    __table_args__ = (
        Index("idx_sonic_kits_tenant_workspace", "tenant_uuid", "workspace_id"),
        Index("idx_sonic_kits_status", "status"),
    )

    def __repr__(self):
        return f"<SonicSoundKit(id={self.id}, name={self.name})>"


class SonicSoundKitItem(Base):
    """Sound kit item model for kit contents."""

    __tablename__ = "sonic_sound_kit_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sound_kit_id = Column(
        UUID(as_uuid=True),
        ForeignKey("sonic_sound_kits.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    segment_id = Column(
        UUID(as_uuid=True),
        ForeignKey("sonic_segments.id"),
        nullable=False,
        index=True
    )

    # File info
    filename = Column(String(255), nullable=False)
    category = Column(String(100))

    # Metadata
    duration_ms = Column(Integer)
    license_card_id = Column(UUID(as_uuid=True))

    # Relationships
    sound_kit = relationship("SonicSoundKit", back_populates="items")

    __table_args__ = (
        UniqueConstraint("sound_kit_id", "segment_id", name="uq_kit_segment"),
    )

    def __repr__(self):
        return f"<SonicSoundKitItem(id={self.id}, filename={self.filename})>"


class SonicPerceptualAxes(Base):
    """Perceptual axes model for calibrated steer directions (aggregated)."""

    __tablename__ = "sonic_perceptual_axes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(String(255), nullable=False, index=True)
    tenant_uuid = Column(String(255), nullable=False, index=True)

    # Model info
    embedding_model = Column(String(50), default="clap")
    embedding_dim = Column(Integer, default=512)

    # Axes
    axes = Column(JSONB)  # [{name, positive_pole, negative_pole, direction_vector, confidence}]

    # Quality metrics
    orthogonality_score = Column(Float)
    total_annotations = Column(Integer, default=0)

    # Version
    version = Column(String(50), default="1.0.0")

    # Status
    is_active = Column(Boolean, default=False)

    # Timestamps
    calibration_date = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_sonic_axes_tenant_workspace", "tenant_uuid", "workspace_id"),
    )

    def __repr__(self):
        return f"<SonicPerceptualAxes(id={self.id}, version={self.version})>"


class SonicPerceptualAxisModel(Base):
    """Individual perceptual axis calibration model."""

    __tablename__ = "sonic_perceptual_axis_models"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(String(255), nullable=False, index=True)
    tenant_uuid = Column(String(255), nullable=False, index=True)

    # Axis definition
    axis_id = Column(String(50), nullable=False)  # warmth, brightness, spatiality, etc.
    axis_name = Column(String(100), nullable=False)
    positive_pole = Column(String(100))
    negative_pole = Column(String(100))

    # Calibration data
    annotation_pairs = Column(JSONB)  # [{positive_segment_id, negative_segment_id, confidence}]
    direction_vector = Column(JSONB)  # Computed direction in embedding space
    confidence = Column(Float)

    # Status
    status = Column(String(50), default="collecting")  # collecting, calibrating, calibrated

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_sonic_axis_models_tenant_workspace", "tenant_uuid", "workspace_id"),
        Index("idx_sonic_axis_models_axis_id", "axis_id"),
    )

    def __repr__(self):
        return f"<SonicPerceptualAxisModel(id={self.id}, axis_id={self.axis_id})>"


class SonicExportAudit(Base):
    """Export audit log for tracking exports."""

    __tablename__ = "sonic_export_audits"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(String(255), nullable=False, index=True)
    tenant_uuid = Column(String(255), nullable=False, index=True)
    user_id = Column(String(255), nullable=False)

    # What was exported
    segment_ids = Column(ARRAY(String(255)))
    kit_id = Column(UUID(as_uuid=True))

    # Export details
    intended_use = Column(String(50))  # commercial, non_commercial, internal
    platform = Column(String(100))
    territory = Column(String(100))

    # Compliance
    all_checks_passed = Column(Boolean, default=False)
    watermarks_applied = Column(ARRAY(String(255)))
    decision = Column(JSONB)  # Full export decision

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_sonic_exports_tenant_workspace", "tenant_uuid", "workspace_id"),
        Index("idx_sonic_exports_user", "user_id"),
    )

    def __repr__(self):
        return f"<SonicExportAudit(id={self.id}, intended_use={self.intended_use})>"

