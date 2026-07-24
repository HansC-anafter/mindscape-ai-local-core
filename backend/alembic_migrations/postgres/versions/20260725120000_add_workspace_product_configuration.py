"""Add immutable PCS catalog and workspace/group product configuration.

Revision ID: 20260725120000
Revises: 20260715130000
Create Date: 2026-07-25 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260725120000"
down_revision = "20260715130000"
branch_labels = None
depends_on = "20260716020000"


def upgrade() -> None:
    op.execute("SET lock_timeout = '15s'")
    op.execute("SET statement_timeout = '120s'")

    op.create_table(
        "product_capability_catalog_versions",
        sa.Column("artifact_hash", sa.String(length=64), primary_key=True),
        sa.Column("catalog_hash", sa.String(length=64), nullable=False),
        sa.Column("source_commit", sa.String(length=64), nullable=False),
        sa.Column("compiler_version", sa.String(length=32), nullable=False),
        sa.Column("artifact_json", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("imported_by", sa.String(length=128), nullable=False),
        sa.Column(
            "imported_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "status IN ('active', 'inactive')",
            name="chk_product_catalog_status",
        ),
    )
    op.create_index(
        "idx_product_catalog_semantic_hash",
        "product_capability_catalog_versions",
        ["catalog_hash"],
    )
    op.create_index(
        "uq_product_catalog_one_active",
        "product_capability_catalog_versions",
        ["status"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )

    op.create_table(
        "workspace_product_configuration_scopes",
        sa.Column("scope_kind", sa.String(length=16), primary_key=True),
        sa.Column("scope_id", sa.String(length=128), primary_key=True),
        sa.Column("catalog_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "revision",
            sa.BigInteger(),
            nullable=False,
            server_default="1",
        ),
        sa.Column("admission_mode", sa.String(length=32), nullable=True),
        sa.Column("updated_by", sa.String(length=128), nullable=False),
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
            "scope_kind IN ('workspace', 'workspace_group')",
            name="chk_workspace_product_scope_kind",
        ),
        sa.CheckConstraint(
            "revision >= 1",
            name="chk_workspace_product_scope_revision",
        ),
        sa.CheckConstraint(
            "("
            "scope_kind = 'workspace' AND admission_mode IN "
            "('configuration_only', 'shadow', 'enforced')"
            ") OR ("
            "scope_kind = 'workspace_group' AND admission_mode IS NULL"
            ")",
            name="chk_workspace_product_admission_owner",
        ),
    )
    op.create_index(
        "idx_workspace_product_scope_catalog",
        "workspace_product_configuration_scopes",
        ["catalog_hash", "scope_kind"],
    )

    op.create_table(
        "workspace_product_configuration_assignments",
        sa.Column("scope_kind", sa.String(length=16), primary_key=True),
        sa.Column("scope_id", sa.String(length=128), primary_key=True),
        sa.Column("pcs_id", sa.String(length=128), primary_key=True),
        sa.Column("pcs_version", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.ForeignKeyConstraint(
            ["scope_kind", "scope_id"],
            [
                "workspace_product_configuration_scopes.scope_kind",
                "workspace_product_configuration_scopes.scope_id",
            ],
            ondelete="CASCADE",
        ),
    )

    op.create_table(
        "workspace_product_configuration_receipts",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("scope_kind", sa.String(length=16), nullable=False),
        sa.Column("scope_id", sa.String(length=128), nullable=False),
        sa.Column("previous_revision", sa.BigInteger(), nullable=False),
        sa.Column("new_revision", sa.BigInteger(), nullable=False),
        sa.Column("catalog_hash", sa.String(length=64), nullable=False),
        sa.Column("admission_mode", sa.String(length=32), nullable=True),
        sa.Column("assignments", postgresql.JSONB(), nullable=False),
        sa.Column("actor_user_id", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "new_revision = previous_revision + 1",
            name="chk_workspace_product_receipt_revision",
        ),
    )
    op.create_index(
        "idx_workspace_product_receipt_scope",
        "workspace_product_configuration_receipts",
        ["scope_kind", "scope_id", "created_at"],
    )

    op.execute("RESET statement_timeout")
    op.execute("RESET lock_timeout")


def downgrade() -> None:
    op.execute("SET lock_timeout = '15s'")
    op.execute("SET statement_timeout = '120s'")
    op.drop_index(
        "idx_workspace_product_receipt_scope",
        table_name="workspace_product_configuration_receipts",
    )
    op.drop_table("workspace_product_configuration_receipts")
    op.drop_table("workspace_product_configuration_assignments")
    op.drop_index(
        "idx_workspace_product_scope_catalog",
        table_name="workspace_product_configuration_scopes",
    )
    op.drop_table("workspace_product_configuration_scopes")
    op.drop_index(
        "uq_product_catalog_one_active",
        table_name="product_capability_catalog_versions",
    )
    op.drop_index(
        "idx_product_catalog_semantic_hash",
        table_name="product_capability_catalog_versions",
    )
    op.drop_table("product_capability_catalog_versions")
    op.execute("RESET statement_timeout")
    op.execute("RESET lock_timeout")
