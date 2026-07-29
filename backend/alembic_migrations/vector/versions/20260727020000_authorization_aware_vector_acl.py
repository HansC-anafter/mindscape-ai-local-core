"""Add canonical resource, security-label, grant, audit, and chunk bindings.

Revision ID: 20260727020000
Revises: 20260727010000
Create Date: 2026-07-27
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260727020000"
down_revision = "20260727010000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "knowledge_security_labels",
        sa.Column("security_label_id", sa.Text(), primary_key=True),
        sa.Column("classification", sa.Text(), nullable=False),
        sa.Column(
            "authz_revision",
            sa.BigInteger(),
            nullable=False,
            server_default="1",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "classification IN ('private', 'workspace', 'group')",
            name="ck_knowledge_security_labels_classification",
        ),
        sa.CheckConstraint(
            "authz_revision >= 1",
            name="ck_knowledge_security_labels_revision",
        ),
    )
    op.create_table(
        "knowledge_resources",
        sa.Column("knowledge_resource_id", sa.Text(), primary_key=True),
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("owner_capability_code", sa.Text(), nullable=False),
        sa.Column("source_kind", sa.Text(), nullable=False),
        sa.Column("source_app", sa.Text(), nullable=False),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("source_ref", sa.Text(), nullable=False),
        sa.Column("source_revision", sa.Text(), nullable=False),
        sa.Column("owner_scope_type", sa.Text(), nullable=False),
        sa.Column("owner_scope_id", sa.Text(), nullable=False),
        sa.Column(
            "security_label_id",
            sa.Text(),
            sa.ForeignKey(
                "knowledge_security_labels.security_label_id",
                ondelete="RESTRICT",
            ),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("TRUE"),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "source_kind IN ('object', 'artifact', 'memory', 'document')",
            name="ck_knowledge_resources_source_kind",
        ),
        sa.CheckConstraint(
            "owner_scope_type IN ('tenant', 'workspace', 'group')",
            name="ck_knowledge_resources_owner_scope_type",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "owner_capability_code",
            "source_kind",
            "source_ref",
            "owner_scope_type",
            "owner_scope_id",
            name="uq_knowledge_resources_stable_identity",
        ),
    )
    op.create_table(
        "knowledge_security_label_grants",
        sa.Column("grant_id", sa.Text(), primary_key=True),
        sa.Column(
            "security_label_id",
            sa.Text(),
            sa.ForeignKey(
                "knowledge_security_labels.security_label_id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column("principal_type", sa.Text(), nullable=False),
        sa.Column("principal_id", sa.Text(), nullable=False),
        sa.Column("relation", sa.Text(), nullable=False),
        sa.Column("effect", sa.Text(), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True)),
        sa.Column("valid_until", sa.DateTime(timezone=True)),
        sa.Column("authz_revision", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "principal_type IN "
            "('user', 'workspace_role', 'group_role', 'service')",
            name="ck_knowledge_grants_principal_type",
        ),
        sa.CheckConstraint(
            "effect IN ('allow', 'deny')",
            name="ck_knowledge_grants_effect",
        ),
        sa.CheckConstraint(
            "relation IN ('reader', 'editor', 'owner', 'ingester')",
            name="ck_knowledge_grants_relation",
        ),
        sa.CheckConstraint(
            "authz_revision >= 1",
            name="ck_knowledge_grants_revision",
        ),
        sa.CheckConstraint(
            "valid_until IS NULL OR valid_from IS NULL "
            "OR valid_until > valid_from",
            name="ck_knowledge_grants_validity_window",
        ),
        sa.UniqueConstraint(
            "security_label_id",
            "principal_type",
            "principal_id",
            "relation",
            "effect",
            name="uq_knowledge_grants_normalized",
        ),
    )
    op.create_table(
        "knowledge_acl_audit_log",
        sa.Column("mutation_id", sa.Text(), primary_key=True),
        sa.Column("actor_user_id", sa.Text(), nullable=False),
        sa.Column("principal_context_hash", sa.Text(), nullable=False),
        sa.Column(
            "knowledge_resource_id",
            sa.Text(),
            sa.ForeignKey(
                "knowledge_resources.knowledge_resource_id",
                ondelete="RESTRICT",
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
        sa.Column("old_authz_revision", sa.BigInteger(), nullable=False),
        sa.Column("new_authz_revision", sa.BigInteger(), nullable=False),
        sa.Column("diff_digest", sa.Text(), nullable=False),
        sa.Column(
            "normalized_diff",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "char_length(principal_context_hash) = 64",
            name="ck_knowledge_acl_audit_context_hash",
        ),
        sa.CheckConstraint(
            "char_length(diff_digest) = 64",
            name="ck_knowledge_acl_audit_diff_hash",
        ),
        sa.CheckConstraint(
            "new_authz_revision >= old_authz_revision",
            name="ck_knowledge_acl_audit_revision_order",
        ),
    )

    op.create_index(
        "idx_knowledge_resources_scope",
        "knowledge_resources",
        ["tenant_id", "owner_scope_type", "owner_scope_id", "active"],
    )
    op.create_index(
        "idx_knowledge_resources_source",
        "knowledge_resources",
        ["source_app", "source_id", "source_revision"],
    )
    op.create_index(
        "idx_knowledge_grants_principal",
        "knowledge_security_label_grants",
        ["principal_type", "principal_id", "effect", "security_label_id"],
    )
    op.create_index(
        "idx_knowledge_grants_label_revision",
        "knowledge_security_label_grants",
        ["security_label_id", "authz_revision"],
    )
    op.create_index(
        "idx_knowledge_acl_audit_resource_created",
        "knowledge_acl_audit_log",
        ["knowledge_resource_id", "created_at"],
    )

    op.add_column(
        "external_docs",
        sa.Column("knowledge_resource_id", sa.Text(), nullable=True),
    )
    op.add_column(
        "external_docs",
        sa.Column("security_label_id", sa.Text(), nullable=True),
    )
    op.create_index(
        "idx_external_docs_knowledge_resource",
        "external_docs",
        ["knowledge_resource_id"],
    )
    op.create_index(
        "idx_external_docs_security_label",
        "external_docs",
        ["security_label_id"],
    )

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM external_docs
                WHERE source_app <> 'document_ingestion'
                   OR NULLIF((metadata->>'workspace_id'), '') IS NULL
                   OR NULLIF((metadata->>'document_id'), '') IS NULL
                   OR NULLIF(metadata->>'revision_id', '') IS NULL
                   OR NULLIF(user_id, '') IS NULL
            ) THEN
                RAISE EXCEPTION
                    'knowledge_acl_backfill_unmapped_external_docs';
            END IF;
            IF EXISTS (
                SELECT 1
                FROM external_docs
                GROUP BY
                    source_app,
                    (metadata->>'workspace_id'),
                    (metadata->>'document_id')
                HAVING COUNT(DISTINCT user_id) <> 1
            ) THEN
                RAISE EXCEPTION
                    'knowledge_acl_backfill_ambiguous_document_owner';
            END IF;
        END
        $$;
        """
    )
    op.execute(
        """
        WITH mapped AS (
            SELECT DISTINCT
                'kr_' || encode(
                    sha256(convert_to(
                        concat_ws(
                            chr(31), source_app, 'document',
                            'document:' || (metadata->>'document_id'),
                            'workspace', (metadata->>'workspace_id')
                        ),
                        'UTF8'
                    )),
                    'hex'
                ) AS resource_id
            FROM external_docs
        ),
        labeled AS (
            SELECT
                resource_id,
                'ksl_' || encode(
                    sha256(convert_to(resource_id, 'UTF8')),
                    'hex'
                ) AS label_id
            FROM mapped
        )
        INSERT INTO knowledge_security_labels (
            security_label_id, classification, authz_revision
        )
        SELECT label_id, 'private', 1
        FROM labeled
        """
    )
    op.execute(
        """
        WITH mapped AS (
            SELECT DISTINCT ON (
                source_app,
                (metadata->>'workspace_id'),
                (metadata->>'document_id')
            )
                'kr_' || encode(
                    sha256(convert_to(
                        concat_ws(
                            chr(31), source_app, 'document',
                            'document:' || (metadata->>'document_id'),
                            'workspace', (metadata->>'workspace_id')
                        ),
                        'UTF8'
                    )),
                    'hex'
                ) AS resource_id,
                source_app,
                (metadata->>'document_id') AS document_id,
                metadata->>'revision_id' AS source_revision,
                (metadata->>'workspace_id') AS workspace_id
            FROM external_docs
            ORDER BY
                source_app,
                (metadata->>'workspace_id'),
                (metadata->>'document_id'),
                updated_at DESC,
                id
        ),
        labeled AS (
            SELECT
                mapped.*,
                'ksl_' || encode(
                    sha256(convert_to(resource_id, 'UTF8')),
                    'hex'
                ) AS label_id
            FROM mapped
        )
        INSERT INTO knowledge_resources (
            knowledge_resource_id, tenant_id, owner_capability_code,
            source_kind, source_app, source_id, source_ref, source_revision,
            owner_scope_type, owner_scope_id, security_label_id
        )
        SELECT
            resource_id, 'local', source_app,
            'document', source_app, document_id,
            'document:' || document_id, source_revision,
            'workspace', workspace_id, label_id
        FROM labeled
        """
    )
    op.execute(
        """
        WITH mapped AS (
            SELECT DISTINCT
                'kr_' || encode(
                    sha256(convert_to(
                        concat_ws(
                            chr(31), source_app, 'document',
                            'document:' || (metadata->>'document_id'),
                            'workspace', (metadata->>'workspace_id')
                        ),
                        'UTF8'
                    )),
                    'hex'
                ) AS resource_id,
                user_id
            FROM external_docs
        ),
        labeled AS (
            SELECT
                resource_id,
                'ksl_' || encode(
                    sha256(convert_to(resource_id, 'UTF8')),
                    'hex'
                ) AS label_id,
                user_id
            FROM mapped
        )
        INSERT INTO knowledge_security_label_grants (
            grant_id, security_label_id, principal_type, principal_id,
            relation, effect, authz_revision
        )
        SELECT
            'kg_' || encode(
                sha256(convert_to(
                    concat_ws(
                        chr(31), label_id, 'user', user_id, 'owner', 'allow'
                    ),
                    'UTF8'
                )),
                'hex'
            ),
            label_id, 'user', user_id, 'owner', 'allow', 1
        FROM labeled
        """
    )
    op.execute(
        """
        UPDATE external_docs AS document
        SET
            knowledge_resource_id = mapped.resource_id,
            security_label_id = mapped.label_id
        FROM (
            SELECT
                id,
                'kr_' || encode(
                    sha256(convert_to(
                        concat_ws(
                            chr(31), source_app, 'document',
                            'document:' || (metadata->>'document_id'),
                            'workspace', (metadata->>'workspace_id')
                        ),
                        'UTF8'
                    )),
                    'hex'
                ) AS resource_id
            FROM external_docs
        ) AS base_mapped
        CROSS JOIN LATERAL (
            SELECT
                base_mapped.resource_id,
                'ksl_' || encode(
                    sha256(convert_to(base_mapped.resource_id, 'UTF8')),
                    'hex'
                ) AS label_id
        ) AS mapped
        WHERE document.id = base_mapped.id
        """
    )

    op.create_foreign_key(
        "fk_external_docs_knowledge_resource",
        "external_docs",
        "knowledge_resources",
        ["knowledge_resource_id"],
        ["knowledge_resource_id"],
        ondelete="RESTRICT",
        postgresql_not_valid=True,
    )
    op.create_foreign_key(
        "fk_external_docs_security_label",
        "external_docs",
        "knowledge_security_labels",
        ["security_label_id"],
        ["security_label_id"],
        ondelete="RESTRICT",
        postgresql_not_valid=True,
    )
    op.execute(
        "ALTER TABLE external_docs "
        "VALIDATE CONSTRAINT fk_external_docs_knowledge_resource"
    )
    op.execute(
        "ALTER TABLE external_docs "
        "VALIDATE CONSTRAINT fk_external_docs_security_label"
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM external_docs AS document
                JOIN knowledge_resources AS resource
                  ON resource.knowledge_resource_id =
                     document.knowledge_resource_id
                WHERE document.security_label_id <>
                      resource.security_label_id
                   OR document.knowledge_resource_id IS NULL
                   OR document.security_label_id IS NULL
            ) OR EXISTS (
                SELECT 1
                FROM external_docs
                WHERE knowledge_resource_id IS NULL
                   OR security_label_id IS NULL
            ) THEN
                RAISE EXCEPTION
                    'knowledge_acl_backfill_binding_validation_failed';
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_external_docs_security_label",
        "external_docs",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_external_docs_knowledge_resource",
        "external_docs",
        type_="foreignkey",
    )
    op.drop_index("idx_external_docs_security_label", table_name="external_docs")
    op.drop_index("idx_external_docs_knowledge_resource", table_name="external_docs")
    op.drop_column("external_docs", "security_label_id")
    op.drop_column("external_docs", "knowledge_resource_id")
    op.drop_table("knowledge_acl_audit_log")
    op.drop_table("knowledge_security_label_grants")
    op.drop_table("knowledge_resources")
    op.drop_table("knowledge_security_labels")
