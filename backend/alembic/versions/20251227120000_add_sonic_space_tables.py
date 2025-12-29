"""Add Sonic Space tables

Revision ID: 20251227120000
Revises: 20251220120000
Create Date: 2025-12-27 12:00:00.000000

Creates all tables for Sonic Space capability:
- sonic_audio_assets: Audio asset storage
- sonic_license_cards: License governance
- sonic_segments: Audio segments
- sonic_embeddings: Vector embeddings (supports pgvector)
- sonic_intent_cards: Search intents
- sonic_candidate_sets: Search results
- sonic_decision_traces: A/B decision tracking
- sonic_bookmarks: Latent space bookmarks
- sonic_sound_kits: Sound kit packages
- sonic_sound_kit_items: Kit contents
- sonic_perceptual_axes: Calibrated perceptual axes
- sonic_perceptual_axis_models: Individual axis calibrations
- sonic_export_audits: Export compliance logs

See: capabilities/sonic_space/docs/implementation/sonic-space-implementation-roadmap-2025-12-27.md
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20251227120000'
down_revision = '20251227000001'  # Updated to match local-core migration sequence
branch_labels = None
depends_on = None


def upgrade():
    """
    Create all Sonic Space tables with multi-tenancy support.
    All tables include workspace_id and tenant_uuid for isolation.
    """

    # Create sonic_audio_assets table
    op.create_table(
        'sonic_audio_assets',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('workspace_id', sa.String(255), nullable=False),
        sa.Column('tenant_uuid', sa.String(255), nullable=False),
        sa.Column('original_filename', sa.String(500), nullable=False),
        sa.Column('normalized_path', sa.String(1000)),
        sa.Column('storage_key', sa.String(500)),
        sa.Column('sample_rate', sa.Integer(), server_default='44100'),
        sa.Column('bit_depth', sa.Integer(), server_default='16'),
        sa.Column('channels', sa.Integer(), server_default='2'),
        sa.Column('duration_ms', sa.Integer()),
        sa.Column('peak_db', sa.Float()),
        sa.Column('lufs', sa.Float()),
        sa.Column('dynamic_range_db', sa.Float()),
        sa.Column('qa_passed', sa.Boolean(), server_default='false'),
        sa.Column('qa_result', postgresql.JSONB(astext_type=sa.Text())),
        sa.Column('source_type', sa.String(50), server_default='upload'),
        sa.Column('source_url', sa.Text()),
        sa.Column('status', sa.String(50), server_default='pending'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('created_by', sa.String(255)),
    )
    op.create_index('idx_sonic_assets_tenant_workspace', 'sonic_audio_assets', ['tenant_uuid', 'workspace_id'])
    op.create_index('idx_sonic_assets_workspace_id', 'sonic_audio_assets', ['workspace_id'])
    op.create_index('idx_sonic_assets_tenant_uuid', 'sonic_audio_assets', ['tenant_uuid'])
    op.create_index('idx_sonic_assets_status', 'sonic_audio_assets', ['status'])

    # Create sonic_license_cards table
    op.create_table(
        'sonic_license_cards',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('audio_asset_id', postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column('workspace_id', sa.String(255), nullable=False),
        sa.Column('tenant_uuid', sa.String(255), nullable=False),
        sa.Column('source_type', sa.String(50), nullable=False),
        sa.Column('source_details', postgresql.JSONB(astext_type=sa.Text())),
        sa.Column('usage_scope', postgresql.JSONB(astext_type=sa.Text())),
        sa.Column('restrictions', postgresql.JSONB(astext_type=sa.Text())),
        sa.Column('risk_level', sa.String(20), server_default='medium'),
        sa.Column('risk_factors', postgresql.ARRAY(sa.String(255))),
        sa.Column('usage_rules', postgresql.JSONB(astext_type=sa.Text())),
        sa.Column('attribution_required', sa.Boolean(), server_default='false'),
        sa.Column('attribution_text', sa.Text()),
        sa.Column('expiry_date', sa.DateTime()),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['audio_asset_id'], ['sonic_audio_assets.id'], ondelete='CASCADE'),
    )
    op.create_index('idx_sonic_licenses_tenant_workspace', 'sonic_license_cards', ['tenant_uuid', 'workspace_id'])
    op.create_index('idx_sonic_licenses_workspace_id', 'sonic_license_cards', ['workspace_id'])
    op.create_index('idx_sonic_licenses_tenant_uuid', 'sonic_license_cards', ['tenant_uuid'])
    op.create_index('idx_sonic_licenses_risk', 'sonic_license_cards', ['risk_level'])
    op.create_index('idx_sonic_licenses_audio_asset_id', 'sonic_license_cards', ['audio_asset_id'])

    # Create sonic_segments table
    op.create_table(
        'sonic_segments',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('audio_asset_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('workspace_id', sa.String(255), nullable=False),
        sa.Column('tenant_uuid', sa.String(255), nullable=False),
        sa.Column('start_ms', sa.Integer(), nullable=False),
        sa.Column('end_ms', sa.Integer(), nullable=False),
        sa.Column('duration_ms', sa.Integer(), nullable=False),
        sa.Column('is_silent', sa.Boolean(), server_default='false'),
        sa.Column('spectral_centroid', sa.Float()),
        sa.Column('spectral_flux', sa.Float()),
        sa.Column('dynamic_range_db', sa.Float()),
        sa.Column('rms_energy', sa.Float()),
        sa.Column('low_mid_ratio', sa.Float()),
        sa.Column('reverb_ratio', sa.Float()),
        sa.Column('tempo_stability', sa.Float()),
        sa.Column('storage_key', sa.String(500)),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['audio_asset_id'], ['sonic_audio_assets.id'], ondelete='CASCADE'),
    )
    op.create_index('idx_sonic_segments_tenant_workspace', 'sonic_segments', ['tenant_uuid', 'workspace_id'])
    op.create_index('idx_sonic_segments_workspace_id', 'sonic_segments', ['workspace_id'])
    op.create_index('idx_sonic_segments_tenant_uuid', 'sonic_segments', ['tenant_uuid'])
    op.create_index('idx_sonic_segments_asset', 'sonic_segments', ['audio_asset_id'])

    # Create sonic_embeddings table
    op.create_table(
        'sonic_embeddings',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('segment_id', postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column('workspace_id', sa.String(255), nullable=False),
        sa.Column('tenant_uuid', sa.String(255), nullable=False),
        sa.Column('model', sa.String(50), server_default='clap'),
        sa.Column('dimension', sa.Integer(), server_default='512'),
        sa.Column('vector_db_ref', sa.String(255)),
        sa.Column('vector_data', postgresql.JSONB(astext_type=sa.Text())),
        sa.Column('embedding_metadata', postgresql.JSONB(astext_type=sa.Text())),
        sa.Column('storage_backend', sa.String(50), server_default='pgvector'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['segment_id'], ['sonic_segments.id'], ondelete='CASCADE'),
    )
    op.create_index('idx_sonic_embeddings_tenant_workspace', 'sonic_embeddings', ['tenant_uuid', 'workspace_id'])
    op.create_index('idx_sonic_embeddings_workspace_id', 'sonic_embeddings', ['workspace_id'])
    op.create_index('idx_sonic_embeddings_tenant_uuid', 'sonic_embeddings', ['tenant_uuid'])
    op.create_index('idx_sonic_embeddings_segment_id', 'sonic_embeddings', ['segment_id'])

    # Create sonic_intent_cards table
    op.create_table(
        'sonic_intent_cards',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('workspace_id', sa.String(255), nullable=False),
        sa.Column('tenant_uuid', sa.String(255), nullable=False),
        sa.Column('original_description', sa.Text(), nullable=False),
        sa.Column('target_scene', sa.String(50)),
        sa.Column('dimension_targets', postgresql.JSONB(astext_type=sa.Text())),
        sa.Column('prohibitions', postgresql.JSONB(astext_type=sa.Text())),
        sa.Column('reference_fingerprints', postgresql.JSONB(astext_type=sa.Text())),
        sa.Column('status', sa.String(50), server_default='draft'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index('idx_sonic_intents_tenant_workspace', 'sonic_intent_cards', ['tenant_uuid', 'workspace_id'])
    op.create_index('idx_sonic_intents_workspace_id', 'sonic_intent_cards', ['workspace_id'])
    op.create_index('idx_sonic_intents_tenant_uuid', 'sonic_intent_cards', ['tenant_uuid'])
    op.create_index('idx_sonic_intents_status', 'sonic_intent_cards', ['status'])

    # Create sonic_candidate_sets table
    op.create_table(
        'sonic_candidate_sets',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('intent_card_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('workspace_id', sa.String(255), nullable=False),
        sa.Column('tenant_uuid', sa.String(255), nullable=False),
        sa.Column('candidates', postgresql.JSONB(astext_type=sa.Text())),
        sa.Column('search_params', postgresql.JSONB(astext_type=sa.Text())),
        sa.Column('total_found', sa.Integer(), server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['intent_card_id'], ['sonic_intent_cards.id'], ondelete='CASCADE'),
    )
    op.create_index('idx_sonic_candidates_tenant_workspace', 'sonic_candidate_sets', ['tenant_uuid', 'workspace_id'])
    op.create_index('idx_sonic_candidates_workspace_id', 'sonic_candidate_sets', ['workspace_id'])
    op.create_index('idx_sonic_candidates_tenant_uuid', 'sonic_candidate_sets', ['tenant_uuid'])
    op.create_index('idx_sonic_candidates_intent_card_id', 'sonic_candidate_sets', ['intent_card_id'])

    # Create sonic_decision_traces table
    op.create_table(
        'sonic_decision_traces',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('intent_card_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('workspace_id', sa.String(255), nullable=False),
        sa.Column('tenant_uuid', sa.String(255), nullable=False),
        sa.Column('parent_trace_id', postgresql.UUID(as_uuid=True)),
        sa.Column('fork_point_step', sa.Integer()),
        sa.Column('decisions', postgresql.JSONB(astext_type=sa.Text())),
        sa.Column('current_step', sa.Integer(), server_default='0'),
        sa.Column('current_position', postgresql.JSONB(astext_type=sa.Text())),
        sa.Column('status', sa.String(50), server_default='exploring'),
        sa.Column('decision_session_id', sa.String(255)),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['intent_card_id'], ['sonic_intent_cards.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['parent_trace_id'], ['sonic_decision_traces.id']),
    )
    op.create_index('idx_sonic_traces_tenant_workspace', 'sonic_decision_traces', ['tenant_uuid', 'workspace_id'])
    op.create_index('idx_sonic_traces_workspace_id', 'sonic_decision_traces', ['workspace_id'])
    op.create_index('idx_sonic_traces_tenant_uuid', 'sonic_decision_traces', ['tenant_uuid'])
    op.create_index('idx_sonic_traces_status', 'sonic_decision_traces', ['status'])
    op.create_index('idx_sonic_traces_intent_card_id', 'sonic_decision_traces', ['intent_card_id'])

    # Create sonic_bookmarks table
    op.create_table(
        'sonic_bookmarks',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('workspace_id', sa.String(255), nullable=False),
        sa.Column('tenant_uuid', sa.String(255), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text()),
        sa.Column('embedding', postgresql.JSONB(astext_type=sa.Text())),
        sa.Column('fingerprint', postgresql.JSONB(astext_type=sa.Text())),
        sa.Column('representative_segment_id', postgresql.UUID(as_uuid=True)),
        sa.Column('usage_suggestions', postgresql.JSONB(astext_type=sa.Text())),
        sa.Column('source_type', sa.String(50)),
        sa.Column('source_reference_id', sa.String(255)),
        sa.Column('tags', postgresql.ARRAY(sa.String(100))),
        sa.Column('usage_count', sa.Integer(), server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('last_used_at', sa.DateTime()),
        sa.ForeignKeyConstraint(['representative_segment_id'], ['sonic_segments.id']),
    )
    op.create_index('idx_sonic_bookmarks_tenant_workspace', 'sonic_bookmarks', ['tenant_uuid', 'workspace_id'])
    op.create_index('idx_sonic_bookmarks_workspace_id', 'sonic_bookmarks', ['workspace_id'])
    op.create_index('idx_sonic_bookmarks_tenant_uuid', 'sonic_bookmarks', ['tenant_uuid'])
    op.create_index('idx_sonic_bookmarks_representative_segment_id', 'sonic_bookmarks', ['representative_segment_id'])

    # Create sonic_sound_kits table
    op.create_table(
        'sonic_sound_kits',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('workspace_id', sa.String(255), nullable=False),
        sa.Column('tenant_uuid', sa.String(255), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('kit_type', sa.String(50)),
        sa.Column('version', sa.String(50), server_default='1.0.0'),
        sa.Column('description', sa.Text()),
        sa.Column('contents', postgresql.JSONB(astext_type=sa.Text())),
        sa.Column('format_spec', postgresql.JSONB(astext_type=sa.Text())),
        sa.Column('license_summary', postgresql.JSONB(astext_type=sa.Text())),
        sa.Column('package_url', sa.Text()),
        sa.Column('preview_url', sa.Text()),
        sa.Column('sound_tokens', postgresql.JSONB(astext_type=sa.Text())),
        sa.Column('downloads', sa.Integer(), server_default='0'),
        sa.Column('status', sa.String(50), server_default='draft'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index('idx_sonic_kits_tenant_workspace', 'sonic_sound_kits', ['tenant_uuid', 'workspace_id'])
    op.create_index('idx_sonic_kits_workspace_id', 'sonic_sound_kits', ['workspace_id'])
    op.create_index('idx_sonic_kits_tenant_uuid', 'sonic_sound_kits', ['tenant_uuid'])
    op.create_index('idx_sonic_kits_status', 'sonic_sound_kits', ['status'])

    # Create sonic_sound_kit_items table
    op.create_table(
        'sonic_sound_kit_items',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('sound_kit_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('segment_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('filename', sa.String(255), nullable=False),
        sa.Column('category', sa.String(100)),
        sa.Column('duration_ms', sa.Integer()),
        sa.Column('license_card_id', postgresql.UUID(as_uuid=True)),
        sa.ForeignKeyConstraint(['sound_kit_id'], ['sonic_sound_kits.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['segment_id'], ['sonic_segments.id']),
        sa.UniqueConstraint('sound_kit_id', 'segment_id', name='uq_kit_segment'),
    )
    op.create_index('idx_sonic_kit_items_sound_kit_id', 'sonic_sound_kit_items', ['sound_kit_id'])
    op.create_index('idx_sonic_kit_items_segment_id', 'sonic_sound_kit_items', ['segment_id'])

    # Create sonic_perceptual_axes table
    op.create_table(
        'sonic_perceptual_axes',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('workspace_id', sa.String(255), nullable=False),
        sa.Column('tenant_uuid', sa.String(255), nullable=False),
        sa.Column('embedding_model', sa.String(50), server_default='clap'),
        sa.Column('embedding_dim', sa.Integer(), server_default='512'),
        sa.Column('axes', postgresql.JSONB(astext_type=sa.Text())),
        sa.Column('orthogonality_score', sa.Float()),
        sa.Column('total_annotations', sa.Integer(), server_default='0'),
        sa.Column('version', sa.String(50), server_default='1.0.0'),
        sa.Column('is_active', sa.Boolean(), server_default='false'),
        sa.Column('calibration_date', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index('idx_sonic_axes_tenant_workspace', 'sonic_perceptual_axes', ['tenant_uuid', 'workspace_id'])
    op.create_index('idx_sonic_axes_workspace_id', 'sonic_perceptual_axes', ['workspace_id'])
    op.create_index('idx_sonic_axes_tenant_uuid', 'sonic_perceptual_axes', ['tenant_uuid'])

    # Create sonic_perceptual_axis_models table
    op.create_table(
        'sonic_perceptual_axis_models',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('workspace_id', sa.String(255), nullable=False),
        sa.Column('tenant_uuid', sa.String(255), nullable=False),
        sa.Column('axis_id', sa.String(50), nullable=False),
        sa.Column('axis_name', sa.String(100), nullable=False),
        sa.Column('positive_pole', sa.String(100)),
        sa.Column('negative_pole', sa.String(100)),
        sa.Column('annotation_pairs', postgresql.JSONB(astext_type=sa.Text())),
        sa.Column('direction_vector', postgresql.JSONB(astext_type=sa.Text())),
        sa.Column('confidence', sa.Float()),
        sa.Column('status', sa.String(50), server_default='collecting'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index('idx_sonic_axis_models_tenant_workspace', 'sonic_perceptual_axis_models', ['tenant_uuid', 'workspace_id'])
    op.create_index('idx_sonic_axis_models_workspace_id', 'sonic_perceptual_axis_models', ['workspace_id'])
    op.create_index('idx_sonic_axis_models_tenant_uuid', 'sonic_perceptual_axis_models', ['tenant_uuid'])
    op.create_index('idx_sonic_axis_models_axis_id', 'sonic_perceptual_axis_models', ['axis_id'])

    # Create sonic_export_audits table
    op.create_table(
        'sonic_export_audits',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('workspace_id', sa.String(255), nullable=False),
        sa.Column('tenant_uuid', sa.String(255), nullable=False),
        sa.Column('user_id', sa.String(255), nullable=False),
        sa.Column('segment_ids', postgresql.ARRAY(sa.String(255))),
        sa.Column('kit_id', postgresql.UUID(as_uuid=True)),
        sa.Column('intended_use', sa.String(50)),
        sa.Column('platform', sa.String(100)),
        sa.Column('territory', sa.String(100)),
        sa.Column('all_checks_passed', sa.Boolean(), server_default='false'),
        sa.Column('watermarks_applied', postgresql.ARRAY(sa.String(255))),
        sa.Column('decision', postgresql.JSONB(astext_type=sa.Text())),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index('idx_sonic_exports_tenant_workspace', 'sonic_export_audits', ['tenant_uuid', 'workspace_id'])
    op.create_index('idx_sonic_exports_workspace_id', 'sonic_export_audits', ['workspace_id'])
    op.create_index('idx_sonic_exports_tenant_uuid', 'sonic_export_audits', ['tenant_uuid'])
    op.create_index('idx_sonic_exports_user', 'sonic_export_audits', ['user_id'])


def downgrade():
    """
    Drop all Sonic Space tables.
    """
    op.drop_index('idx_sonic_exports_user', table_name='sonic_export_audits')
    op.drop_index('idx_sonic_exports_tenant_uuid', table_name='sonic_export_audits')
    op.drop_index('idx_sonic_exports_workspace_id', table_name='sonic_export_audits')
    op.drop_index('idx_sonic_exports_tenant_workspace', table_name='sonic_export_audits')
    op.drop_table('sonic_export_audits')

    op.drop_index('idx_sonic_axis_models_axis_id', table_name='sonic_perceptual_axis_models')
    op.drop_index('idx_sonic_axis_models_tenant_uuid', table_name='sonic_perceptual_axis_models')
    op.drop_index('idx_sonic_axis_models_workspace_id', table_name='sonic_perceptual_axis_models')
    op.drop_index('idx_sonic_axis_models_tenant_workspace', table_name='sonic_perceptual_axis_models')
    op.drop_table('sonic_perceptual_axis_models')

    op.drop_index('idx_sonic_axes_tenant_uuid', table_name='sonic_perceptual_axes')
    op.drop_index('idx_sonic_axes_workspace_id', table_name='sonic_perceptual_axes')
    op.drop_index('idx_sonic_axes_tenant_workspace', table_name='sonic_perceptual_axes')
    op.drop_table('sonic_perceptual_axes')

    op.drop_index('idx_sonic_kit_items_segment_id', table_name='sonic_sound_kit_items')
    op.drop_index('idx_sonic_kit_items_sound_kit_id', table_name='sonic_sound_kit_items')
    op.drop_table('sonic_sound_kit_items')

    op.drop_index('idx_sonic_kits_status', table_name='sonic_sound_kits')
    op.drop_index('idx_sonic_kits_tenant_uuid', table_name='sonic_sound_kits')
    op.drop_index('idx_sonic_kits_workspace_id', table_name='sonic_sound_kits')
    op.drop_index('idx_sonic_kits_tenant_workspace', table_name='sonic_sound_kits')
    op.drop_table('sonic_sound_kits')

    op.drop_index('idx_sonic_bookmarks_representative_segment_id', table_name='sonic_bookmarks')
    op.drop_index('idx_sonic_bookmarks_tenant_uuid', table_name='sonic_bookmarks')
    op.drop_index('idx_sonic_bookmarks_workspace_id', table_name='sonic_bookmarks')
    op.drop_index('idx_sonic_bookmarks_tenant_workspace', table_name='sonic_bookmarks')
    op.drop_table('sonic_bookmarks')

    op.drop_index('idx_sonic_traces_intent_card_id', table_name='sonic_decision_traces')
    op.drop_index('idx_sonic_traces_status', table_name='sonic_decision_traces')
    op.drop_index('idx_sonic_traces_tenant_uuid', table_name='sonic_decision_traces')
    op.drop_index('idx_sonic_traces_workspace_id', table_name='sonic_decision_traces')
    op.drop_index('idx_sonic_traces_tenant_workspace', table_name='sonic_decision_traces')
    op.drop_table('sonic_decision_traces')

    op.drop_index('idx_sonic_candidates_intent_card_id', table_name='sonic_candidate_sets')
    op.drop_index('idx_sonic_candidates_tenant_uuid', table_name='sonic_candidate_sets')
    op.drop_index('idx_sonic_candidates_workspace_id', table_name='sonic_candidate_sets')
    op.drop_index('idx_sonic_candidates_tenant_workspace', table_name='sonic_candidate_sets')
    op.drop_table('sonic_candidate_sets')

    op.drop_index('idx_sonic_intents_status', table_name='sonic_intent_cards')
    op.drop_index('idx_sonic_intents_tenant_uuid', table_name='sonic_intent_cards')
    op.drop_index('idx_sonic_intents_workspace_id', table_name='sonic_intent_cards')
    op.drop_index('idx_sonic_intents_tenant_workspace', table_name='sonic_intent_cards')
    op.drop_table('sonic_intent_cards')

    op.drop_index('idx_sonic_embeddings_segment_id', table_name='sonic_embeddings')
    op.drop_index('idx_sonic_embeddings_tenant_uuid', table_name='sonic_embeddings')
    op.drop_index('idx_sonic_embeddings_workspace_id', table_name='sonic_embeddings')
    op.drop_index('idx_sonic_embeddings_tenant_workspace', table_name='sonic_embeddings')
    op.drop_table('sonic_embeddings')

    op.drop_index('idx_sonic_segments_asset', table_name='sonic_segments')
    op.drop_index('idx_sonic_segments_tenant_uuid', table_name='sonic_segments')
    op.drop_index('idx_sonic_segments_workspace_id', table_name='sonic_segments')
    op.drop_index('idx_sonic_segments_tenant_workspace', table_name='sonic_segments')
    op.drop_table('sonic_segments')

    op.drop_index('idx_sonic_licenses_audio_asset_id', table_name='sonic_license_cards')
    op.drop_index('idx_sonic_licenses_risk', table_name='sonic_license_cards')
    op.drop_index('idx_sonic_licenses_tenant_uuid', table_name='sonic_license_cards')
    op.drop_index('idx_sonic_licenses_workspace_id', table_name='sonic_license_cards')
    op.drop_index('idx_sonic_licenses_tenant_workspace', table_name='sonic_license_cards')
    op.drop_table('sonic_license_cards')

    op.drop_index('idx_sonic_assets_status', table_name='sonic_audio_assets')
    op.drop_index('idx_sonic_assets_tenant_uuid', table_name='sonic_audio_assets')
    op.drop_index('idx_sonic_assets_workspace_id', table_name='sonic_audio_assets')
    op.drop_index('idx_sonic_assets_tenant_workspace', table_name='sonic_audio_assets')
    op.drop_table('sonic_audio_assets')

