"""Add pack-neutral projection, multimodal evidence, and graph storage.

Revision ID: 20260727030000
Revises: 20260727020000
Create Date: 2026-07-27
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260727030000"
down_revision = "20260727020000"
branch_labels = None
depends_on = None


JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "knowledge_resource_projections",
        sa.Column("projection_revision_id", sa.Text(), primary_key=True),
        sa.Column(
            "knowledge_resource_id",
            sa.Text(),
            sa.ForeignKey(
                "knowledge_resources.knowledge_resource_id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column("source_instance_id", sa.Text(), nullable=False),
        sa.Column("source_revision", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("descriptor_id", sa.Text(), nullable=False),
        sa.Column("descriptor_revision", sa.Text(), nullable=False),
        sa.Column("projector_revision", sa.Text(), nullable=False),
        sa.Column("facet_schema_revision", sa.Text(), nullable=False),
        sa.Column("embedding_profile_revision", sa.Text(), nullable=False),
        sa.Column("projection_hash", sa.Text(), nullable=False),
        sa.Column("visibility_partition_hash", sa.Text(), nullable=False),
        sa.Column("authz_revision", sa.BigInteger(), nullable=False),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default="staged",
        ),
        sa.Column(
            "active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("FALSE"),
        ),
        sa.Column(
            "evidence_unit_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "record_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "relation_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("activated_at", sa.DateTime(timezone=True)),
        sa.Column("superseded_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN "
            "('staged', 'active', 'degraded_channels', 'degraded_graph', "
            "'superseded', 'revoked')",
            name="ck_knowledge_projections_status",
        ),
        sa.CheckConstraint(
            "char_length(content_hash) = 64 "
            "AND char_length(projection_hash) = 64 "
            "AND char_length(visibility_partition_hash) = 64",
            name="ck_knowledge_projections_hashes",
        ),
        sa.CheckConstraint(
            "authz_revision >= 1",
            name="ck_knowledge_projections_authz_revision",
        ),
        sa.UniqueConstraint(
            "knowledge_resource_id",
            "source_revision",
            "content_hash",
            "projector_revision",
            "embedding_profile_revision",
            name="uq_knowledge_projection_idempotency",
        ),
    )
    op.create_index(
        "uq_knowledge_projection_active_profile",
        "knowledge_resource_projections",
        ["knowledge_resource_id", "embedding_profile_revision"],
        unique=True,
        postgresql_where=sa.text("active"),
    )
    op.create_index(
        "idx_knowledge_projection_source",
        "knowledge_resource_projections",
        ["source_instance_id", "source_revision", "status"],
    )

    op.create_table(
        "knowledge_projection_records",
        sa.Column("projection_record_id", sa.Text(), primary_key=True),
        sa.Column(
            "projection_revision_id",
            sa.Text(),
            sa.ForeignKey(
                "knowledge_resource_projections.projection_revision_id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column(
            "knowledge_resource_id",
            sa.Text(),
            sa.ForeignKey(
                "knowledge_resources.knowledge_resource_id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column("record_kind", sa.Text(), nullable=False),
        sa.Column("record_key", sa.Text(), nullable=False),
        sa.Column("search_text", sa.Text(), nullable=False),
        sa.Column("citation", JSONB, nullable=False),
        sa.Column("values", JSONB, nullable=False),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "char_length(content_hash) = 64",
            name="ck_knowledge_projection_records_content_hash",
        ),
        sa.UniqueConstraint(
            "projection_revision_id",
            "record_kind",
            "record_key",
            name="uq_knowledge_projection_record_key",
        ),
    )
    op.create_index(
        "idx_knowledge_projection_records_resource_kind",
        "knowledge_projection_records",
        ["knowledge_resource_id", "record_kind"],
    )

    op.create_table(
        "knowledge_projection_facets",
        sa.Column("projection_facet_id", sa.Text(), primary_key=True),
        sa.Column(
            "projection_record_id",
            sa.Text(),
            sa.ForeignKey(
                "knowledge_projection_records.projection_record_id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column("facet_key", sa.Text(), nullable=False),
        sa.Column("facet_type", sa.Text(), nullable=False),
        sa.Column("text_value", sa.Text()),
        sa.Column("number_value", sa.Numeric()),
        sa.Column("bool_value", sa.Boolean()),
        sa.Column("timestamp_value", sa.DateTime(timezone=True)),
        sa.Column("ref_value", sa.Text()),
        sa.Column("ordinal", sa.Integer(), nullable=False, server_default="0"),
        sa.CheckConstraint(
            "facet_type IN "
            "('string', 'number', 'boolean', 'timestamp', 'enum', 'ref')",
            name="ck_knowledge_projection_facets_type",
        ),
        sa.CheckConstraint(
            "num_nonnulls("
            "text_value, number_value, bool_value, timestamp_value, ref_value"
            ") = 1",
            name="ck_knowledge_projection_facets_exactly_one_value",
        ),
        sa.UniqueConstraint(
            "projection_record_id",
            "facet_key",
            "ordinal",
            name="uq_knowledge_projection_facet_ordinal",
        ),
    )
    op.create_index(
        "idx_knowledge_facets_text",
        "knowledge_projection_facets",
        ["facet_key", "text_value", "projection_record_id"],
    )
    op.create_index(
        "idx_knowledge_facets_number",
        "knowledge_projection_facets",
        ["facet_key", "number_value", "projection_record_id"],
    )
    op.create_index(
        "idx_knowledge_facets_timestamp",
        "knowledge_projection_facets",
        ["facet_key", "timestamp_value", "projection_record_id"],
    )

    op.create_table(
        "knowledge_evidence_units",
        sa.Column("evidence_unit_row_id", sa.Text(), primary_key=True),
        sa.Column(
            "projection_revision_id",
            sa.Text(),
            sa.ForeignKey(
                "knowledge_resource_projections.projection_revision_id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column(
            "knowledge_resource_id",
            sa.Text(),
            sa.ForeignKey(
                "knowledge_resources.knowledge_resource_id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column(
            "security_label_id",
            sa.Text(),
            sa.ForeignKey(
                "knowledge_security_labels.security_label_id",
                ondelete="RESTRICT",
            ),
            nullable=False,
        ),
        sa.Column("unit_key", sa.Text(), nullable=False),
        sa.Column("unit_kind", sa.Text(), nullable=False),
        sa.Column("owner_asset_ref", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("media_type", sa.Text()),
        sa.Column("anchor", JSONB, nullable=False),
        sa.Column("derivative_refs", JSONB, nullable=False, server_default="[]"),
        sa.Column("external_doc_id", postgresql.UUID(as_uuid=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "unit_kind IN "
            "('text_span', 'image_region', 'video_segment', 'audio_segment')",
            name="ck_knowledge_evidence_units_kind",
        ),
        sa.CheckConstraint(
            "char_length(content_hash) = 64",
            name="ck_knowledge_evidence_units_content_hash",
        ),
        sa.UniqueConstraint(
            "projection_revision_id",
            "unit_key",
            name="uq_knowledge_evidence_unit_key",
        ),
    )
    op.create_index(
        "idx_knowledge_evidence_units_binding",
        "knowledge_evidence_units",
        ["knowledge_resource_id", "security_label_id", "unit_kind"],
    )

    op.create_table(
        "knowledge_embedding_channel_receipts",
        sa.Column("channel_receipt_id", sa.Text(), primary_key=True),
        sa.Column(
            "projection_revision_id",
            sa.Text(),
            sa.ForeignKey(
                "knowledge_resource_projections.projection_revision_id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column(
            "evidence_unit_row_id",
            sa.Text(),
            sa.ForeignKey(
                "knowledge_evidence_units.evidence_unit_row_id",
                ondelete="CASCADE",
            ),
        ),
        sa.Column("channel_id", sa.Text(), nullable=False),
        sa.Column("modality", sa.Text(), nullable=False),
        sa.Column("profile_revision", sa.Text(), nullable=False),
        sa.Column("model_revision", sa.Text()),
        sa.Column("dimension", sa.Integer()),
        sa.Column("calibration_revision", sa.Text()),
        sa.Column("index_revision", sa.Text()),
        sa.Column(
            "required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("FALSE"),
        ),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("byte_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("reason", sa.Text()),
        sa.Column("physical_store_ref", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "modality IN ('text', 'image', 'video', 'audio')",
            name="ck_knowledge_channel_receipts_modality",
        ),
        sa.CheckConstraint(
            "state IN "
            "('active', 'pending', 'degraded', 'unsupported', "
            "'not_admitted', 'failed', 'revoked')",
            name="ck_knowledge_channel_receipts_state",
        ),
        sa.CheckConstraint(
            "row_count >= 0 AND byte_count >= 0",
            name="ck_knowledge_channel_receipts_counts",
        ),
        sa.CheckConstraint(
            "(state = 'active' AND model_revision IS NOT NULL "
            "AND index_revision IS NOT NULL AND row_count > 0) "
            "OR (state <> 'active' AND row_count = 0)",
            name="ck_knowledge_channel_receipts_active_shape",
        ),
        sa.UniqueConstraint(
            "projection_revision_id",
            "evidence_unit_row_id",
            "channel_id",
            name="uq_knowledge_channel_receipt",
        ),
    )
    op.create_index(
        "idx_knowledge_channel_receipts_projection_state",
        "knowledge_embedding_channel_receipts",
        ["projection_revision_id", "channel_id", "state"],
    )

    op.create_table(
        "knowledge_graph_entities",
        sa.Column("entity_id", sa.Text(), primary_key=True),
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("scope_type", sa.Text(), nullable=False),
        sa.Column("scope_id", sa.Text(), nullable=False),
        sa.Column("canonical_key", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("resolver_revision", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "scope_type IN ('tenant', 'workspace', 'group')",
            name="ck_knowledge_graph_entities_scope",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "scope_type",
            "scope_id",
            "canonical_key",
            "entity_type",
            "resolver_revision",
            name="uq_knowledge_graph_entity_revision",
        ),
    )
    op.create_table(
        "knowledge_graph_mentions",
        sa.Column("mention_id", sa.Text(), primary_key=True),
        sa.Column(
            "entity_id",
            sa.Text(),
            sa.ForeignKey("knowledge_graph_entities.entity_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "projection_revision_id",
            sa.Text(),
            sa.ForeignKey(
                "knowledge_resource_projections.projection_revision_id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column(
            "knowledge_resource_id",
            sa.Text(),
            sa.ForeignKey(
                "knowledge_resources.knowledge_resource_id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column(
            "security_label_id",
            sa.Text(),
            sa.ForeignKey(
                "knowledge_security_labels.security_label_id",
                ondelete="RESTRICT",
            ),
            nullable=False,
        ),
        sa.Column("evidence_unit_row_id", sa.Text()),
        sa.Column("projection_record_id", sa.Text()),
        sa.Column("surface_text", sa.Text(), nullable=False),
        sa.Column("mention_type", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("citation", JSONB, nullable=False),
        sa.Column("extractor_revision", sa.Text(), nullable=False),
        sa.Column("model_revision", sa.Text(), nullable=False),
        sa.Column("prompt_revision", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_knowledge_graph_mentions_confidence",
        ),
        sa.CheckConstraint(
            "num_nonnulls(evidence_unit_row_id, projection_record_id) >= 1",
            name="ck_knowledge_graph_mentions_evidence",
        ),
    )
    op.create_index(
        "idx_knowledge_graph_mentions_entity_binding",
        "knowledge_graph_mentions",
        ["entity_id", "security_label_id", "projection_revision_id"],
    )

    op.create_table(
        "knowledge_graph_relations",
        sa.Column("relation_id", sa.Text(), primary_key=True),
        sa.Column(
            "projection_revision_id",
            sa.Text(),
            sa.ForeignKey(
                "knowledge_resource_projections.projection_revision_id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column(
            "source_entity_id",
            sa.Text(),
            sa.ForeignKey("knowledge_graph_entities.entity_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "target_entity_id",
            sa.Text(),
            sa.ForeignKey("knowledge_graph_entities.entity_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("relation_kind", sa.Text(), nullable=False),
        sa.Column("origin", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("supporting_resource_ids", JSONB, nullable=False),
        sa.Column("supporting_citations", JSONB, nullable=False),
        sa.Column("extractor_revision", sa.Text()),
        sa.Column("owner_relation_revision", sa.Text()),
        sa.Column("visibility_partition_hash", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "origin IN ('owner_declared', 'extracted')",
            name="ck_knowledge_graph_relations_origin",
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_knowledge_graph_relations_confidence",
        ),
        sa.CheckConstraint(
            "(origin = 'owner_declared' "
            "AND owner_relation_revision IS NOT NULL) "
            "OR (origin = 'extracted' AND extractor_revision IS NOT NULL)",
            name="ck_knowledge_graph_relations_revision",
        ),
        sa.CheckConstraint(
            "char_length(visibility_partition_hash) = 64",
            name="ck_knowledge_graph_relations_visibility_hash",
        ),
    )
    op.create_index(
        "idx_knowledge_graph_relations_source",
        "knowledge_graph_relations",
        ["source_entity_id", "relation_kind", "projection_revision_id"],
    )
    op.create_index(
        "idx_knowledge_graph_relations_target",
        "knowledge_graph_relations",
        ["target_entity_id", "relation_kind", "projection_revision_id"],
    )

    op.create_table(
        "knowledge_graph_communities",
        sa.Column("community_id", sa.Text(), primary_key=True),
        sa.Column("graph_generation_id", sa.Text(), nullable=False),
        sa.Column(
            "projection_revision_id",
            sa.Text(),
            sa.ForeignKey(
                "knowledge_resource_projections.projection_revision_id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column(
            "knowledge_resource_id",
            sa.Text(),
            sa.ForeignKey(
                "knowledge_resources.knowledge_resource_id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column(
            "security_label_id",
            sa.Text(),
            sa.ForeignKey(
                "knowledge_security_labels.security_label_id",
                ondelete="RESTRICT",
            ),
            nullable=False,
        ),
        sa.Column("authz_revision", sa.BigInteger(), nullable=False),
        sa.Column("algorithm_revision", sa.Text(), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column(
            "parent_community_id",
            sa.Text(),
            sa.ForeignKey(
                "knowledge_graph_communities.community_id",
                ondelete="CASCADE",
            ),
        ),
        sa.Column("visibility_partition_hash", sa.Text(), nullable=False),
        sa.Column("affected_subgraph_hash", sa.Text(), nullable=False),
        sa.Column("full_rebuild_hash", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "level >= 0",
            name="ck_knowledge_graph_communities_level",
        ),
        sa.CheckConstraint(
            "authz_revision >= 1",
            name="ck_knowledge_graph_communities_authz_revision",
        ),
        sa.CheckConstraint(
            "char_length(visibility_partition_hash) = 64 "
            "AND char_length(affected_subgraph_hash) = 64 "
            "AND char_length(full_rebuild_hash) = 64",
            name="ck_knowledge_graph_communities_hashes",
        ),
        sa.UniqueConstraint(
            "graph_generation_id",
            "algorithm_revision",
            "level",
            "visibility_partition_hash",
            "community_id",
            name="uq_knowledge_graph_community_generation",
        ),
    )
    op.create_table(
        "knowledge_graph_community_memberships",
        sa.Column(
            "community_id",
            sa.Text(),
            sa.ForeignKey(
                "knowledge_graph_communities.community_id",
                ondelete="CASCADE",
            ),
            primary_key=True,
        ),
        sa.Column(
            "entity_id",
            sa.Text(),
            sa.ForeignKey("knowledge_graph_entities.entity_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("relation_ids", JSONB, nullable=False),
    )
    op.create_index(
        "idx_knowledge_graph_communities_projection",
        "knowledge_graph_communities",
        ["projection_revision_id", "security_label_id", "authz_revision"],
    )
    op.create_index(
        "idx_knowledge_graph_memberships_entity",
        "knowledge_graph_community_memberships",
        ["entity_id", "community_id"],
    )
    op.create_table(
        "knowledge_graph_community_reports",
        sa.Column("community_report_id", sa.Text(), primary_key=True),
        sa.Column(
            "community_id",
            sa.Text(),
            sa.ForeignKey(
                "knowledge_graph_communities.community_id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column("authz_revision", sa.BigInteger(), nullable=False),
        sa.Column("visibility_partition_hash", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("findings", JSONB, nullable=False),
        sa.Column("rank", sa.Float(), nullable=False),
        sa.Column("supporting_citations", JSONB, nullable=False),
        sa.Column("model_revision", sa.Text(), nullable=False),
        sa.Column("prompt_revision", sa.Text(), nullable=False),
        sa.Column(
            "active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("FALSE"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "authz_revision >= 1",
            name="ck_knowledge_graph_reports_authz_revision",
        ),
        sa.CheckConstraint(
            "char_length(visibility_partition_hash) = 64",
            name="ck_knowledge_graph_reports_visibility_hash",
        ),
        sa.UniqueConstraint(
            "community_id",
            "authz_revision",
            "model_revision",
            "prompt_revision",
            name="uq_knowledge_graph_community_report_revision",
        ),
    )
    op.create_index(
        "idx_knowledge_graph_reports_active_partition",
        "knowledge_graph_community_reports",
        ["visibility_partition_hash", "authz_revision"],
        postgresql_where=sa.text("active"),
    )

    op.add_column(
        "external_docs",
        sa.Column("projection_revision_id", sa.Text(), nullable=True),
    )
    op.create_index(
        "idx_external_docs_projection_revision",
        "external_docs",
        ["projection_revision_id"],
    )
    op.create_foreign_key(
        "fk_external_docs_projection_revision",
        "external_docs",
        "knowledge_resource_projections",
        ["projection_revision_id"],
        ["projection_revision_id"],
        ondelete="RESTRICT",
        postgresql_not_valid=True,
    )
    op.execute(
        "ALTER TABLE external_docs "
        "VALIDATE CONSTRAINT fk_external_docs_projection_revision"
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_external_docs_projection_revision",
        "external_docs",
        type_="foreignkey",
    )
    op.drop_index(
        "idx_external_docs_projection_revision",
        table_name="external_docs",
    )
    op.drop_column("external_docs", "projection_revision_id")
    op.drop_table("knowledge_graph_community_reports")
    op.drop_table("knowledge_graph_community_memberships")
    op.drop_table("knowledge_graph_communities")
    op.drop_table("knowledge_graph_relations")
    op.drop_table("knowledge_graph_mentions")
    op.drop_table("knowledge_graph_entities")
    op.drop_table("knowledge_embedding_channel_receipts")
    op.drop_table("knowledge_evidence_units")
    op.drop_table("knowledge_projection_facets")
    op.drop_table("knowledge_projection_records")
    op.drop_table("knowledge_resource_projections")
