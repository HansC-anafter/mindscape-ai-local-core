"""add_sonic_space_tables

Revision ID: 20251227170000
Revises: 20251227000001
Create Date: 2025-12-27 17:00:00

Adds all Sonic Space database tables for audio assets, licenses, segments, embeddings,
intent cards, candidate sets, decision traces, bookmarks, sound kits, perceptual axes, and export audit.

This migration creates the complete database schema for the Sonic Space capability.
See: docs-internal/implementation/database-orm-implementation-complete-2025-12-27.md
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '20251227170000'
down_revision: Union[str, None] = '20251227174800'  # Depends on init_mindscape_tables
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create all Sonic Space tables"""

    # sonic_audio_assets
    op.create_table(
        'sonic_audio_assets',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('workspace_id', sa.String(255), nullable=False),
        sa.Column('tenant_uuid', sa.String(255), nullable=False),
        sa.Column('original_filename', sa.String(500), nullable=False),
        sa.Column('normalized_path', sa.String(1000)),
        sa.Column('storage_key', sa.String(500)),
        sa.Column('sample_rate', sa.Integer, default=44100),
        sa.Column('bit_depth', sa.Integer, default=16),
        sa.Column('channels', sa.Integer, default=2),
        sa.Column('duration_ms', sa.Integer),
        sa.Column('peak_db', sa.Float),
        sa.Column('lufs', sa.Float),
        sa.Column('dynamic_range_db', sa.Float),
        sa.Column('qa_passed', sa.Boolean, default=False),
        sa.Column('qa_result', postgresql.JSONB),
        sa.Column('source_type', sa.String(50), default='upload'),
        sa.Column('source_url', sa.Text),
        sa.Column('status', sa.String(50), default='pending'),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('updated_at', sa.DateTime),
        sa.Column('created_by', sa.String(255)),
        sa.Index('idx_sonic_assets_tenant_workspace', 'tenant_uuid', 'workspace_id'),
        sa.Index('idx_sonic_assets_status', 'status'),
        sa.Index('ix_sonic_audio_assets_workspace_id', 'workspace_id'),
        sa.Index('ix_sonic_audio_assets_tenant_uuid', 'tenant_uuid'),
    )

    # sonic_license_cards
    op.create_table(
        'sonic_license_cards',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('audio_asset_id', postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column('workspace_id', sa.String(255), nullable=False),
        sa.Column('tenant_uuid', sa.String(255), nullable=False),
        sa.Column('source_type', sa.String(50), nullable=False),
        sa.Column('source_details', postgresql.JSONB),
        sa.Column('usage_scope', postgresql.JSONB),
        sa.Column('restrictions', postgresql.JSONB),
        sa.Column('expires_at', sa.DateTime),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('updated_at', sa.DateTime),
        sa.ForeignKeyConstraint(['audio_asset_id'], ['sonic_audio_assets.id'], ondelete='CASCADE'),
        sa.Index('ix_sonic_license_cards_audio_asset_id', 'audio_asset_id'),
        sa.Index('ix_sonic_license_cards_workspace_id', 'workspace_id'),
        sa.Index('ix_sonic_license_cards_tenant_uuid', 'tenant_uuid'),
    )

    # sonic_segments
    op.create_table(
        'sonic_segments',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('audio_asset_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('workspace_id', sa.String(255), nullable=False),
        sa.Column('tenant_uuid', sa.String(255), nullable=False),
        sa.Column('start_ms', sa.Integer, nullable=False),
        sa.Column('end_ms', sa.Integer, nullable=False),
        sa.Column('duration_ms', sa.Integer, nullable=False),
        sa.Column('is_silent', sa.Boolean, default=False),
        sa.Column('spectral_centroid', sa.Float),
        sa.Column('spectral_flux', sa.Float),
        sa.Column('dynamic_range_db', sa.Float),
        sa.Column('rms_energy', sa.Float),
        sa.Column('low_mid_ratio', sa.Float),
        sa.Column('reverb_ratio', sa.Float),
        sa.Column('tempo_stability', sa.Float),
        sa.Column('storage_key', sa.String(500)),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.ForeignKeyConstraint(['audio_asset_id'], ['sonic_audio_assets.id'], ondelete='CASCADE'),
        sa.Index('ix_sonic_segments_audio_asset_id', 'audio_asset_id'),
        sa.Index('ix_sonic_segments_workspace_id', 'workspace_id'),
        sa.Index('ix_sonic_segments_tenant_uuid', 'tenant_uuid'),
        sa.Index('idx_sonic_segments_tenant_workspace', 'tenant_uuid', 'workspace_id'),
        sa.Index('idx_sonic_segments_asset', 'audio_asset_id'),
    )

    # sonic_embeddings
    op.create_table(
        'sonic_embeddings',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('segment_id', postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column('workspace_id', sa.String(255), nullable=False),
        sa.Column('tenant_uuid', sa.String(255), nullable=False),
        sa.Column('model', sa.String(50), default='clap'),
        sa.Column('dimension', sa.Integer, default=512),
        sa.Column('vector_db_ref', sa.String(255)),
        sa.Column('vector_data', postgresql.JSONB),
        sa.Column('embedding_metadata', postgresql.JSONB),
        sa.Column('storage_backend', sa.String(50), default='pgvector'),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.ForeignKeyConstraint(['segment_id'], ['sonic_segments.id'], ondelete='CASCADE'),
        sa.Index('ix_sonic_embeddings_segment_id', 'segment_id'),
        sa.Index('ix_sonic_embeddings_workspace_id', 'workspace_id'),
        sa.Index('ix_sonic_embeddings_tenant_uuid', 'tenant_uuid'),
        sa.Index('idx_sonic_embeddings_tenant_workspace', 'tenant_uuid', 'workspace_id'),
    )

    # sonic_intent_cards
    op.create_table(
        'sonic_intent_cards',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('workspace_id', sa.String(255), nullable=False),
        sa.Column('tenant_uuid', sa.String(255), nullable=False),
        sa.Column('original_description', sa.Text, nullable=False),
        sa.Column('target_scene', sa.String(50)),
        sa.Column('dimension_targets', postgresql.JSONB),
        sa.Column('prohibitions', postgresql.JSONB),
        sa.Column('reference_fingerprints', postgresql.JSONB),
        sa.Column('status', sa.String(50), default='draft'),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('updated_at', sa.DateTime),
        sa.Index('ix_sonic_intent_cards_workspace_id', 'workspace_id'),
        sa.Index('ix_sonic_intent_cards_tenant_uuid', 'tenant_uuid'),
        sa.Index('idx_sonic_intents_tenant_workspace', 'tenant_uuid', 'workspace_id'),
        sa.Index('idx_sonic_intents_status', 'status'),
    )

    # sonic_candidate_sets
    op.create_table(
        'sonic_candidate_sets',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('intent_card_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('workspace_id', sa.String(255), nullable=False),
        sa.Column('tenant_uuid', sa.String(255), nullable=False),
        sa.Column('candidates', postgresql.JSONB, nullable=False),
        sa.Column('search_params', postgresql.JSONB),
        sa.Column('total_found', sa.Integer, default=0),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.ForeignKeyConstraint(['intent_card_id'], ['sonic_intent_cards.id'], ondelete='CASCADE'),
        sa.Index('ix_sonic_candidate_sets_intent_card_id', 'intent_card_id'),
        sa.Index('ix_sonic_candidate_sets_workspace_id', 'workspace_id'),
        sa.Index('ix_sonic_candidate_sets_tenant_uuid', 'tenant_uuid'),
        sa.Index('idx_sonic_candidates_tenant_workspace', 'tenant_uuid', 'workspace_id'),
    )

    # sonic_decision_traces
    op.create_table(
        'sonic_decision_traces',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('intent_card_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('workspace_id', sa.String(255), nullable=False),
        sa.Column('tenant_uuid', sa.String(255), nullable=False),
        sa.Column('parent_trace_id', postgresql.UUID(as_uuid=True)),
        sa.Column('fork_point_step', sa.Integer),
        sa.Column('decisions', postgresql.JSONB),
        sa.Column('current_step', sa.Integer, default=0),
        sa.Column('current_position', postgresql.JSONB),
        sa.Column('status', sa.String(50), default='exploring'),
        sa.Column('decision_session_id', sa.String(255)),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('updated_at', sa.DateTime),
        sa.ForeignKeyConstraint(['intent_card_id'], ['sonic_intent_cards.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['parent_trace_id'], ['sonic_decision_traces.id']),
        sa.Index('ix_sonic_decision_traces_intent_card_id', 'intent_card_id'),
        sa.Index('ix_sonic_decision_traces_workspace_id', 'workspace_id'),
        sa.Index('ix_sonic_decision_traces_tenant_uuid', 'tenant_uuid'),
        sa.Index('idx_sonic_traces_tenant_workspace', 'tenant_uuid', 'workspace_id'),
        sa.Index('idx_sonic_traces_status', 'status'),
    )

    # sonic_bookmarks
    op.create_table(
        'sonic_bookmarks',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('workspace_id', sa.String(255), nullable=False),
        sa.Column('tenant_uuid', sa.String(255), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text),
        sa.Column('embedding', postgresql.JSONB),
        sa.Column('fingerprint', postgresql.JSONB),
        sa.Column('representative_segment_id', postgresql.UUID(as_uuid=True)),
        sa.Column('usage_suggestions', postgresql.JSONB),
        sa.Column('source_type', sa.String(50)),
        sa.Column('source_reference_id', sa.String(255)),
        sa.Column('tags', postgresql.ARRAY(sa.String(100))),
        sa.Column('usage_count', sa.Integer, default=0),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('last_used_at', sa.DateTime),
        sa.ForeignKeyConstraint(['representative_segment_id'], ['sonic_segments.id']),
        sa.Index('ix_sonic_bookmarks_workspace_id', 'workspace_id'),
        sa.Index('ix_sonic_bookmarks_tenant_uuid', 'tenant_uuid'),
        sa.Index('idx_sonic_bookmarks_tenant_workspace', 'tenant_uuid', 'workspace_id'),
    )

    # sonic_sound_kits
    op.create_table(
        'sonic_sound_kits',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('workspace_id', sa.String(255), nullable=False),
        sa.Column('tenant_uuid', sa.String(255), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('kit_type', sa.String(50)),
        sa.Column('version', sa.String(50), default='1.0.0'),
        sa.Column('description', sa.Text),
        sa.Column('contents', postgresql.JSONB),
        sa.Column('format_spec', postgresql.JSONB),
        sa.Column('license_summary', postgresql.JSONB),
        sa.Column('package_url', sa.Text),
        sa.Column('preview_url', sa.Text),
        sa.Column('sound_tokens', postgresql.JSONB),
        sa.Column('downloads', sa.Integer, default=0),
        sa.Column('status', sa.String(50), default='draft'),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('updated_at', sa.DateTime),
        sa.Index('ix_sonic_sound_kits_workspace_id', 'workspace_id'),
        sa.Index('ix_sonic_sound_kits_tenant_uuid', 'tenant_uuid'),
        sa.Index('idx_sonic_kits_tenant_workspace', 'tenant_uuid', 'workspace_id'),
        sa.Index('idx_sonic_kits_status', 'status'),
    )

    # sonic_sound_kit_items
    op.create_table(
        'sonic_sound_kit_items',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('sound_kit_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('segment_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('filename', sa.String(255), nullable=False),
        sa.Column('category', sa.String(100)),
        sa.Column('duration_ms', sa.Integer),
        sa.Column('license_card_id', postgresql.UUID(as_uuid=True)),
        sa.ForeignKeyConstraint(['sound_kit_id'], ['sonic_sound_kits.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['segment_id'], ['sonic_segments.id']),
        sa.UniqueConstraint('sound_kit_id', 'segment_id', name='uq_kit_segment'),
    )

    # sonic_perceptual_axes
    op.create_table(
        'sonic_perceptual_axes',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('workspace_id', sa.String(255), nullable=False),
        sa.Column('tenant_uuid', sa.String(255), nullable=False),
        sa.Column('embedding_model', sa.String(50), default='clap'),
        sa.Column('embedding_dim', sa.Integer, default=512),
        sa.Column('axes', postgresql.JSONB, nullable=False),
        sa.Column('orthogonality_score', sa.Float),
        sa.Column('total_annotations', sa.Integer, default=0),
        sa.Column('version', sa.String(50), default='1.0.0'),
        sa.Column('is_active', sa.Boolean, default=False),
        sa.Column('calibration_date', sa.DateTime),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Index('ix_sonic_perceptual_axes_workspace_id', 'workspace_id'),
        sa.Index('ix_sonic_perceptual_axes_tenant_uuid', 'tenant_uuid'),
        sa.Index('idx_sonic_axes_tenant_workspace', 'tenant_uuid', 'workspace_id'),
    )

    # sonic_perceptual_axis_models
    op.create_table(
        'sonic_perceptual_axis_models',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('workspace_id', sa.String(255), nullable=False),
        sa.Column('tenant_uuid', sa.String(255), nullable=False),
        sa.Column('axis_id', sa.String(50), nullable=False),
        sa.Column('axis_name', sa.String(100), nullable=False),
        sa.Column('positive_pole', sa.String(100)),
        sa.Column('negative_pole', sa.String(100)),
        sa.Column('annotation_pairs', postgresql.JSONB),
        sa.Column('direction_vector', postgresql.JSONB),
        sa.Column('confidence', sa.Float),
        sa.Column('status', sa.String(50), default='collecting'),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('updated_at', sa.DateTime),
        sa.Index('idx_sonic_axis_models_tenant_workspace', 'tenant_uuid', 'workspace_id'),
        sa.Index('idx_sonic_axis_models_axis_id', 'axis_id'),
    )

    # sonic_export_audits
    op.create_table(
        'sonic_export_audits',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('workspace_id', sa.String(255), nullable=False),
        sa.Column('tenant_uuid', sa.String(255), nullable=False),
        sa.Column('user_id', sa.String(255), nullable=False),
        sa.Column('segment_ids', postgresql.ARRAY(sa.String(255))),
        sa.Column('kit_id', postgresql.UUID(as_uuid=True)),
        sa.Column('intended_use', sa.String(50)),
        sa.Column('platform', sa.String(100)),
        sa.Column('territory', sa.String(100)),
        sa.Column('all_checks_passed', sa.Boolean, default=False),
        sa.Column('watermarks_applied', postgresql.ARRAY(sa.String(255))),
        sa.Column('decision', postgresql.JSONB),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Index('ix_sonic_export_audits_workspace_id', 'workspace_id'),
        sa.Index('ix_sonic_export_audits_tenant_uuid', 'tenant_uuid'),
        sa.Index('idx_sonic_exports_tenant_workspace', 'tenant_uuid', 'workspace_id'),
        sa.Index('idx_sonic_exports_user', 'user_id'),
    )


def downgrade() -> None:
    """Drop all Sonic Space tables"""
    op.drop_table('sonic_export_audits')
    op.drop_table('sonic_perceptual_axis_models')
    op.drop_table('sonic_perceptual_axes')
    op.drop_table('sonic_sound_kit_items')
    op.drop_table('sonic_sound_kits')
    op.drop_table('sonic_bookmarks')
    op.drop_table('sonic_decision_traces')
    op.drop_table('sonic_candidate_sets')
    op.drop_table('sonic_intent_cards')
    op.drop_table('sonic_embeddings')
    op.drop_table('sonic_segments')
    op.drop_table('sonic_license_cards')
    op.drop_table('sonic_audio_assets')

